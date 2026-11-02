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

MARKER = ".viwo-patched"
CORE_PACK = {"unarchive.zip": "pack.zip"}


@dataclass
class Edit:
    file: Path
    kind: str
    container: str
    member: str
    plugin: str = ""  # owner of "exported" files


@dataclass
class PlanItem:
    container: str  # game-relative; "" for loose files
    slot: str  # "override" or a pack.* slot
    members: dict[str, Path] = field(default_factory=dict)


def edit_set(workspace: Path) -> tuple[list[Edit], list[str]]:
    """Workspace files whose content differs from what extraction wrote."""
    path, edits, skipped, missing = workspace / ws.PROVENANCE_FILE, [], [], []
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    for entry in map(json.loads, lines):
        rel = ws.safe_member(entry["path"])
        file = workspace.joinpath(*rel.parts) if rel else None
        if file is None or not file.is_file():
            missing.append(entry["path"])
            continue
        if sha256(file) == entry["sha256"]:
            continue
        kind = entry.get("kind", "derived")
        if kind in ("loose", "member", "exported"):
            where = (entry.get("container", ""), entry.get("member", ""), entry.get("plugin", ""))
            edits.append(Edit(file, kind, *where))
        else:
            skipped.append(f"{entry['path']}: {kind} file, writing it back is not supported yet")
    if missing:  # renamed, moved or trashed since extraction: their edits cannot be traced
        shown = ", ".join(missing[:5]) + (
            f" and {len(missing) - 5} more" if len(missing) > 5 else ""
        )
        skipped.append(f"{len(missing)} extracted file(s) were moved, renamed or trashed: {shown}")
    return edits, skipped


def _pack_slot(rt, match) -> str:
    if match is None:
        return ""
    owner = rt.slots[match.slot_id].owner
    if owner == "core":
        return CORE_PACK.get(match.slot_id, "")
    plugin = rt.plugins.get(owner)
    return plugin.pack_slot(match.slot_id) if plugin else ""


def plan(rt, game: Path, edits: list[Edit]) -> tuple[list[PlanItem], list[str]]:
    items, warnings, groups = [], [], defaultdict(dict)
    loose = {e.member: e.file for e in edits if e.kind == "loose"}
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
            items.append(PlanItem(container, slot, members))
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


def _policy(rt, items: list[PlanItem]) -> None:
    owners = {rt.slots[i.slot].owner for i in items if i.slot in rt.slots}
    sensitive = [o for o in owners if o in rt.plugins and rt.plugins[o].manifest.tos_sensitive]
    if sensitive:
        raise ViwoError("refused", f"repacking is refused for {', '.join(sensitive)} (policy)")


def _prepare(game: Path, target: Path, temp: Path) -> None:
    refuse_writes_inside(game, workspace=target, temp_folder=temp)
    if target.exists() and any(target.iterdir()):
        if not (target / MARKER).is_dir():
            raise ViwoError("refused", f"{target} is not empty and is not a ViWo patched copy")
        shutil.rmtree(target)
    shutil.copytree(game, target, symlinks=True, dirs_exist_ok=True)  # copies, never links
    (target / MARKER).mkdir(exist_ok=True)


def _ctx(rt, target: Path, work: Path, sink, cancel) -> ExtractionContext:
    detection = DetectionResult("core", 0.0, (), "core")
    return ExtractionContext(
        "repack", target, work / "out", work / "scratch", rt.os, detection, None, {}, sink, cancel
    )


def _verify(rt, packed: Path, members: dict[str, Path], ctx) -> list[str]:
    """Members that do not come back with the edited content after re-extraction."""
    match = identify(packed, rt.slots.values())
    if match is None:
        return list(members)
    dest = Path(tempfile.mkdtemp(dir=ctx.scratch.parent))
    outcome, _ = run_with_failover(
        rt.bindings[match.slot_id], rt.backends, lambda b: b.extract(packed, dest, ctx)
    )
    bad = [
        m
        for m, src in members.items()
        if not outcome.ok or not (dest / m).is_file() or sha256(dest / m) != sha256(src)
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
        bad = rt.backends[used].verify(out, item.members, ctx)
        bad = _verify(rt, out, item.members, ctx) if bad is None else bad
    except Exception as exc:  # noqa: BLE001 (reported per container)
        bad, result["error"] = list(item.members), f"verify failed: {exc}"
    state = "verified" if not bad else f"{len(bad)} member(s) FAILED"
    ctx.log(f"Verify {out.name}: {state}", "info" if not bad else "warn", "repack")
    return {
        **result,
        "output": out.relative_to(target).as_posix(),
        "failed": bad,
        "notes": list(outcome.notes),
    }


def repack(
    rt, workspace: Path, target: Path | None, sink=None, cancel=None, apply: bool = True
) -> dict:
    """Plan (apply=False) or build a patched copy of the game with the workspace edits."""
    game = source_game(workspace)
    edits, skipped = edit_set(workspace)
    items, warnings = plan(rt, game, edits)
    _policy(rt, items)
    report = {
        "game": str(game),
        "target": str(target or ""),
        "edits": len(edits),
        "plan": [
            {"container": i.container, "slot": i.slot, "members": sorted(i.members)} for i in items
        ],
        "skipped": skipped,
        "warnings": warnings,
    }
    if not apply or not items:
        return report
    if target is None:
        raise ViwoError("invalid_request", "no target folder for the patched copy")
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
        _prepare(game, target, rt.temp_root)
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
    (target / MARKER / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    say(
        ProgressEvent(
            f"Patched copy ready ({'verified' if report['verified'] else 'NOT verified'})",
            "info",
            "core",
            "repack",
        )
    )
    return report
