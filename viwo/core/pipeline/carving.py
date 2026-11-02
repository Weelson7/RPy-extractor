"""CARVE (after UNPACK): pull embedded files out of blobs nothing else recognizes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts.pipeline import CarveMode

from .failover import run_with_failover
from .identify import identify

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


@dataclass
class CarveReport:
    scanned: int = 0
    files: int = 0
    origins: dict[Path, str] = field(default_factory=dict)  # carve dir -> origin label
    failures: list[str] = field(default_factory=list)


def wanted(path: Path, mode: CarveMode, claimed: frozenset[str], slots) -> bool:
    """Whether a file is a carving candidate under this mode."""
    ext, name = path.suffix.lower(), path.name.lower()
    if mode is CarveMode.OFF or ext in KNOWN or path.stat().st_size < MIN_SIZE:
        return False
    if mode is CarveMode.UNKNOWN and (ext in CODE or ext in claimed or name in claimed):
        return False
    return identify(path, slots) is None


def carve_all(run, claimed: frozenset[str], items: list[tuple[Path, str]]) -> CarveReport:
    """claimed: suffixes/names decoded by an exporter that succeeded in this run."""
    rt, report = run.rt, CarveReport()
    binding = rt.bindings.get("carve.signatures")
    todo = [(p, o) for p, o in items if wanted(p, run.request.carve, claimed, rt.slots.values())]
    if not todo or binding is None or not binding.bound:
        return report
    ctx = run.ctx("core")
    run.log(f"Carving {len(todo)} unrecognized file(s) for embedded assets", "carve")
    for path, origin in todo:
        if run.cancel.cancelled:
            break
        if path.stat().st_size > BIG:
            run.log(f"Scanning {path.name} ({path.stat().st_size >> 20} MB)", "carve")
        dest = run.work / "carve" / f"{report.scanned:05d}_{uuid.uuid4().hex[:6]}"
        report.scanned += 1
        outcome, used = run_with_failover(
            binding, rt.backends, lambda backend: backend.carve(path, dest, ctx)
        )
        if not outcome.ok:
            report.failures.append(f"carve {origin}: {outcome.kind.value}: {outcome.error}")
        elif outcome.files:
            report.files += outcome.files
            report.origins[dest] = f"carve:{origin}"
            run.log(f"Carved {outcome.files} file(s) from {path.name} via {used}", "carve")
    return report
