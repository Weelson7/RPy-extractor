"""EXPORT stage: one export per selected plugin, plus the wrapper re-detection (doc 14.2 #3)."""

from __future__ import annotations

from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.pipeline import PluginRun

from .failover import run_with_failover
from .probe import FolderProbe, detect_all


def kinds(staging: Path) -> dict[str, int]:
    """Exported files per extension (doc 3.5 exportedByKind)."""
    kinds: dict[str, int] = {}
    for file in staging.rglob("*"):
        if file.is_file() and file.name != ws.EXPORT_MAP:
            kind = file.suffix.lower().lstrip(".") or "noext"
            kinds[kind] = kinds.get(kind, 0) + 1
    return kinds


def export_one(run, plugin_id: str, game: Path | None = None) -> PluginRun:
    plugin, detection = run.rt.plugins[plugin_id], run.detections[plugin_id]
    slot_id = plugin.export_slot()
    if not slot_id:
        return PluginRun(plugin_id, detection)
    ctx = run.ctx(plugin_id, game)
    ctx.staging.mkdir(parents=True, exist_ok=True)
    run.log(f"Exporting {plugin.manifest.name} assets ({slot_id})", "export")
    outcome, used = run_with_failover(
        run.rt.bindings[slot_id], run.rt.backends, lambda backend: backend.export(ctx)
    )
    error = "" if outcome.ok else f"{slot_id}: {outcome.kind.value}: {outcome.error}"
    return PluginRun(
        plugin_id,
        detection,
        outcome.files,
        used if outcome.ok else "",
        warnings=(error,) if error else (),
        error=error,
        exported_by_kind=kinds(ctx.staging),
    )


WRAPPERS = {".asar", ".nw"}  # outer wrappers (Electron / NW.js): detection runs once more inside


def rewrap(run, chosen: tuple[str, ...], unpacked) -> list[PluginRun]:
    """Doc 3.1: after an outer wrapper is unpacked, detect once inside it and export the
    strongest engine found there that was not already selected (one pass, never nested)."""
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
        out.append(export_one(run, best.plugin_id, dest))
    return out
