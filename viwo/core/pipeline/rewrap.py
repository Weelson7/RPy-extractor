"""Wrapper plugins (doc 14.2 #3): one re-detection after an outer wrapper is unpacked.

Stage runner (doc 3.1): prepare, probe, detect, unpack, export, collect, verify, report."""

from __future__ import annotations

from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.pipeline import PluginRun

from .probe import FolderProbe

SECRET = "<secret>"


def _kinds(staging: Path) -> dict[str, int]:
    """Exported files per extension (doc 3.5 exportedByKind)."""
    kinds: dict[str, int] = {}
    for file in staging.rglob("*"):
        if file.is_file() and file.name != ws.EXPORT_MAP:
            kind = file.suffix.lower().lstrip(".") or "noext"
            kinds[kind] = kinds.get(kind, 0) + 1
    return kinds


WRAPPERS = {".asar", ".nw"}  # outer wrappers (Electron / NW.js): detection runs once more inside


def _rewrap(run, chosen: tuple[str, ...], unpacked) -> list[PluginRun]:
    """Doc 3.1: after an outer wrapper is unpacked, detect once inside it and export the
    strongest engine found there that was not already selected (one pass, never nested)."""
    from .runner import _export, detect_all  # runtime import: the runner imports this module

    rt, out, taken = run.rt, [], set(chosen)
    for dest, origin in list(unpacked.origins.items()):
        if "!" in origin or Path(origin.split(":", 1)[-1]).suffix.lower() not in WRAPPERS:
            continue
        inner = detect_all(rt, FolderProbe(dest))
        best = max(
            (d for pid, d in inner.items() if pid not in taken and pid != "generic"),
            key=lambda d: d.confidence,
            default=None,
        )
        if best is None or best.confidence < run.request.mixed_threshold:
            continue
        run.log(f"Re-detected {best.plugin_id} inside {origin} ({best.confidence:.0%})", "detect")
        run.detections[best.plugin_id] = best
        taken.add(best.plugin_id)
        out.append(_export(run, best.plugin_id, dest))
    return out
