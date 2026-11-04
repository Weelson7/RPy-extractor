"""`viwo survey`: read-only coverage report for a game folder or a whole library (D21).

Per game: the engine, and every data file sorted into what would happen to it: a direct
asset, a container with (or without) its tool, decoded by the engine's exporter, code, or
unknown. Unknown blobs get a density estimate: dense data is encrypted or compressed and
needs a key, a decoder or runtime capture; structured data is where the carver can help.
Every step reports its counts as events (scan, identify, probe, carve, decode).
"""

from __future__ import annotations

import os
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.types import CancelToken

from .carve import count_embedded
from .pipeline.carving import CODE, KNOWN, MIN_SIZE
from .pipeline.identify import identify
from .pipeline.probe import FolderProbe
from .pipeline.runner import detect_all
from .steps import Step

COVERED = ("asset", "container", "engine", "carvable")
SAMPLE = 1 << 16


@dataclass
class GameSurvey:
    path: str
    engine: str
    confidence: float
    evidence: tuple[str, ...]
    sizes: dict[str, list[int]] = field(default_factory=dict)  # category -> [files, bytes]
    unknown: list[dict] = field(default_factory=list)  # largest unknown blobs
    missing: set[str] = field(default_factory=set)  # tools that would cover more

    def add(self, category: str, size: int) -> None:
        entry = self.sizes.setdefault(category, [0, 0])
        entry[0], entry[1] = entry[0] + 1, entry[1] + size

    def to_dict(self) -> dict:
        data = sum(b for c, (_, b) in self.sizes.items() if c not in ("code", "small"))
        covered = sum(self.sizes.get(c, [0, 0])[1] for c in COVERED)
        top = sorted(self.unknown, key=lambda u: -u["bytes"])[:8]
        return {
            "path": self.path,
            "engine": self.engine,
            "confidence": round(self.confidence, 2),
            "evidence": list(self.evidence),
            "categories": {c: {"files": f, "bytes": b} for c, (f, b) in sorted(self.sizes.items())},
            "coverage": round(covered / data, 3) if data else 1.0,
            "unknown": top,
            "missingTools": sorted(self.missing),
        }


