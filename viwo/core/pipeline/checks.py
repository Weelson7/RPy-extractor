"""VERIFY stage warnings (doc 3.1) and the per-plugin verify call (doc 2.2, 0.4)."""

from __future__ import annotations

from dataclasses import replace

from viwo.contracts.pipeline import PluginRun


def _verify(unpacked, collected) -> list[str]:
    warnings = []
    if unpacked.found and not unpacked.extracted:
        warnings.append("Archives were discovered but none extracted successfully.")
    if collected.scanned == 0:
        warnings.append("No files were scanned from source roots.")
    if collected.collected == 0:
        warnings.append("No files were copied into the output folder.")
    return warnings


def verify_one(plugin, ctx, collected: int) -> tuple[tuple[str, ...], int, int]:
    """(warnings, inventory items, items found) from the plugin's verify_report() (doc 2.2)."""
    inventory = tuple(plugin.inventory(ctx))
    report = plugin.verify_report(ctx, inventory, None, collected)
    found = tuple(f"verify: {w}" for w in report.warnings)
    if not report.ok and not found:
        found = (f"verify: {plugin.manifest.name}: verification failed",)
    return found, report.expected, report.found


def verified(run, runs: list[PluginRun], collected: int) -> list[PluginRun]:
    """Plugin `verify()` warnings land on the plugin's own entry (doc 3.4 failure isolation)."""
    out = []
    for r in runs:
        plugin, items, hit = run.rt.plugins[r.plugin_id], 0, 0
        try:
            found, items, hit = verify_one(plugin, run.ctx(r.plugin_id), collected)
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
