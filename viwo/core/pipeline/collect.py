"""COLLECT (doc 3.1): copy from the game folder, move from staging, dedupe, provenance."""

from __future__ import annotations

import hashlib
import os
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts import workspace as ws

SKIP_DIRS = {".git", ".venv", "__pycache__"}


@dataclass
class Source:
    root: Path
    move: bool  # False: copy (game folder is read-only); True: move (staging)
    origin: str  # label prefix for provenance


@dataclass
class CollectReport:
    scanned: int = 0
    by_ext: Counter = field(default_factory=Counter)
    skipped_by_ext: Counter = field(default_factory=Counter)
    provenance: list[dict] = field(default_factory=list)

    @property
    def collected(self) -> int:
        return sum(self.by_ext.values())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _walk(root: Path, skip: set[str], avoid: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if d not in skip and (here / d).resolve() != avoid)
        for name in sorted(filenames):
            if name not in (ws.MARKER, *ws.LEGACY_MARKERS):
                yield here / name


def _place(src: Path, folder: Path, digest: str) -> Path | None:
    """Target path, or None when an identical file (size + hash) is already there."""
    candidate = folder / src.name
    index = 1
    while candidate.exists():
        if candidate.stat().st_size == src.stat().st_size and sha256(candidate) == digest:
            return None
        candidate = folder / ws.COLLISION.format(stem=src.stem, index=index, suffix=src.suffix)
        index += 1
    return candidate


def collect(
    sources: list[Source], workspace: Path, selected: frozenset[str] | None, skip: set[str], cancel
) -> CollectReport:
    report = CollectReport()
    avoid = workspace.resolve()
    for source in sources:
        for src in _walk(source.root, SKIP_DIRS | skip, avoid):
            if cancel.cancelled:
                return report
            report.scanned += 1
            ext = ws.ext_of(src)
            group = ws.ext_folder(ext)
            if selected is not None and ext not in selected:
                report.skipped_by_ext[group] += 1
                continue
            _collect_one(src, workspace / group, source, report)
    return report


def _collect_one(src: Path, folder: Path, source: Source, report: CollectReport) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    digest = sha256(src)
    target = _place(src, folder, digest)
    if target is None:
        return
    (shutil.move if source.move else shutil.copy2)(str(src), str(target))
    report.by_ext[folder.name] += 1
    rel = src.relative_to(source.root).as_posix()
    report.provenance.append(
        {
            "path": f"{folder.name}/{target.name}",
            "origin": f"{source.origin}:{rel}",
            "sha256": digest,
            "size": target.stat().st_size,
        }
    )
