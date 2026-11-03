"""Asset sanitizer, phase 1 (doc 5): zero-byte files, wrong extensions, exact duplicates,
engine junk, and health checks. Plan first (read-only), then apply only accepted safe
actions; every apply is journaled under .sanitizer/ and can be undone. Nothing lossy.
"""

from __future__ import annotations

import json
import mmap
import re
import shutil
import struct
import time
import uuid
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

from . import provenance
from .carve import SIGNATURES
from .carve import formats2 as g
from .curation import trash
from .pipeline.collect import sha256
from .steps import Step
from .workspace import write_atomic

ROOT = ".sanitizer"
JUNK = {".import", ".meta", ".tmp", ".bak"}
JUNK_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
SAME = {".jpeg": ".jpg", ".midi": ".mid", ".tif": ".tiff"}
NEEDLE_EXT = {
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
    b"GIF8": ".gif",
    b"OggS": ".ogg",
}
NEEDLE_EXT |= {b"MThd": ".mid", b"DDS |": ".dds", b"glTF": ".glb", b"7z\xbc\xaf\x27\x1c": ".7z"}


def sniff(path: Path) -> tuple[str, int] | None:
    """(suffix, size) of the format this file starts with, from the carver's sizers;
    size -1 when the file starts with a signature but its structure does not walk."""
    size = path.stat().st_size
    if size < 16:
        return None
    with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
        for needle, delta, sizer in SIGNATURES:
            if m[-delta : -delta + len(needle)] != needle:  # needle sits at -delta in the file
                continue
            try:
                found = sizer(m, 0, size, {}) if sizer is g.zip_file else sizer(m, 0, size)
            except (IndexError, ValueError, OverflowError, struct.error):
                found = None
            if found:
                return found[1], found[0]
            if path.suffix.lower() == NEEDLE_EXT.get(needle):
                return path.suffix.lower(), -1
    return None


def _asset_files(workspace: Path) -> list[Path]:
    return [
        p
        for group in sorted(workspace.iterdir())
        if group.is_dir() and not ws.is_reserved(group.name)
        for p in sorted(group.rglob("*"))
        if p.is_file()
    ]


def _finding(rule: str, path: Path, workspace: Path, message: str, action: str, **extra) -> dict:
    rel = path.relative_to(workspace).as_posix()
    return {"rule": rule, "path": rel, "message": message, "action": action, **extra}


def _inspect(path: Path, workspace: Path) -> list[dict]:
    ext, size, name = path.suffix.lower(), path.stat().st_size, path.name.lower()
    if size == 0:
        return [_finding("core.zero_byte", path, workspace, "empty file", "trash")]
    if ext in JUNK or name in JUNK_NAMES:
        return [_finding("core.junk", path, workspace, f"engine/OS junk ({ext or name})", "trash")]
    found = sniff(path)
    if found is None:
        return []
    real, length = found
    if length != size:
        what = "truncated or corrupt" if length < 0 else f"{size - length} bytes of trailing data"
        return [_finding("core.health", path, workspace, f"{real[1:]} {what}", "none")]
    if SAME.get(ext, ext) != real and not (ext == ".wav" and real == ".wem"):
        new = path.with_suffix(real).name
        return [_finding("core.extension", path, workspace, f"is really {real}", "rename", to=new)]
    return []


def _duplicates(
    files: list[Path], workspace: Path, renames: set[str], flagged: set[str], sink=None, cancel=None
) -> list[dict]:
    """Identical files: keep the cleanest copy (no __N suffix, right extension, first path)."""
    by_size: dict[int, list[Path]] = {}
    for path in files:
        by_size.setdefault(path.stat().st_size, []).append(path)
    todo = [p for same in by_size.values() if len(same) > 1 for p in same]
    step, by_hash = Step(sink, "hash", "Hashing files:", len(todo)), {}
    for path in todo:
        step.tick(cancel)
        by_hash.setdefault(sha256(path), []).append(path)
    if todo:
        step.done()
    out = []
    for same in (s for s in by_hash.values() if len(s) > 1):
        rel = {p: p.relative_to(workspace).as_posix() for p in same}
        candidates = [p for p in same if rel[p] not in flagged]  # never trash the last copy
        if len(candidates) < 2:
            continue
        keep = min(candidates, key=lambda p: ("__" in p.stem, rel[p] in renames, rel[p]))
        out += [
            _finding("core.duplicate", p, workspace, f"same bytes as {rel[keep]}", "trash")
            for p in candidates
            if p != keep
        ]
    return out


