"""Runtime capture pilot (D19, doc 11): POLICY -> RESTORE pending -> CAPTURE (RenderDoc) ->
HARVEST -> GATHER into the workspace -> DIFF against static extraction -> REPORT."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import CancelToken, DetectionResult, ProgressEvent

from ..context import core_context
from ..pipeline.collect import Source, collect, sha256
from ..pipeline.failover import run_with_failover
from ..pipeline.guard import refuse_writes_inside
from ..pipeline.probe import FolderProbe
from ..pipeline.runner import detect_all
from ..records import record_context
from ..steps import teller
from ..workspace import claim, write_atomic
from .journal import pending
from .policy import check, warnings_for
from .renderdoc import RENDERDOCCMD, RenderDocCapture

SLOTS = (SlotDefinition("capture.gpu", "capture", "core", "renderdoc"),)


def backends() -> list:
    return [RenderDocCapture()]


def _known_hashes(workspace: Path) -> set[str]:
    path = workspace / ws.PROVENANCE_FILE
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return {json.loads(line)["sha256"] for line in lines}


def sensitive_plugins(rt, game: Path) -> list[str]:
    found = detect_all(rt, FolderProbe(game))
    return [
        p for p, d in found.items() if d.confidence >= 0.5 and rt.plugins[p].manifest.tos_sensitive
    ]


def warnings(rt, game: Path) -> list[str]:
    """Everything the user should know before a capture (doc 11.1): markers, running services,
    online titles, sensitive plugins, network; information, never a block."""
    return warnings_for(game, sensitive_plugins(rt, game), rt)


@dataclass
class CaptureRequest:
    game: Path
    exe: Path
    workspace: Path
    confirmed: bool = False


def _restore_pending(rt, say) -> None:
    warn = teller(say, "restore", "warn") or (lambda m: None)
    for journal in pending(rt.temp_root.parent / "capture", warn):
        say(
            ProgressEvent(
                f"Restoring an interrupted session in {journal.game}", "warn", "core", "restore"
            )
        )
        if journal.restore():
            raise ViwoError(
                "failed", f"could not restore {journal.game}; check it before capturing"
            )


def _prepare(rt, req: CaptureRequest) -> set[str]:
    """Check the target workspace; returns the hashes static extraction already produced."""
    refuse_writes_inside(req.game, workspace=req.workspace, temp_folder=rt.temp_root)
    folder = req.workspace
    if folder.is_dir() and any(folder.iterdir()) and not ws.has_marker(folder):
        raise ViwoError("refused", f"{folder} is not empty and is not a ViWo workspace")
    known = _known_hashes(folder) if folder.is_dir() else set()
    claim(folder)
    return known


def _run(rt, req: CaptureRequest, known: set[str], sink, cancel) -> tuple:
    binding = rt.bindings.get("capture.gpu")
    if binding is None or not binding.bound:
        raise ViwoError("unavailable", "no capture backend", hint=RENDERDOCCMD.hint)
    rt.temp_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="viwo-capture-", dir=rt.temp_root))
    try:
        ctx = core_context(rt, "capture", req.game, work, sink, cancel)
        ctx.staging.mkdir(parents=True)
        spec = {"exe": str(req.exe), "workdir": str(req.exe.parent), "args": []}
        outcome, used = run_with_failover(
            binding, rt.backends, lambda b: b.capture(spec, ctx.staging, ctx)
        )
        if not outcome.ok:
            raise ViwoError("failed", outcome.error or "capture failed")
        job = time.strftime("%Y%m%d-%H%M%S")
        same = [f for f in ctx.staging.rglob("*") if f.is_file() and sha256(f) in known]
        for f in same:  # already found by static extraction: not stored twice
            f.unlink()
        origin = Source(ctx.staging, True, f"capture:{used}:{job}")
        return collect([origin], req.workspace, None, set(), ctx.cancel), used, job, len(same)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def capture(rt, req: CaptureRequest, sink=None, cancel=None) -> dict:
    say = sink or (lambda e: None)
    if not ws.inside(req.game, req.exe) or not req.exe.is_file():  # policy covers the game only
        raise ViwoError("refused", "the executable must be a file inside the game folder")
    warnings = check(rt, req.game, req.confirmed, sensitive_plugins(rt, req.game))
    _restore_pending(rt, say)
    known = _prepare(rt, req)
    gathered, used, job, same = _run(rt, req, known, sink, cancel)
    new = gathered.provenance
    (req.workspace / ws.METADATA_DIR).mkdir(parents=True, exist_ok=True)
    with open(req.workspace / ws.PROVENANCE_FILE, "a", encoding="utf-8") as fh:
        fh.writelines(json.dumps(p, sort_keys=True) + "\n" for p in gathered.provenance)
    report = {
        "game": str(req.game),
        "backend": used,
        "gathered": gathered.collected,
        "alreadyStatic": same,
        "newVsStatic": len(new),
        "new": [p["path"] for p in new][:200],
        "warnings": warnings,
        "context": record_context(rt),  # effective ini, bindings, tool versions (doc 12.3)
    }
    (req.workspace / ws.RUNS_DIR).mkdir(parents=True, exist_ok=True)
    record = req.workspace / ws.RUNS_DIR / f"capture-{job}.json"
    write_atomic(record, json.dumps(report, indent=2))
    say(
        ProgressEvent(
            f"Captured {gathered.collected} file(s), {len(new)} new vs static",
            "info",
            "core",
            "report",
        )
    )
    return report
