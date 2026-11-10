"""Stage runner (doc 3.1): prepare, probe, detect, unpack, export, collect, verify, report."""

import json
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from viwo import __version__
from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.contracts.pipeline import ExtractionRequest, ExtractionResult
from viwo.contracts.plugin import ExtractionContext
from viwo.contracts.types import CancelToken, DetectionResult, ProgressEvent, ProgressSink

from ..context import core_context, for_owner
from ..records import record_context
from ..scan_exclusions import excluded
from ..steps import tell
from ..workspace import precheck, resolve_target, workspace_lock, write_atomic
from .carving import carve_all
from .checks import _verify, verified
from .collect import collect
from .export import export_one, rewrap
from .filters import prune, widened
from .guard import change_warning, refuse_writes_inside, snapshot
from .probe import FolderProbe, detect_all
from .select import select_plugins, with_games
from .sources import claimed, sources_for
from .ticker import clock
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
    probe: FolderProbe | None = None  # the shared index (doc 2.3), built once by DETECT
    chosen: tuple[str, ...] = ()  # the plugins selected for this game
    took: dict[str, float] = field(default_factory=dict)  # stage -> seconds spent in it
    at: list = field(default_factory=lambda: ["", time.monotonic(), threading.Lock()])

    def emit(self, event: ProgressEvent) -> None:
        for line in (*self._turn(event.stage), event):
            self.logs.append(line.legacy_line())
            self.sink(line)

    def _turn(self, stage: str) -> tuple[ProgressEvent, ...]:
        """Never silent about time: when the work moves to another stage, the one it leaves
        says how long it took (stages of a second or more); the totals close the run."""
        with self.at[2]:
            last, since, now = self.at[0], self.at[1], time.monotonic()
            if not stage or stage == last:
                return ()
            self.at[:2] = [stage, now]
            self.took[last] = self.took.get(last, 0.0) + now - since
        if not last or now - since < 1:
            return ()
        return (ProgressEvent(f"{last} took {clock(now - since)}", "info", "core", last),)

    def log(self, message: str, stage: str, level: str = "info") -> None:
        self.emit(ProgressEvent(message, level, "core", stage))

    def ctx(self, owner: str, game: Path | None = None) -> ExtractionContext:
        root = game or self.game
        base = core_context(self.rt, self.job_id, root, self.work, self.emit, self.cancel)
        found = {"detection": self.detections[owner]} if owner in self.detections else {}
        options = self.request.plugin_options.get(owner, {})
        probe = self.probe if game is None else None
        extra = {"selected_exts": self.request.selected_exts, "probe": probe, **found}
        extra["workspace"] = Path(self.request.workspace) if self.request.workspace else None
        mine = [self.rt.plugins[g] for g in self.chosen]
        extra["games"] = tuple(p for p in mine if p.manifest.engine == owner)
        return for_owner(base, self.rt, owner, options, **extra)


def extract(
    rt,
    request: ExtractionRequest,
    job_id: str,
    sink: ProgressSink,
    cancel: CancelToken,
    default_workspace: Path | None = None,
) -> ExtractionResult:
    from ..context import require

    require(rt, "extraction", "extraction")
    game = Path(request.game_path)
    if not request.game_path or not game.is_dir():
        raise ViwoError("invalid_request", f"game folder not found: {request.game_path}")
    target = Path(request.workspace) if request.workspace else default_workspace
    if target is None:
        raise ViwoError("invalid_request", "no workspace given")
    refuse_writes_inside(game, workspace=target, temp_folder=rt.temp_root)
    with workspace_lock(target):
        precheck(target, request.on_existing, default_workspace)  # ask before announcing work
        tell(sink, f"Preparing workspace {target} ({request.on_existing.value})", "prepare")
        workspace = resolve_target(target, request.on_existing, default_workspace)
        rt.temp_root.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=f"viwo-{job_id}-", dir=rt.temp_root))
        try:
            run = Run(rt, request, job_id, sink, cancel, game, work)
            with excluded(rt, (game, workspace, work), lambda m: run.log(m, "prepare", "warn")):
                return _stages(run, workspace)
        finally:
            shutil.rmtree(work, ignore_errors=True)


