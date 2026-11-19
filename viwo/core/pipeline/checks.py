"""VERIFY stage warnings (doc 3.1) and the per-plugin verify call (doc 2.2, 0.4)."""

from dataclasses import replace
from pathlib import PurePosixPath

from viwo.contracts import workspace as ws
from viwo.contracts.pipeline import PluginRun

SHOWN = 5  # missing inventory items named in the warning


def _verify(unpacked, collected) -> list[str]:
    warnings = []
    if unpacked.found and not unpacked.extracted:
        warnings.append("Archives were discovered but none extracted successfully.")
    if collected.scanned == 0:
        warnings.append("No files were scanned from source roots.")
    if collected.collected == 0:
        warnings.append("No files were copied into the output folder.")
    if collected.unreadable:
        shown = ", ".join(collected.unreadable[:5])
        warnings.append(
            f"{len(collected.unreadable)} file(s) could not be read "
            f"(antivirus block or lock), skipped: {shown}"
        )
    return warnings + collected.warnings


def recorded(provenance: list[dict]) -> frozenset[str]:
    """What COLLECT recorded, named as an inventory names it (doc 0.4, 2.2): `<container>/
    <member>` for a container's member, the game-relative path for a loose file."""
    return frozenset(
        f"{p['container']}/{p['member']}" if p.get("container") else str(p.get("member", ""))
        for p in provenance
    )


def _counted(inventory, collected: frozenset[str], selected) -> tuple[int, int, list[str]]:
    """(items, items collected, the missing ones) of an inventory; only the items of the
    extensions the run selected count (a filtered run never claims the rest)."""
    items = {i for i in inventory if selected is None or ws.ext_of(PurePosixPath(i)) in selected}
    missing = sorted(items - collected)
    return len(items), len(items) - len(missing), missing


def verify_one(
    plugin, ctx, collected: int, members=frozenset()
) -> tuple[tuple[str, ...], int, int]:
    """(warnings, inventory items, items found) from the plugin's verify_report() (doc 2.2).
    A plugin that keeps an inventory is counted by core against what COLLECT recorded
    (`members`, see `recorded`), and every item that did not come out is said."""
    inventory = tuple(plugin.inventory(ctx))
    report = plugin.verify_report(ctx, inventory, None, collected)
    found = tuple(f"verify: {w}" for w in report.warnings)
    if not report.ok and not found:
        found = (f"verify: {plugin.manifest.name}: verification failed",)
    if not inventory:
        return found, report.expected, report.found
    items, hit, missing = _counted(inventory, members, ctx.selected_exts)
    if missing:
        first = ", ".join(missing[:SHOWN])
        found += (
            f"verify: {plugin.manifest.name}: {len(missing)} of {items} inventory item(s) "
            f"not collected, first: {first}",
        )
    return found, items, hit


def verified(run, runs: list[PluginRun], collected: int, members=frozenset()) -> list[PluginRun]:
    """Plugin `verify()` warnings land on the plugin's own entry (doc 3.4 failure isolation)."""
    out = []
    for r in runs:
        plugin, items, hit = run.rt.plugins[r.plugin_id], 0, 0
        try:
            found, items, hit = verify_one(plugin, run.ctx(r.plugin_id), collected, members)
            error = r.error
        except Exception as exc:  # one plugin's verify never takes the run down
            found = (f"verify: {type(exc).__name__}: {exc}",)
            error = r.error or found[0]
        out.append(
            replace(
                r,
                warnings=(*r.warnings, *found),
                error=error,
                verify_passed=not found,
                inventory_items=items,
                inventory_found=hit,
            )
        )
    return out
