"""`viwo survey`: read-only coverage report for a game folder or a whole library (D21).

Per game: the engine, and every data file sorted into what would happen to it: a direct
asset, a container with (or without) its tool, decoded by the engine's exporter, code, or
unknown. Unknown blobs get a density estimate: dense data is encrypted or compressed and
needs a key, a decoder or runtime capture; structured data is where the carver can help.
"""

from __future__ import annotations

import os
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts.types import CancelToken

from .carve import count_embedded
from .pipeline.carving import CODE, KNOWN, MIN_SIZE
from .pipeline.identify import identify
from .pipeline.probe import FolderProbe
from .pipeline.runner import detect_all

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
        fh.seek(max(0, size // 2 - SAMPLE // 2))
        sample += fh.read(SAMPLE)
    return len(zlib.compress(sample, 1)) > 0.95 * len(sample)


def _engine(rt, game: Path) -> tuple[str, float, tuple[str, ...]]:
    found = [d for pid, d in detect_all(rt, FolderProbe(game)).items() if pid != "generic"]
    best = max(found, key=lambda d: d.confidence, default=None)
    if best is None or best.confidence < 0.5:
        return "generic", 0.0, ()
    return best.plugin_id, best.confidence, tuple(best.evidence)


def _classify(rt, report: GameSurvey, path: Path, claimed: frozenset[str], deep: bool) -> None:
    size, ext = path.stat().st_size, path.suffix.lower()
    match = identify(path, rt.slots.values()) if size else None
    if match is not None:
        binding = rt.bindings.get(match.slot_id)
        if binding is not None and binding.bound:
            return report.add("container", size)
        report.missing.add(f"{match.slot_id} (see `viwo slots`)")
        return report.add("container-no-tool", size)
    if ext in KNOWN:
        return report.add("asset", size)
    if ext in claimed or path.name.lower() in claimed:
        return report.add("engine", size)
    if ext in CODE:
        return report.add("code", size)
    if size < MIN_SIZE:
        return report.add("small", size)
    if deep and count_embedded(path, CancelToken()):
        return report.add("carvable", size)
    kind = "unknown-dense" if dense(path, size) else "unknown"
    report.unknown.append({"file": path.name, "bytes": size, "dense": kind.endswith("dense")})
    report.add(kind, size)


def survey_game(rt, game: Path, deep: bool = False) -> GameSurvey:
    engine, confidence, evidence = _engine(rt, game)
    report = GameSurvey(str(game), engine, confidence, evidence)
    plugin = rt.plugins.get(engine)
    claimed: frozenset[str] = frozenset()
    if plugin is not None and plugin.export_slot():
        binding = rt.bindings.get(plugin.export_slot())
        if binding is not None and binding.bound:
            claimed = frozenset(s.lower() for s in plugin.claimed_suffixes())
        else:
            report.missing.add(f"{plugin.export_slot()} exporter (see `viwo slots`)")
    for dirpath, dirnames, filenames in os.walk(game):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            try:
                _classify(rt, report, Path(dirpath) / name, claimed, deep)
            except OSError:
                report.add("unreadable", 0)
    return report


def games_in(root: Path, rt) -> list[Path]:
    """A folder holding only folders is a library (each subfolder a game, like Steam's
    common/); a folder with files of its own is one game."""
    entries = [p for p in root.iterdir() if not p.name.startswith(".")]
    subs = sorted(p for p in entries if p.is_dir())
    return subs if subs and all(p.is_dir() for p in entries) else [root]


def survey(rt, root: Path, deep: bool = False, progress=None) -> list[dict]:
    results, games = [], games_in(root, rt)
    for index, game in enumerate(games, 1):
        if progress:
            progress(game, index, len(games))
        results.append(survey_game(rt, game, deep).to_dict())
    return results
