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

from ..workspace import resolve_target, workspace_lock
from .collect import Source, collect
from .failover import run_with_failover
from .probe import FolderProbe
from .select import select_plugins
from .unpack import files_under, unpack_all


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
    with workspace_lock(target):
        workspace = resolve_target(target, request.on_existing, default_workspace)
        rt.temp_root.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=f"viwo-{job_id}-", dir=rt.temp_root))
        try:
            run = Run(rt, request, job_id, sink, cancel, game, work)
            return _stages(run, workspace)
        finally:
            shutil.rmtree(work, ignore_errors=True)


def _stages(run: Run, workspace: Path) -> ExtractionResult:
    rt = run.rt
    run.log(f"Workspace: {workspace}", "prepare")
    run.detections = detect_all(rt, FolderProbe(run.game))
    priorities = {pid: p.manifest.priority for pid, p in rt.plugins.items()}
    chosen = select_plugins(run.request, list(run.detections.values()), priorities)
    run.log(f"Selected plugin(s): {', '.join(chosen)}", "detect")
    skip = {d.lower() for pid in chosen for d in rt.plugins[pid].skip_dirs()}
    items = files_under(run.game, "game", skip)
    unpacked = unpack_all(rt, items, run.work / "unpack", run.ctx)
    runs = [_export(run, pid) for pid in chosen]
    sources = _game_sources(run, chosen)
    sources += [Source(d, True, label) for d, label in unpacked.origins.items()]
    sources += [
        Source(run.work / "staging" / r.plugin_id, True, f"export:{r.backend}")
        for r in runs
        if r.backend
    ]
    collected = collect(sources, workspace, run.request.selected_exts, skip, run.cancel)
    if run.cancel.cancelled:
        raise ViwoError("cancelled", "extraction cancelled")
    warnings = _verify(unpacked, collected) + [w for r in runs for w in r.warnings]
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
        tuple(warnings + unpacked.failures),
        tuple(run.logs),
    )
    return _report(run, workspace, result, collected.provenance)


def _game_sources(run: Run, chosen: tuple[str, ...]) -> list[Source]:
    probe = FolderProbe(run.game, limit=1)
    roots = {
        r.resolve() for pid in chosen for r in run.rt.plugins[pid].source_roots(run.game, probe)
    }
    outer = [r for r in roots if not any(o != r and o in r.parents for o in roots)]
    labels = {r: r.relative_to(run.game.resolve()).as_posix() for r in outer}
    return [
        Source(r, False, "game" if labels[r] == "." else f"game:{labels[r]}") for r in sorted(outer)
    ]


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
            "selected_exts": sorted(run.request.selected_exts or []),
            "option_keys": {k: sorted(v) for k, v in run.request.plugin_options.items()},
        },
        "bindings": {sid: [b.main, b.spare] for sid, b in sorted(run.rt.bindings.items())},
        "result": {k: v for k, v in result.to_legacy_dict().items() if k != "logs"},
    }
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    run.log(f"Run record: {record_path.relative_to(workspace)} ({meta.name})", "report")
    return ExtractionResult(
        **{**result.__dict__, "run_record": str(record_path), "logs": tuple(run.logs)}
    )
