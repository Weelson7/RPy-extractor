"""Round trip (doc 18): edit set -> plan -> patched copy -> pack -> verify -> report.

The game folder is only read. Edited workspace files are found by hash against the
provenance map; loose files are overridden in the copy, container members go through the
owning plugin's pack.* slot, and every packed container is re-extracted to verify it.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.contracts.plugin import ExtractionContext
from viwo.contracts.types import CancelToken, DetectionResult, ProgressEvent

from .pipeline.collect import sha256
from .pipeline.failover import run_with_failover
from .pipeline.guard import changes, refuse_writes_inside, snapshot
from .pipeline.identify import identify
from .pipeline.ticker import Ticker
from .records import record_context
from .roundtrip_edits import Edit, edit_set, original_hashes
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


def _prepare(game: Path, target: Path, temp: Path, say=None) -> None:
    refuse_writes_inside(game, workspace=target, temp_folder=temp)
    ticker = Ticker(say, "Copied game files:")

    def copy(src, dst):  # copies (never links), with a throttled count for the progress rail
        shutil.copy2(src, dst)
        ticker.tick()

    if target.exists() and any(p.name != ws.METADATA_DIR for p in target.iterdir()):
        if not (target / MARKER).is_dir():
            raise ViwoError("refused", f"{target} is not empty and is not a ViWo patched copy")
        for entry in target.iterdir():  # the lock file (.extraction_metadata) stays
            if entry.name != ws.METADATA_DIR:
                shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    shutil.copytree(game, target, symlinks=True, dirs_exist_ok=True, copy_function=copy)
    (target / MARKER).mkdir(exist_ok=True)


def _ctx(rt, target: Path, work: Path, sink, cancel) -> ExtractionContext:
    detection = DetectionResult("core", 0.0, (), "core")
    return ExtractionContext(
        "repack", target, work / "out", work / "scratch", rt.os, detection, None, {}, sink, cancel
    )


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
        rel = ws.safe_member(member)
        dest = target.joinpath(*rel.parts) if rel else None
        if dest is None or not ws.inside(target, dest.parent) or dest.is_symlink():
            bad.append(member)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        if sha256(dest) != sha256(source):
            bad.append(member)
    return {"container": "", "slot": "override", "members": len(item.members), "failed": bad}


def _container(target: Path, rel: str) -> Path | None:
    member = ws.safe_member(rel)
    path = target.joinpath(*member.parts) if member else None
    return path if path is not None and ws.inside(target, path) else None


def _apply(rt, item: PlanItem, target: Path, ctx) -> dict:
    if item.slot == "override":
        return _override(item, target)
    container = _container(target, item.container)
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
        "notes": [*outcome.notes, *notes],
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
    say = sink or (lambda e: None)
    before = snapshot(game)
    rt.temp_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="viwo-repack-", dir=rt.temp_root))
    try:
        say(ProgressEvent(f"Copying the game to {target}", "info", "core", "repack"))
        _prepare(
            game, target, rt.temp_root, lambda m: say(ProgressEvent(m, "info", "core", "repack"))
        )
        ctx = _ctx(rt, target, work, sink, cancel)
        (work / "scratch").mkdir(parents=True, exist_ok=True)
        report["results"] = []
        for item in items:
            if ctx.cancel.cancelled:
                raise ViwoError("cancelled", "repack cancelled; the patched copy is incomplete")
            report["results"].append(_apply(rt, item, target, ctx))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    report["verified"] = all(not r["failed"] for r in report["results"])
    touched = changes(before, snapshot(game))
    if touched:
        report["warnings"].append(f"GAME FOLDER CHANGED during repack: {', '.join(touched[:10])}")
    write_atomic(target / MARKER / "report.json", json.dumps(report, indent=2))
    say(
        ProgressEvent(
            f"Patched copy ready ({'verified' if report['verified'] else 'NOT verified'})",
            "info",
            "core",
            "repack",
        )
    )
    return report
