"""CARVE (after UNPACK): pull embedded files out of blobs nothing else recognizes."""

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts.pipeline import CarveMode

from .failover import run_with_failover
from .identify import identify
from .pool import each, workers
from .ticker import Ticker

KNOWN = frozenset(
    ".png .jpg .jpeg .gif .bmp .tga .webp .dds .ktx .ktx2 .ogg .opus .wav .wem .mp3 .flac .m4a "
    ".aac .mid .midi .mus .mp4 .webm .mkv .avi .mov .ogv .bik .bk2 .usm .fsb .bnk .txt .json "
    ".xml .ini .cfg .csv .yaml .yml .md .html .htm .css .js .ts .lua .py .rpy .rpym .cs .shader "
    ".glsl .hlsl .gd .tscn .tres .log .ttf .otf .woff .woff2 .fnt .svg .pdf .glb .gltf .obj .fbx "
    ".mtl .lmp".split()
)
CODE = frozenset(
    ".exe .dll .so .dylib .pyd .pyc .pyo .rpyc .class .node .sys .msi .bat .cmd .sh".split()
)
MIN_SIZE = 1024
BIG = 100 << 20
SAID_FROM = 200  # files from which the check for carving candidates is announced


@dataclass
class CarveReport:
    scanned: int = 0
    files: int = 0
    origins: dict[Path, str] = field(default_factory=dict)  # carve dir -> origin label
    failures: list[str] = field(default_factory=list)


def _size(path: Path) -> int | None:
    """None when the file is gone or held (an antivirus): not a candidate; the collect step
    and the game-folder guard name it."""
    try:
        return path.stat().st_size
    except OSError:
        return None


def wanted(path: Path, mode: CarveMode, claimed: frozenset[str], slots) -> bool:
    """Whether a file is a carving candidate under this mode."""
    ext, name = path.suffix.lower(), path.name.lower()
    size = _size(path)
    if mode is CarveMode.OFF or ext in KNOWN or size is None or size < MIN_SIZE:
        return False
    if mode is CarveMode.UNKNOWN and (ext in CODE or ext in claimed or name in claimed):
        return False
    return identify(path, slots) is None


def carve_all(run, claimed: frozenset[str], items: list[tuple[Path, str]]) -> CarveReport:
    """claimed: suffixes/names decoded by an exporter that succeeded in this run."""
    rt, report = run.rt, CarveReport()
    binding = rt.bindings.get("carve.signatures")
    if run.request.carve is CarveMode.OFF or binding is None or not binding.bound:
        return report
    say, slots = (lambda m: run.log(m, "carve")), list(rt.slots.values())
    if len(items) >= SAID_FROM:  # each file is opened: minutes on a large game, so it is said
        say(f"Looking through {len(items):,} file(s) for ones nothing recognizes")
    ticker = Ticker(say, "Checked files:", len(items))
    check = lambda item: wanted(item[0], run.request.carve, claimed, slots)  # noqa: E731
    keep = [ticker.tick() or yes for yes in each(check, items, run.cancel)]
    todo = [item for item, yes in zip(items, keep) if yes]
    if not todo:
        return report
    ctx = run.ctx("core")
    say(f"Carving {len(todo)} unrecognized file(s) for embedded assets on {workers()} workers")
    ticker = Ticker(say, "Carve-scanned files:", len(todo))
    jobs = [  # numbered in the files' order, so the folders are the same on every run
        (path, origin, run.work / "carve" / f"{i:05d}_{uuid.uuid4().hex[:6]}")
        for i, (path, origin) in enumerate(todo)
    ]

    def one(job):
        if (_size(job[0]) or 0) > BIG:
            say(f"Scanning {job[0].name} ({(_size(job[0]) or 0) >> 20} MB)")
        return run_with_failover(binding, rt.backends, lambda b: b.carve(job[0], job[2], ctx))

    for (path, origin, dest), (outcome, used) in zip(jobs, each(one, jobs, run.cancel)):
        ticker.tick(note=f"{report.files:,} embedded file(s) found")
        report.scanned += 1
        if outcome.fallback:
            run.log(f"{path.name}: {outcome.fallback}", "carve", "warn")
        if not outcome.ok:
            report.failures.append(f"carve {origin}: {outcome.kind.value}: {outcome.error}")
        elif outcome.files:
            report.files += outcome.files
            report.origins[dest] = f"carve:{origin}"
            run.log(f"Carved {outcome.files} file(s) from {path.name} via {used}", "carve")
    return report
