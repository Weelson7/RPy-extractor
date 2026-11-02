"""Stage runner (doc 3.1): prepare, probe, detect, unpack, export, collect, verify, report."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from viwo import __version__
from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.contracts.pipeline import ExtractionRequest, ExtractionResult, PluginRun
from viwo.contracts.plugin import ExtractionContext
from viwo.contracts.types import CancelToken, DetectionResult, ProgressEvent, ProgressSink

from ..workspace import precheck, resolve_target, workspace_lock
from .carving import carve_all
from .collect import collect
from .failover import run_with_failover
from .guard import changes, refuse_writes_inside, snapshot
from .probe import FolderProbe
from .select import select_plugins
from .sources import claimed, sources_for
from .unpack import files_under, unpack_all

SECRET = "<secret>"


@dataclass
class Run:
    rt: object
    request: ExtractionRequest
    job_id: str
    sink: ProgressSink
    cancel: CancelToken
    game: Path
    work: Path
    detections: dict[str, DetectionResult] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)

    def emit(self, event: ProgressEvent) -> None:
        self.logs.append(event.legacy_line())
        self.sink(event)

    def log(self, message: str, stage: str, level: str = "info") -> None:
        self.emit(ProgressEvent(message, level, "core", stage))

    def ctx(self, owner: str) -> ExtractionContext:
        options = {**self.rt.owner_options(owner), **self.request.plugin_options.get(owner, {})}
        detection = self.detections.get(owner) or DetectionResult(owner, 0.0, (), owner)
        return ExtractionContext(
            self.job_id,
            self.game,
            self.work / "staging" / owner,
            self.work / "scratch",
            self.rt.os,
            detection,
            self.request.selected_exts,
            options,
            self.emit,
            self.cancel,
            "core" if owner == "core" else f"plugin:{owner}",
        )


def detect_all(rt, probe: FolderProbe) -> dict[str, DetectionResult]:
    found = {}
    for plugin_id, plugin in rt.plugins.items():
        try:
            found[plugin_id] = plugin.detect(probe)
        except Exception as exc:  # detect must never take the run down
            found[plugin_id] = DetectionResult(
                plugin_id, 0.0, (f"detect failed: {exc}",), plugin_id
            )
    return found


def extract(
    rt,
    request: ExtractionRequest,
    job_id: str,
    sink: ProgressSink,
    cancel: CancelToken,
    default_workspace: Path | None = None,
) -> ExtractionResult:
    game = Path(request.game_path)
    if not request.game_path or not game.is_dir():
        raise ViwoError("invalid_request", f"game folder not found: {request.game_path}")
    target = Path(request.workspace) if request.workspace else default_workspace
    if target is None:
        raise ViwoError("invalid_request", "no workspace given")
    refuse_writes_inside(game, workspace=target, temp_folder=rt.temp_root)
    with workspace_lock(target):
        precheck(target, request.on_existing, default_workspace)  # ask before announcing work
        sink(
            ProgressEvent(
                f"Preparing workspace {target} ({request.on_existing.value})",
                "info",
                "core",
                "prepare",
            )
        )
        workspace = resolve_target(target, request.on_existing, default_workspace)
        rt.temp_root.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=f"viwo-{job_id}-", dir=rt.temp_root))
        try:
            run = Run(rt, request, job_id, sink, cancel, game, work)
            return _stages(run, workspace)
        finally:
            shutil.rmtree(work, ignore_errors=True)


def _select(run: Run) -> tuple[str, ...]:
    rt = run.rt
    run.detections = detect_all(rt, FolderProbe(run.game))
    priorities = {pid: p.manifest.priority for pid, p in rt.plugins.items()}
    chosen = select_plugins(run.request, list(run.detections.values()), priorities)
    run.log(f"Selected plugin(s): {', '.join(chosen)}", "detect")
    return chosen


def _stages(run: Run, workspace: Path) -> ExtractionResult:
    rt = run.rt
    run.log(f"Workspace: {workspace}", "prepare")
    before = snapshot(run.game)
    chosen = _select(run)
    skip = {d.lower() for pid in chosen for d in rt.plugins[pid].skip_dirs()}
    game_files = files_under(run.game, "game", skip)
    unpacked = unpack_all(rt, game_files, run.work / "unpack", run.ctx)
    runs = [_export(run, pid) for pid in chosen]
    carved, unpacked = _carve(run, runs, game_files, unpacked)
    sources = sources_for(run, chosen, {**unpacked.origins, **carved.origins}, runs)
    collected = _decode(
        run, workspace, collect(sources, workspace, run.request.selected_exts, skip, run.cancel)
    )
    if run.cancel.cancelled:
        raise ViwoError("cancelled", "extraction cancelled")
    warnings = _verify(unpacked, collected) + [w for r in runs for w in r.warnings]
    touched = changes(before, snapshot(run.game))
    if touched:  # ViWo never writes there; a running game may (saves, logs)
        warnings.append(f"GAME FOLDER CHANGED during extraction: {', '.join(touched[:10])}")
    warnings += [
        w for pid in chosen for w in rt.plugins[pid].verify(run.ctx(pid), collected.collected)
    ]
    result = ExtractionResult(
        True,
        run.request.mode,
        tuple(runs),
        str(workspace),
        unpacked.found,
        unpacked.extracted,
        collected.scanned,
        collected.collected,
        dict(collected.by_ext),
        dict(unpacked.by_backend),
        tuple(warnings + unpacked.failures + carved.failures),
        tuple(run.logs),
        carved_files=carved.files,
    )
    return _report(run, workspace, result, collected.provenance)


def _decode(run: Run, workspace: Path, collected):
    """Viewable copies of game media (WAV/PNG/MP4) join the collect report."""
    from ..decode import decode_all

    decoded = decode_all(run, workspace, collected.provenance)
    if decoded is not None:
        collected.by_ext.update(decoded.by_ext)
        collected.provenance += decoded.provenance
    return collected


def _carve(run: Run, runs, game_files, unpacked):
    """Carve unknown blobs (game and unpacked), then unpack any archives found inside them.
    Files an exporter decoded are left alone, unless that exporter failed or is missing."""
    items = game_files + [i for d, o in unpacked.origins.items() for i in files_under(d, o, set())]
    carved = carve_all(run, claimed(run, runs), items)
    nested = [i for d, o in carved.origins.items() for i in files_under(d, o, set())]
    if nested:
        more = unpack_all(run.rt, nested, run.work / "unpack-carved", run.ctx)
        unpacked.origins.update(more.origins)
        unpacked.found, unpacked.extracted = (
            unpacked.found + more.found,
            unpacked.extracted + more.extracted,
        )
        unpacked.by_backend.update(more.by_backend)
        unpacked.failures += more.failures
    return carved, unpacked


def _export(run: Run, plugin_id: str) -> PluginRun:
    plugin, detection = run.rt.plugins[plugin_id], run.detections[plugin_id]
    slot_id = plugin.export_slot()
    if not slot_id:
        return PluginRun(plugin_id, detection)
    ctx = run.ctx(plugin_id)
    ctx.staging.mkdir(parents=True, exist_ok=True)
    outcome, used = run_with_failover(
        run.rt.bindings[slot_id], run.rt.backends, lambda backend: backend.export(ctx)
    )
    warnings = () if outcome.ok else (f"{slot_id}: {outcome.kind.value}: {outcome.error}",)
    return PluginRun(plugin_id, detection, outcome.files, used if outcome.ok else "", warnings)


def _verify(unpacked, collected) -> list[str]:
    warnings = []
    if unpacked.found and not unpacked.extracted:
        warnings.append("Archives were discovered but none extracted successfully.")
    if collected.scanned == 0:
        warnings.append("No files were scanned from source roots.")
    if collected.collected == 0:
        warnings.append("No files were copied into the output folder.")
    return warnings


def _masked_options(run: Run) -> dict[str, dict[str, str]]:
    """Plugin option values for replay; secret options are never written to disk."""
    out: dict[str, dict[str, str]] = {}
    for owner, values in run.request.plugin_options.items():
        plugin = run.rt.plugins.get(owner)
        secret = {o.key for o in plugin.manifest.options if o.kind == "secret"} if plugin else set()
        out[owner] = {k: SECRET if k in secret else str(v) for k, v in values.items()}
    return out


def _report(run: Run, workspace: Path, result: ExtractionResult, provenance: list[dict]):
    meta = workspace / ws.METADATA_DIR
    (workspace / ws.RUNS_DIR).mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(p, sort_keys=True) + "\n" for p in provenance)
    (workspace / ws.PROVENANCE_FILE).write_text(lines, encoding="utf-8")
    record_path = workspace / ws.RUNS_DIR / f"{run.job_id}.json"
    record = {
        "job": run.job_id,
        "viwo": __version__,
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "request": {
            "game_path": run.request.game_path,
            "mode": run.request.mode.value,
            "plugins": list(run.request.plugins),
            "mixed_policy": run.request.mixed_policy.value,
            "carve": run.request.carve.value,
            "selected_exts": sorted(run.request.selected_exts)
            if run.request.selected_exts is not None
            else None,
            "options": _masked_options(run),
        },
        "bindings": {sid: [b.main, b.spare] for sid, b in sorted(run.rt.bindings.items())},
        "result": {k: v for k, v in result.to_legacy_dict().items() if k != "logs"},
    }
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    run.log(f"Run record: {record_path.relative_to(workspace)} ({meta.name})", "report")
    return ExtractionResult(
        **{**result.__dict__, "run_record": str(record_path), "logs": tuple(run.logs)}
    )