def plan(workspace: Path, sink=None, cancel=None) -> dict:
    files, findings = _asset_files(workspace), []
    step = Step(sink, "scan", "Scanning files:", len(files))
    for path in files:
        step.tick(cancel)
        findings += _inspect(path, workspace)
    step.done()
    flagged = {f["path"] for f in findings if f["action"] == "trash"}
    renames = {f["path"] for f in findings if f["action"] == "rename"}
    dupes = _duplicates(files, workspace, renames, flagged, sink, cancel)
    gone = {f["path"] for f in dupes}
    findings = [f for f in findings if f["path"] not in gone] + dupes
    for finding in findings:  # remembered so that a stale plan is never applied
        file = workspace.joinpath(*Path(finding["path"]).parts)
        finding["size"] = file.stat().st_size if file.is_file() else -1
    plan_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    result = {"planId": plan_id, "scanned": len(files), "findings": findings}
    folder = workspace / ROOT / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    write_atomic(folder / f"{plan_id}.json", json.dumps(result, indent=1))
    return result


def _move(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = ws.next_free(dest)
    shutil.move(str(src), str(target))
    return target


PLAN_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


def _plan_id(value) -> str:
    if not PLAN_ID.match(str(value)):
        raise ViwoError("invalid_request", f"not a sanitizer plan id: {value!r}")
    return str(value)


def _ws_file(workspace: Path, rel) -> Path | None:
    """A path read back from a plan or journal, only if it stays inside the workspace."""
    member = ws.safe_member(str(rel))
    path = workspace.joinpath(*member.parts) if member else None
    return path if path is not None and ws.inside(workspace, path) else None


def _act(workspace: Path, finding: dict) -> str:
    """Carry out one finding; returns where the file went (workspace-relative)."""
    src = _ws_file(workspace, finding["path"])
    if src is None or not src.is_file():
        raise OSError("file is gone or outside the workspace")
    if finding["action"] == "trash":
        dest = trash.area(workspace, "items").joinpath(*Path(finding["path"]).parts)
    else:
        name = ws.safe_member(str(finding.get("to", "")))
        if name is None or len(name.parts) != 1:
            raise OSError("bad new name")
        dest = src.with_name(name.name)
    return _move(src, dest).relative_to(workspace).as_posix()


def _chosen(workspace: Path, findings: list[dict], accept) -> list[dict]:
    """The accepted findings of a plan, refused when a file changed since the scan."""
    try:
        picked = range(len(findings)) if accept == "all-safe" else sorted({int(i) for i in accept})
    except (TypeError, ValueError):
        raise ViwoError("invalid_request", "accept must be 'all-safe' or a list of indexes")
    chosen = [findings[i] for i in picked if 0 <= i < len(findings)]
    for finding in chosen:
        file = _ws_file(workspace, finding["path"])
        if "size" in finding and file and file.is_file() and file.stat().st_size != finding["size"]:
            raise ViwoError(
                "invalid_request", f"plan is stale: {finding['path']} changed; scan again"
            )
    return chosen


def apply(workspace: Path, plan_id: str, accept="all-safe", sink=None, cancel=None) -> dict:
    plan_id = _plan_id(plan_id)
    path = workspace / ROOT / "plans" / f"{plan_id}.json"
    if not path.is_file():
        raise ViwoError("not_found", f"no sanitizer plan {plan_id}")
    chosen = _chosen(workspace, json.loads(path.read_text(encoding="utf-8"))["findings"], accept)
    journal, failed = [], []
    step = Step(sink, "apply", "Applying actions:", len(chosen))
    for finding in chosen:
        step.tick(cancel)
        if finding["action"] in ("trash", "rename"):
            try:
                journal.append([_act(workspace, finding), finding["path"]])
            except OSError as exc:
                failed.append(f"{finding['path']}: {exc}")
    if chosen:
        step.done()
    folder = workspace / ROOT / "journal"
    folder.mkdir(parents=True, exist_ok=True)
    record = folder / f"{plan_id}.json"  # several applies of one plan add up
    earlier = json.loads(record.read_text(encoding="utf-8")) if record.is_file() else []
    write_atomic(record, json.dumps(earlier + journal))
    provenance.rewrite(workspace, {before: now for now, before in journal})
    moved = [{"from": before, "to": now} for now, before in journal]
    return {
        "planId": plan_id,
        "applied": len(journal),
        "moved": moved,
        "failed": failed,
        "undoToken": plan_id,
    }


def undo(workspace: Path, token: str, sink=None, cancel=None) -> dict:
    path = workspace / ROOT / "journal" / f"{_plan_id(token)}.json"
    if not path.is_file():
        raise ViwoError("not_found", f"nothing to undo for {token}")
    restored, back = 0, {}
    entries = json.loads(path.read_text(encoding="utf-8"))
    step = Step(sink, "undo", "Undoing actions:", len(entries))
    for now, before in reversed(entries):
        step.tick(cancel)
        src, dest = _ws_file(workspace, now), _ws_file(workspace, before)
        if src is not None and dest is not None and src.is_file():
            back[now] = _move(src, dest).relative_to(workspace).as_posix()
            restored += 1
    if entries:
        step.done()
    provenance.rewrite(workspace, back)
    path.unlink()
    return {"restored": restored}