def _select(run: Run) -> tuple[str, ...]:
    rt = run.rt
    run.probe = FolderProbe(run.game)
    run.detections = detect_all(rt, run.probe)
    if run.probe.truncated:  # never silent: detection saw only the first part of the folder
        run.log(
            "The folder has more entries than detection reads; evidence past them is not seen",
            "detect",
            "warn",
        )
    priorities = {pid: p.manifest.priority for pid, p in rt.plugins.items()}
    picked = select_plugins(run.request, list(run.detections.values()), priorities)
    chosen = with_games(rt.plugins, picked, run.detections)
    run.log(f"Selected plugin(s): {', '.join(chosen)}", "detect")
    run.chosen = tuple(chosen)
    return chosen


def _stop_if_cancelled(run: Run) -> None:
    if run.cancel.cancelled:
        raise ViwoError("cancelled", "extraction cancelled")


def _stages(run: Run, workspace: Path) -> ExtractionResult:
    rt = run.rt
    run.log(f"Workspace: {workspace}", "prepare")
    before = snapshot(run.game)
    chosen = _select(run)
    skip = {d.lower() for pid in chosen for d in rt.plugins[pid].skip_dirs()}
    game_files = files_under(run.game, "game", skip)
    run.log(f"Scanning {len(game_files)} game file(s) for containers", "unpack")
    unpacked = unpack_all(rt, game_files, run.work / "unpack", run.ctx, run.cancel)
    _stop_if_cancelled(run)
    runs = [export_one(run, pid) for pid in chosen if not run.cancel.cancelled]
    _stop_if_cancelled(run)
    runs += rewrap(run, chosen, unpacked)
    carved, unpacked = _carve(run, runs, game_files, unpacked)
    sources = sources_for(run, chosen, {**unpacked.origins, **carved.origins}, runs)
    collected = _collect(run, workspace, sources, skip)
    _stop_if_cancelled(run)
    warnings = _verify(unpacked, collected) + [w for r in runs for w in r.warnings]
    changed = change_warning(before, snapshot(run.game), "extraction")
    if changed:  # ViWo never writes there; a running game (saves, logs) or an antivirus may
        warnings.append(changed)
    runs = verified(run, runs, collected.collected)
    warnings += [w[8:] for r in runs for w in r.warnings if w.startswith("verify: ")]
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


def _collect(run: Run, workspace: Path, sources, skip: set[str]):
    run.log(f"Collecting from {len(sources)} source folder(s) into the workspace", "collect")
    say = lambda message: run.log(message, "collect")  # noqa: E731
    selected = run.request.selected_exts
    collected = collect(sources, workspace, widened(run, selected), skip, run.cancel, say)
    groups = len(collected.by_ext)
    run.log(f"Collected {collected.collected} file(s) into {groups} group(s)", "collect")
    from ..decode import decode_all

    decode_all(run, workspace, collected)  # viewable copies of game media join the report
    collected.warnings += prune(run, workspace, collected, selected)
    run.log("Verifying: game folder, archives, plugin checks", "verify")
    return collected


def _carve(run: Run, runs, game_files, unpacked):
    """Carve unknown blobs (game and unpacked), then unpack any archives found inside them.
    Files an exporter decoded are left alone, unless that exporter failed or is missing."""
    items = game_files + [i for d, o in unpacked.origins.items() for i in files_under(d, o, set())]
    carved = carve_all(run, claimed(run, runs), items)
    nested = [i for d, o in carved.origins.items() for i in files_under(d, o, set())]
    if nested:
        more = unpack_all(run.rt, nested, run.work / "unpack-carved", run.ctx, run.cancel)
        unpacked.origins.update(more.origins)
        unpacked.found, unpacked.extracted = (
            unpacked.found + more.found,
            unpacked.extracted + more.extracted,
        )
        unpacked.by_backend.update(more.by_backend)
        unpacked.failures += more.failures
    return carved, unpacked


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
    write_atomic(workspace / ws.PROVENANCE_FILE, lines)
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
        "context": record_context(run.rt),  # doc 12.3: effective ini, tool versions
        "result": {k: v for k, v in result.to_legacy_dict().items() if k != "logs"},
    }
    write_atomic(record_path, json.dumps(record, indent=2, sort_keys=True))
    run.log(f"Run record: {record_path.relative_to(workspace)} ({meta.name})", "report")
    spent = sorted(((s, t) for s, t in run.took.items() if s and t >= 1), key=lambda i: -i[1])
    total = clock(sum(run.took.values()))
    run.log(f"Time: {total}: " + ", ".join(f"{s} {clock(t)}" for s, t in spent), "report")
    return ExtractionResult(
        **{**result.__dict__, "run_record": str(record_path), "logs": tuple(run.logs)}
    )
