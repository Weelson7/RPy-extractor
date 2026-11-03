"""COLLECT (doc 3.1): copy from the game folder, move from staging, dedupe, provenance."""

from __future__ import annotations

import hashlib
import os
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts import workspace as ws

from .ticker import Ticker

SKIP_DIRS = {".git", ".venv", "__pycache__"}


@dataclass
class Source:
    root: Path
    move: bool  # False: copy (game folder is read-only); True: move (staging)
    origin: str  # label prefix for provenance
    exclude: frozenset[str] = frozenset()  # suffixes / names already decoded by an exporter
    kind: str = "derived"  # loose | member | export | derived (round trip, doc 18)
    container: str = ""  # game-relative container of "member" files
    prefix: str = ""  # game-relative root of "loose" files
    mapped: dict = field(default_factory=dict)  # export rel -> [container, member, plugin]


@dataclass
class CollectReport:
    scanned: int = 0
    by_ext: Counter = field(default_factory=Counter)
    skipped_by_ext: Counter = field(default_factory=Counter)
    provenance: list[dict] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)  # the OS refused them (antivirus, lock)

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
            if name not in (ws.MARKER, ws.EXPORT_MAP, *ws.LEGACY_MARKERS) and not os.path.islink(
                here / name
            ):  # links are never followed: they could point outside the game
                yield here / name


def _place(src: Path, folder: Path, digest: str) -> tuple[Path, bool]:
    """(target path, True when an identical file (size + hash) is already there)."""
    candidate = folder / src.name
    index = 1
    while candidate.exists():
        if candidate.stat().st_size == src.stat().st_size and sha256(candidate) == digest:
            return candidate, True
        candidate = folder / ws.COLLISION.format(stem=src.stem, index=index, suffix=src.suffix)
        index += 1
    return candidate, False


def collect(
    sources: list[Source],
    workspace: Path,
    selected: frozenset[str] | None,
    skip: set[str],
    cancel,
    say=None,
) -> CollectReport:
    """say(message), when given, receives a throttled 'Collected N files' progress line."""
    report = CollectReport()
    avoid = workspace.resolve()
    todo = []  # counted first, so the progress bar has a real total
    for source in sources:
        for src in _walk(source.root, SKIP_DIRS | skip, avoid):
            if cancel.cancelled:
                return report
            todo.append((source, src))
    if say is not None:
        say(f"Collecting {len(todo):,} files from {len(sources)} source folder(s)")
    ticker = Ticker(say, "Scanned files:", total=len(todo))
    for source, src in todo:
        if cancel.cancelled:
            return report
        report.scanned += 1
        ticker.tick(note=f"{report.collected:,} collected")
        if src.suffix.lower() in source.exclude or src.name.lower() in source.exclude:
            continue
        ext = ws.ext_of(src)
        group = ws.ext_folder(ext)
        if selected is not None and ext not in selected:
            report.skipped_by_ext[group] += 1
            continue
        try:
            digest = sha256(src)  # where an antivirus hold or a lock on the source surfaces
        except OSError as exc:  # a warning, not a crash; workspace errors below still raise
            report.unreadable.append(f"{src.name} ({exc.strerror or exc.errno})")
            continue
        _collect_one(src, digest, workspace / group, source, report)
    return report


def _where(source: Source, rel: str) -> dict:
    """Round-trip fields: what kind of file this is and where it would be written back."""
    if rel in source.mapped:
        container, member, plugin = source.mapped[rel]
        return {"kind": "exported", "container": container, "member": member, "plugin": plugin}
    member = f"{source.prefix}/{rel}".lstrip("/") if source.kind == "loose" else rel
    return {"kind": source.kind, "container": source.container, "member": member}


def _collect_one(src: Path, digest: str, folder: Path, source: Source, report) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    target, duplicate = _place(src, folder, digest)
    if not duplicate:
        (shutil.move if source.move else shutil.copy2)(str(src), str(target))
        report.by_ext[folder.name] += 1
    rel = src.relative_to(source.root).as_posix()  # duplicates still get provenance (round trip)
    report.provenance.append(
        {
            "path": f"{folder.name}/{target.name}",
            "origin": f"{source.origin}:{rel}",
            "sha256": digest,
            "size": target.stat().st_size,
            **_where(source, rel),
        }
    )
