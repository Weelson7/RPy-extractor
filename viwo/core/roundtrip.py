"""Round trip (doc 18): edit set -> plan -> patched copy -> encode -> pack -> verify -> report.

The game folder is only read. Edited workspace files are found by hash against the
provenance map; an edited decoded file is encoded back into its member first
(roundtrip_encode); loose files are overridden in the copy, container members go through the
owning plugin's pack.* slot or, as a mod, where the engine loads them over the container
(roundtrip_plan), and every packed container is re-extracted to verify it.
"""

import json
import os
import shutil
import tempfile
from contextlib import suppress
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.contracts.types import CancelToken

from .context import core_context
from .pipeline.collect import sha256
from .pipeline.failover import run_with_failover
from .pipeline.guard import PATCHED, change_warning, guarded, snapshot
from .pipeline.identify import identify
from .pipeline.ticker import Ticker
from .records import record_context
from .roundtrip_edits import edit_set, original_hashes
from .roundtrip_encode import encode_all, ways_back
from .roundtrip_plan import MODES, PlanItem, describe, plan
from .steps import tell, teller
from .workspace import read_json, workspace_lock, write_atomic

UNVERIFIED = (
    "untouched members were not re-verified: this packer checks the edited members only "
    "(doc 18.3); the in-place save keeps the others"
)
MARKER = PATCHED
__all__ = ["MARKER", "PlanItem", "plan", "prepare_copy", "repack"]


def source_game(workspace: Path) -> Path:
    """Game folder of the newest extraction run (capture records have no request)."""
    runs = []
    for record in (workspace / ws.RUNS_DIR).glob("*.json"):
        data = read_json(record, {})  # an unreadable record names no game
        if isinstance(data.get("request"), dict) and data["request"].get("game_path"):
            runs.append((str(data.get("finished", "")), record.name, data["request"]["game_path"]))
    if not runs:
        raise ViwoError("not_found", "no extraction run record: extract into this workspace first")
    return Path(max(runs)[2])


def _reminders(rt, items: list[PlanItem]) -> list[str]:
    """Terms-of-service-sensitive plugins: a reminder, never a refusal (the user is responsible)."""
    owners = {rt.slots[i.slot].owner for i in items if i.slot in rt.slots}
    sensitive = [o for o in owners if o in rt.plugins and rt.plugins[o].manifest.tos_sensitive]
    note = f"{', '.join(sensitive)}: own install, offline use; respect the game's terms"
    return [note] if sensitive else []


def _copy_tree(game: Path, target: Path, say) -> list[str]:
    """Every file of the game as a real file (a file link is followed, never recreated, so
    nothing in the copy leads back into the game; a linked folder or junction is not entered:
    it may lead anywhere, or back to an ancestor); returns what was not copied and why."""
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

    def links(folder, names):
        found = [n for n in names if os.path.isdir(os.path.join(folder, n))]
        found = [n for n in found if ws.link_like(os.path.join(folder, n))]
        skipped.extend(f"{n} (a linked folder, not entered)" for n in found)
        return found

    shutil.copytree(
        game, target, symlinks=False, dirs_exist_ok=True, copy_function=copy, ignore=links
    )
    return skipped


def not_copied(left: list[str]) -> str:
    return f"{len(left)} item(s) not copied: {', '.join(left[:5])}"


def prepare_copy(rt, game: Path, target: Path, sink=None, stage="copy", reuse=False) -> list[str]:
    """The patched copy (doc 18): a full copy of the game, marked. With `reuse`, a target that
    already is a patched copy is kept as it is, so patches and mods stack on it. A file the OS
    refuses to read is left out, said in a warn event and returned (callers report it too).
    The guard runs first, whatever the target's marker: an install a patched copy was copied
    over carries the marker and is still the game."""
    target = guarded(game, target, "patched copy", rt.temp_root)
    if reuse and (target / MARKER).is_dir():
        return []
    rt.temp_root.mkdir(parents=True, exist_ok=True)
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


def _verify(rt, packed: Path, item: PlanItem, ctx, untouched: dict) -> list[str]:
    """Re-extract the packed container (18.3 VERIFY): edited members must carry the edited
    content and every untouched member its original hash; returns the members that do not.
    An override file holds the edits only (`untouched` is empty: the container keeps the rest)."""
    match = identify(packed, rt.slots.values())
    if match is None:
        return list(item.members) + list(untouched)
    dest = Path(tempfile.mkdtemp(dir=ctx.scratch.parent))
    call = lambda b: b.extract(packed, dest, ctx)  # noqa: E731
    binding = rt.bindings[match.slot_id]
    outcome, _ = run_with_failover(binding, rt.backends, call, into=dest, cancel=ctx.cancel)
    expected = {m: sha256(f) for m, f in item.members.items() if f is not None} | dict(untouched)
    back = {original: dest / altered for altered, original in ws.renamed(dest).items()}
    at = lambda m: back.get(m, dest / m)  # noqa: E731  (a renamed member: its altered name)
    bad = [m for m, digest in expected.items() if not at(m).is_file() or sha256(at(m)) != digest]
    bad += [m for m, f in item.members.items() if f is None and at(m).is_file()]  # dropped
    shutil.rmtree(dest, ignore_errors=True)
    return bad if outcome.ok else list(item.members) + list(untouched)


