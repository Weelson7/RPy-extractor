"""Asset sanitizer, phase 1 (doc 5): zero-byte files, wrong extensions, exact duplicates,
engine junk, and health checks. Plan first (read-only), then apply only accepted safe
actions; every apply is journaled under .sanitizer/ and can be undone. Nothing lossy.
"""

from __future__ import annotations

import json
import mmap
import shutil
import struct
import time
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

from .carve import SIGNATURES
from .carve import formats2 as g
from .curation import trash
from .pipeline.collect import sha256

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


def _duplicates(files: list[Path], workspace: Path, renames: set[str]) -> list[dict]:
    """Identical files: keep the cleanest copy (no __N suffix, right extension, first path)."""
    by_size: dict[int, list[Path]] = {}
    for path in files:
        by_size.setdefault(path.stat().st_size, []).append(path)
    by_hash: dict[str, list[Path]] = {}
    for path in (p for same in by_size.values() if len(same) > 1 for p in same):
        by_hash.setdefault(sha256(path), []).append(path)
    out = []
    for same in (s for s in by_hash.values() if len(s) > 1):
        rel = {p: p.relative_to(workspace).as_posix() for p in same}
        keep = min(same, key=lambda p: ("__" in p.stem, rel[p] in renames, rel[p]))
        out += [
            _finding("core.duplicate", p, workspace, f"same bytes as {rel[keep]}", "trash")
            for p in same
            if p != keep
        ]
    return out


def plan(workspace: Path) -> dict:
    files = _asset_files(workspace)
    findings = [f for p in files for f in _inspect(p, workspace)]
    flagged = {f["path"] for f in findings if f["action"] == "trash"}
    renames = {f["path"] for f in findings if f["action"] == "rename"}
    dupes = [f for f in _duplicates(files, workspace, renames) if f["path"] not in flagged]
    gone = {f["path"] for f in dupes}
    findings = [f for f in findings if f["path"] not in gone] + dupes
    plan_id = time.strftime("%Y%m%d-%H%M%S")
    result = {"planId": plan_id, "scanned": len(files), "findings": findings}
    folder = workspace / ROOT / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{plan_id}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def _move(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = ws.next_free(dest)
    shutil.move(str(src), str(target))
    return target


def apply(workspace: Path, plan_id: str, accept: list[int] | str = "all-safe") -> dict:
    path = workspace / ROOT / "plans" / f"{plan_id}.json"
    if not path.is_file():
        raise ViwoError("not_found", f"no sanitizer plan {plan_id}")
    findings = json.loads(path.read_text(encoding="utf-8"))["findings"]
    chosen = range(len(findings)) if accept == "all-safe" else [int(i) for i in accept]
    journal, failed = [], []
    for index in chosen:
        finding, src = findings[index], workspace / findings[index]["path"]
        if finding["action"] == "none" or not src.is_file():
            continue
        try:
            dest = (
                trash.area(workspace, "items") / src.name
                if finding["action"] == "trash"
                else src.with_name(finding["to"])
            )
            journal.append([str(_move(src, dest).relative_to(workspace)), finding["path"]])
        except OSError as exc:
            failed.append(f"{finding['path']}: {exc}")
    folder = workspace / ROOT / "journal"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{plan_id}.json").write_text(json.dumps(journal), encoding="utf-8")
    return {"planId": plan_id, "applied": len(journal), "failed": failed, "undoToken": plan_id}


def undo(workspace: Path, token: str) -> dict:
    path = workspace / ROOT / "journal" / f"{token}.json"
    if not path.is_file():
        raise ViwoError("not_found", f"nothing to undo for {token}")
    restored = 0
    for now, before in reversed(json.loads(path.read_text(encoding="utf-8"))):
        if (workspace / now).is_file():
            _move(workspace / now, workspace / before)
            restored += 1
    path.unlink()
    return {"restored": restored}