def dense(path: Path, size: int) -> bool:
    """True when samples from the start and middle barely compress (encrypted/compressed)."""
    with open(path, "rb") as fh:
        sample = fh.read(SAMPLE)
        if size > 2 * SAMPLE:  # a smaller file is read once: the same bytes twice compress well
            fh.seek(size // 2 - SAMPLE // 2)
            sample += fh.read(SAMPLE)
    return len(zlib.compress(sample, 1)) > 0.95 * len(sample)


def _engine(rt, game: Path) -> tuple[str, float, tuple[str, ...]]:
    found = [d for pid, d in detect_all(rt, FolderProbe(game)).items() if pid != "generic"]
    best = max(found, key=lambda d: d.confidence, default=None)
    if best is None or best.confidence < 0.5:
        return "generic", 0.0, ()
    return best.plugin_id, best.confidence, tuple(best.evidence)


def _claimed(rt, report: GameSurvey, engine: str) -> frozenset[str]:
    plugin = rt.plugins.get(engine)
    if plugin is not None and plugin.export_slot():
        binding = rt.bindings.get(plugin.export_slot())
        if binding is not None and binding.bound:
            return frozenset(s.lower() for s in plugin.claimed_suffixes())
        report.missing.add(f"{plugin.export_slot()} exporter (see `viwo slots`)")
    return frozenset()


def _files(game: Path, cancel, sink) -> list[Path]:
    step, out = Step(sink, "scan", "Scanning files:"), []
    for dirpath, dirnames, filenames in os.walk(game):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            out.append(Path(dirpath) / name)
            step.tick(cancel)
    step.done()
    return out


def _sort(rt, report: GameSurvey, path: Path, claimed: frozenset[str]) -> tuple[str, int] | None:
    """Sort one file now; containers (slot id) and unknown blobs ("") come back for later steps."""
    size, ext = path.stat().st_size, path.suffix.lower()
    match = identify(path, rt.slots.values()) if size else None
    if match is not None:
        return match.slot_id, size
    if ext in KNOWN:
        report.add("asset", size)
    elif ext in claimed or path.name.lower() in claimed:
        report.add("engine", size)
    elif ext in CODE:
        report.add("code", size)
    elif size < MIN_SIZE:
        report.add("small", size)
    else:
        return "", size
    return None


def _identify(rt, report: GameSurvey, files: list[Path], claimed, cancel, sink) -> tuple:
    step = Step(sink, "identify", "Identifying files:", len(files))
    containers: list[tuple[Path, str, int]] = []
    blobs: list[tuple[Path, str, int]] = []
    for path in files:
        step.tick(cancel)
        try:
            found = _sort(rt, report, path, claimed)
        except OSError:
            report.add("unreadable", 0)
            continue
        if found is not None:
            (containers if found[0] else blobs).append((path, *found))
    step.done()
    step.tell(f"Identified containers: {len(containers):,}")
    return containers, blobs


def _probe(rt, report: GameSurvey, containers: list, cancel, sink) -> None:
    step = Step(sink, "probe", "Probing archives:", len(containers))
    for _path, slot_id, size in containers:
        step.tick(cancel)
        binding = rt.bindings.get(slot_id)
        if binding is not None and binding.bound:
            report.add("container", size)
        else:
            report.missing.add(f"{slot_id} (see `viwo slots`)")
            report.add("container-no-tool", size)
    if containers:
        step.done()


def _rel(report: GameSurvey, path: Path) -> str:
    """Game-relative path (two Mono config dirs hold files of the same name)."""
    try:
        return path.relative_to(Path(report.path)).as_posix()
    except (ValueError, TypeError, AttributeError):
        return path.name


def _examine(report: GameSurvey, blobs: list, deep: bool, cancel, sink) -> None:
    step = Step(sink, "carve", "Carving unknown blobs:", len(blobs)) if deep else None
    for path, _slot, size in blobs:
        if step is not None:
            step.tick(cancel)
        elif cancel.cancelled:
            raise ViwoError("cancelled", "survey cancelled")
        try:
            if deep and count_embedded(path, cancel):
                report.add("carvable", size)
                continue
            kind = "unknown-dense" if dense(path, size) else "unknown"
        except OSError:
            report.add("unreadable", 0)
            continue
        report.unknown.append(
            {"file": _rel(report, path), "bytes": size, "dense": kind.endswith("dense")}
        )
        report.add(kind, size)
    if step is not None and blobs:
        step.done()


def survey_game(
    rt, game: Path, deep: bool = False, cancel: CancelToken | None = None, sink=None
) -> GameSurvey:
    cancel = cancel or CancelToken()
    engine, confidence, evidence = _engine(rt, game)
    report = GameSurvey(str(game), engine, confidence, evidence)
    claimed = _claimed(rt, report, engine)
    files = _files(game, cancel, sink)
    containers, blobs = _identify(rt, report, files, claimed, cancel, sink)
    _probe(rt, report, containers, cancel, sink)
    _examine(report, blobs, deep, cancel, sink)
    decoders = sum(1 for sid, b in rt.bindings.items() if sid.startswith("decode.") and b.bound)
    Step(sink, "decode", "Decoders available:").tell(f"Decoders available: {decoders}")
    return report


def games_in(root: Path, rt) -> list[Path]:
    """A folder holding only folders is a library (each subfolder a game, like Steam's
    common/); a folder with files of its own is one game."""
    entries = [p for p in root.iterdir() if not p.name.startswith(".")]
    subs = sorted(p for p in entries if p.is_dir())
    if not any(p.is_file() for p in root.rglob("*")):
        return []  # nothing on disk: neither a game nor a library
    return subs if subs and all(p.is_dir() for p in entries) else [root]


def survey(rt, root: Path, deep=False, progress=None, cancel=None, sink=None) -> list[dict]:
    results, games = [], games_in(root, rt)
    for index, game in enumerate(games, 1):
        if cancel is not None and cancel.cancelled:
            raise ViwoError("cancelled", "survey cancelled")
        if progress:
            progress(game, index, len(games))
        results.append(survey_game(rt, game, deep, cancel, sink).to_dict())
    return results