def _override(item: PlanItem, target: Path) -> dict:
    """Loose files copied over; never through a link or outside the patched copy."""
    bad = []
    for member, source in item.members.items():
        dest = ws.member_path(target, member)
        if dest is None:
            bad.append(member)
        elif source is None:  # a replaced file (a stale .rpyc) leaves the copy
            dest.unlink(missing_ok=True)
            bad += [member] if dest.exists() else []
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            bad += [member] if sha256(dest) != sha256(source) else []
    return {"container": "", "slot": "override", "members": len(item.members), "failed": bad}


def _packing(rt, item: PlanItem, container: Path, ctx):
    """One pack attempt per backend. A packer that writes a file of its own beside the
    container (an override, a patch archive) may leave it half-written when it fails: what
    an earlier attempt made there, and was not in the copy before, is removed first."""
    binding = rt.bindings[item.slot]
    outputs = {rt.backends[b].output_for(container) for b in (binding.main, binding.spare) if b}
    made = [out for out in outputs - {container} if not out.exists()]

    def attempt(backend):
        for out in (o for o in made if o.is_file()):
            out.unlink()
        return backend.pack(container, item.members, ctx)

    return attempt


def _apply(rt, item: PlanItem, target: Path, ctx) -> dict:
    if item.slot == "override":
        return _override(item, target)
    container = ws.member_path(target, item.container)
    head = {"container": item.container, "slot": item.slot}
    if container is None:  # a link or a crafted path would lead out of the copy
        failed = {"failed": list(item.members), "error": "container is a link or outside the copy"}
        return {**head, **failed}
    ctx.log(
        f"Packing {item.container} ({item.slot}, {len(item.members)} member(s))", stage="repack"
    )
    outcome, used = run_with_failover(
        rt.bindings[item.slot],
        rt.backends,
        _packing(rt, item, container, ctx),
        into=ctx.staging,
        cancel=ctx.cancel,
    )
    result = {**head, "backend": used, "members": len(item.members)}
    if not outcome.ok:
        return {**result, "failed": list(item.members), "error": outcome.error}
    packer = rt.backends[used]
    out, untouched = packer.output_for(container), {} if packer.override else item.untouched
    try:  # a packer's own verify must not abort the whole repack
        own = packer.verify(out, item.members, ctx)
        # a backend with its own verifier knows its member naming; the generic re-extraction
        # check (edited content + untouched hashes, 18.3) covers every other container
        bad = _verify(rt, out, item, ctx, untouched) if own is None else list(own)
        notes = [UNVERIFIED] if own is not None and untouched else []
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


def repack(rt, workspace: Path, target: Path | None, sink=None, cancel=None, **how) -> dict:
    """Plan (apply=False) or build a patched copy of the game with the workspace edits.
    how: `apply` (default True) and `mode`: "mod" (default: what leaves the game's own files
    untouched, where the engine has it) or "overwrite" (the container rewritten in the copy);
    doc 18.3."""
    apply, mode = how.pop("apply", True), how.pop("mode", "mod")
    if how:
        raise TypeError(f"repack() got unexpected options {sorted(how)}")
    if mode not in MODES:
        raise ViwoError("invalid_request", f"mode must be one of {', '.join(MODES)}: {mode}")
    game = source_game(workspace)
    if apply and target is not None:  # before the lock and the plan, whatever is planned
        target = guarded(game, target, "patched copy", rt.temp_root)
    decoded: list = []
    edits, skipped = edit_set(workspace, decoded)
    back, one_way = ways_back(rt, workspace, decoded)
    items, warnings = plan(rt, game, edits + back, original_hashes(workspace), mode)
    report = {
        "game": str(game),
        "target": str(target or ""),
        "mode": mode,
        "edits": len(edits) + len({e.way.derived for e in back}),
        "plan": describe(items),
        "skipped": skipped + one_way,
        "warnings": [*warnings, *_reminders(rt, items)],
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
        if left := prepare_copy(rt, game, target, sink, "repack"):
            report["warnings"].append(not_copied(left))
        ctx = core_context(rt, "repack", target, work, sink, cancel)
        ctx.staging = work / "out"
        (work / "scratch").mkdir(parents=True, exist_ok=True)
        report["results"] = encode_all(rt, items, work, ctx)  # failures: results of their own
        for item in (i for i in items if i.members):
            if ctx.cancel.cancelled:
                raise ViwoError("cancelled", "repack cancelled; the patched copy is incomplete")
            report["results"].append(_apply(rt, item, target, ctx))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    report["verified"] = all(not r["failed"] for r in report["results"])
    if changed := change_warning(before, snapshot(game), "repack"):
        report["warnings"].append(changed)
    write_atomic(target / MARKER / "report.json", json.dumps(report, indent=2))
    state = "verified" if report["verified"] else "NOT verified"
    tell(sink, f"Patched copy ready ({state})", "repack")
    return report
