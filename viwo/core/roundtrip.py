"""Round trip (doc 18): edit set -> plan -> patched copy -> pack -> verify -> report.

The game folder is only read. Edited workspace files are found by hash against the
provenance map; loose files are overridden in the copy, container members go through the
owning plugin's pack.* slot, and every packed container is re-extracted to verify it.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.contracts.types import CancelToken

from .context import core_context
from .pipeline.collect import sha256
from .pipeline.failover import run_with_failover
from .pipeline.guard import change_warning, refuse_writes_inside, snapshot
from .pipeline.identify import identify
from .pipeline.ticker import Ticker
from .records import record_context
from .roundtrip_edits import Edit, edit_set, original_hashes
from .steps import tell, teller
from .workspace import workspace_lock, write_atomic

UNVERIFIED = (
    "untouched members were not re-verified: this packer checks the edited members only "
    "(doc 18.3); the in-place save keeps the others"
)
MARKER = ".viwo-patched"
CORE_PACK = {"unarchive.zip": "pack.zip"}


@dataclass
class PlanItem:
    container: str  # game-relative; "" for loose files
    slot: str  # "override" or a pack.* slot
    members: dict[str, Path] = field(default_factory=dict)
    untouched: dict[str, str] = field(default_factory=dict)  # member -> original sha256


def _pack_slot(rt, match) -> str:
    if match is None:
        return ""
    owner = rt.slots[match.slot_id].owner
    if owner == "core":
        return CORE_PACK.get(match.slot_id, "")
    plugin = rt.plugins.get(owner)
    return plugin.pack_slot(match.slot_id) if plugin else ""


def plan(rt, game: Path, edits: list[Edit], originals=None) -> tuple[list[PlanItem], list[str]]:
    """originals: container -> {member: sha256} of the extraction, for the untouched check."""
    items, warnings, groups = [], [], defaultdict(dict)
    loose = {e.member: e.file for e in edits if e.kind in ("loose", "added")}
    if loose:
        items.append(PlanItem("", "override", loose))
    for edit in (e for e in edits if e.kind in ("member", "exported")):
        groups[(edit.container, edit.plugin)][edit.member] = edit.file
    for (container, owner), members in sorted(groups.items()):
        if owner:  # exported by a plugin: its packer writes straight into the container
            plugin, match = rt.plugins.get(owner), None
            slot = plugin.pack_slot("exported") if plugin else ""
        else:
            match = identify(game / container, rt.slots.values())
            slot = _pack_slot(rt, match)
        binding = rt.bindings.get(slot)
        if not slot or (match is not None and match.embedded):
            warnings.append(f"{container}: no packer for this container (yet)")
        elif binding is None or not binding.bound:
            warnings.append(f"{container}: {slot} has no available backend (see `viwo slots`)")
        else:
            kept = {
                m: h for m, h in (originals or {}).get(container, {}).items() if m not in members
            }
            items.append(PlanItem(container, slot, members, kept))
    return items, warnings


def source_game(workspace: Path) -> Path:
    """Game folder of the newest extraction run (capture records have no request)."""
    runs = []
    for record in (workspace / ws.RUNS_DIR).glob("*.json"):
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data.get("request"), dict) and data["request"].get("game_path"):
            runs.append((str(data.get("finished", "")), record.name, data["request"]["game_path"]))
    if not runs:
        raise ViwoError("not_found", "no extraction run record: extract into this workspace first")
    return Path(max(runs)[2])


def _reminders(rt, items: list[PlanItem]) -> list[str]:
    """Terms-of-service-sensitive plugins: a reminder, never a refusal (the user is responsible)."""
    owners = {rt.slots[i.slot].owner for i in items if i.slot in rt.slots}
    sensitive = [o for o in owners if o in rt.plugins and rt.plugins[o].manifest.tos_sensitive]
    if sensitive:
        return [f"{', '.join(sensitive)}: own install, offline use; respect the game's terms"]
    return []


def _copy_tree(game: Path, target: Path, say) -> list[str]:
    """Every file of the game as a real file (a link is followed, never recreated, so nothing
    in the copy leads back into the game); returns the files the OS refused to read."""
    ticker = Ticker(say, "Copied game files:")
    skipped: list[str] = []

    def copy(src, dst):
        try:
            shutil.copy2(src, dst)
        except OSError as exc:  # an antivirus hold, a lock, a dangling link
            skipped.append(f"{Path(src).name} ({exc.strerror or exc.errno})")
            with suppress(OSError):  # a read that failed part-way leaves no truncated file
                os.remove(dst)
        ticker.tick()

    shutil.copytree(game, target, symlinks=False, dirs_exist_ok=True, copy_function=copy)
    return skipped


def not_copied(left: list[str]) -> str:
    return f"{len(left)} file(s) not copied (antivirus or lock): {', '.join(left[:5])}"


def prepare_copy(rt, game: Path, target: Path, sink=None, stage="copy", reuse=False) -> list[str]:
    """The patched copy (doc 18): a full copy of the game, marked. With `reuse`, a target that
    already is a patched copy is kept as it is, so patches and mods stack on it. A file the OS
    refuses to read is left out, said in a warn event and returned (callers report it too)."""
    if reuse and (target / MARKER).is_dir():
        return []
    rt.temp_root.mkdir(parents=True, exist_ok=True)
    refuse_writes_inside(game, workspace=target, temp_folder=rt.temp_root)
    tell(sink, f"Copying the game to {target}", stage)
    if target.exists() and any(p.name != ws.METADATA_DIR for p in target.iterdir()):
        if not (target / MARKER).is_dir():
            raise ViwoError("refused", f"{target} is not empty and is not a ViWo patched copy")
        for entry in target.iterdir():  # the lock file (.extraction_metadata) stays
            if entry.name != ws.METADATA_DIR:
                shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    left = _copy_tree(game, target, teller(sink, stage))
    (target / MARKER).mkdir(exist_ok=True)
    if left:
        tell(sink, not_copied(left), stage, "warn")
    return left


def _verify(rt, packed: Path, item: PlanItem, ctx) -> list[str]:
    """Re-extract the packed container (18.3 VERIFY): edited members must carry the edited
    content and every untouched member its original hash; returns the members that do not."""
    match = identify(packed, rt.slots.values())
    if match is None:
        return list(item.members) + list(item.untouched)
    dest = Path(tempfile.mkdtemp(dir=ctx.scratch.parent))
    outcome, _ = run_with_failover(
        rt.bindings[match.slot_id], rt.backends, lambda b: b.extract(packed, dest, ctx)
    )
    expected = {m: sha256(src) for m, src in item.members.items()} | dict(item.untouched)
    bad = [
        m
        for m, digest in expected.items()
        if not outcome.ok or not (dest / m).is_file() or sha256(dest / m) != digest
    ]
    shutil.rmtree(dest, ignore_errors=True)
    return bad


def _override(item: PlanItem, target: Path) -> dict:
    """Loose files copied over; never through a link or outside the patched copy."""
    bad = []
    for member, source in item.members.items():
        dest = ws.member_path(target, member)
        if dest is None:
            bad.append(member)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        if sha256(dest) != sha256(source):
            bad.append(member)
    return {"container": "", "slot": "override", "members": len(item.members), "failed": bad}


def _apply(rt, item: PlanItem, target: Path, ctx) -> dict:
    if item.slot == "override":
        return _override(item, target)
    container = ws.member_path(target, item.container)
    if container is None:  # a link or a crafted path would lead out of the copy
        failed = {"failed": list(item.members), "error": "container is a link or outside the copy"}
        return {"container": item.container, "slot": item.slot, **failed}
    ctx.log(
        f"Packing {item.container} ({item.slot}, {len(item.members)} member(s))", stage="repack"
    )
    outcome, used = run_with_failover(
        rt.bindings[item.slot], rt.backends, lambda b: b.pack(container, item.members, ctx)
    )
    result = {
        "container": item.container,
        "slot": item.slot,
        "backend": used,
        "members": len(item.members),
    }
    if not outcome.ok:
        return {**result, "failed": list(item.members), "error": outcome.error}
    out = rt.backends[used].output_for(container)
    try:  # a packer's own verify must not abort the whole repack
        own = rt.backends[used].verify(out, item.members, ctx)
        # a backend with its own verifier knows its member naming; the generic re-extraction
        # check (edited content + untouched hashes, 18.3) covers every other container
        bad = _verify(rt, out, item, ctx) if own is None else list(own)
        notes = [UNVERIFIED] if own is not None and item.untouched else []
    except Exception as exc:  # noqa: BLE001 (reported per container)
        bad, notes, result["error"] = list(item.members), [], f"verify failed: {exc}"
    state = "verified" if not bad else f"{len(bad)} member(s) FAILED"
    ctx.log(f"Verify {out.name}: {state}", "info" if not bad else "warn", "repack")
    return {
        **result,
        "output": out.relative_to(target).as_posix(),
        "failed": bad,
        "notes": [*outcome.notes, *notes, *([outcome.fallback] if outcome.fallback else [])],
    }


def repack(
    rt, workspace: Path, target: Path | None, sink=None, cancel=None, apply: bool = True
) -> dict:
    """Plan (apply=False) or build a patched copy of the game with the workspace edits."""
    game = source_game(workspace)
    edits, skipped = edit_set(workspace)
    items, warnings = plan(rt, game, edits, original_hashes(workspace))
    warnings = [*warnings, *_reminders(rt, items)]
    report = {
        "game": str(game),
        "target": str(target or ""),
        "edits": len(edits),
        "plan": [
            {"container": i.container, "slot": i.slot, "members": sorted(i.members)} for i in items
        ],
        "skipped": skipped,
        "warnings": warnings,
        "context": record_context(rt),  # effective ini, bindings, tool versions (doc 12.3)
    }
    if not apply or not items:
        return report
    if target is None:
        raise ViwoError("invalid_request", "no target folder for the patched copy")
    with workspace_lock(target):  # two builds into one target cannot interleave
        return _build(rt, game, target, items, report, (sink, cancel or CancelToken()))


def _build(rt, game: Path, target: Path, items: list[PlanItem], report: dict, control) -> dict:
    """control: (progress sink or None, cancel token)."""
    sink, cancel = control
    before = snapshot(game)
    rt.temp_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="viwo-repack-", dir=rt.temp_root))
    try:
        left = prepare_copy(rt, game, target, sink, "repack")
        if left:
            report["warnings"].append(not_copied(left))
        ctx = core_context(rt, "repack", target, work, sink, cancel)
        ctx.staging = work / "out"
        (work / "scratch").mkdir(parents=True, exist_ok=True)
        report["results"] = []
        for item in items:
            if ctx.cancel.cancelled:
                raise ViwoError("cancelled", "repack cancelled; the patched copy is incomplete")
            report["results"].append(_apply(rt, item, target, ctx))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    report["verified"] = all(not r["failed"] for r in report["results"])
    changed = change_warning(before, snapshot(game), "repack")
    if changed:
        report["warnings"].append(changed)
    write_atomic(target / MARKER / "report.json", json.dumps(report, indent=2))
    state = "verified" if report["verified"] else "NOT verified"
    tell(sink, f"Patched copy ready ({state})", "repack")
    return report
