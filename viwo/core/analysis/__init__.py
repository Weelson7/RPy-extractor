"""Static analysis jobs (doc 6): targets proposed by the plugins, one analyzer run per target
into `<workspace>/.analysis/<analyzer>/<key>/`, and "continue in <tool>" handoffs (doc 8.3a).
Never part of an extraction; behind the `analysis` feature switch (a capability switch)."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts.analysis import ANALYSIS_DIR, AnalysisTarget
from viwo.contracts.errors import ViwoError
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import CancelToken, Outcome

from ..context import core_context
from ..pipeline.failover import run_with_failover
from ..pipeline.probe import FolderProbe
from ..records import record_context
from ..scan_exclusions import excluded
from ..workspace import write_atomic
from .emulate import AngrSymbolic, UnicornEmulate
from .ghidra import GhidraGui, GhidraHeadless
from .handoffs import CheatEngineGui, X64dbgGui
from .identify import DetectItEasy
from .managed import Cpp2Il, IlSpy, Unluac


def slot_for(kind: str) -> str:
    """`analysis.<family>` for a target kind (doc 6.2): native_binary -> analysis.native."""
    return f"analysis.{kind.split('_')[0]}"


def output_dir(workspace: Path, backend_id: str, key: str) -> Path:
    return workspace / ANALYSIS_DIR / backend_id / key


def _failure(outcome: Outcome, default: str) -> ViwoError:
    """A failed outcome as an error: its kind is the code ("failed" for a stray "ok")."""
    kind = outcome.kind.value
    return ViwoError(kind if kind != "ok" else "failed", outcome.error or default)


SLOTS = (
    SlotDefinition("analysis.native", "analysis", "core", "ghidra-headless"),
    SlotDefinition("handoff.native", "handoff", "core", "ghidra-gui"),
    SlotDefinition("analysis.dotnet", "analysis", "core", "ilspycmd"),
    SlotDefinition("analysis.il2cpp", "analysis", "core", "cpp2il"),
    SlotDefinition("analysis.script", "analysis", "core", "unluac"),
    SlotDefinition("analysis.protector", "analysis", "core", "die"),
    SlotDefinition("analysis.emulate", "analysis", "core", "unicorn-emulate"),
    SlotDefinition("analysis.symbolic", "analysis", "core", "angr-symbolic"),
    SlotDefinition("handoff.debug", "handoff", "core", "x64dbg-gui"),
    SlotDefinition("handoff.memory", "handoff", "core", "cheatengine-gui"),
)


def backends() -> list:
    return [
        GhidraHeadless(),
        GhidraGui(),
        IlSpy(),
        Cpp2Il(),
        Unluac(),
        DetectItEasy(),
        UnicornEmulate(),
        AngrSymbolic(),
        X64dbgGui(),
        CheatEngineGui(),
    ]


@dataclass
class AnalysisRequest:
    game: Path
    workspace: Path
    target_key: str
    options: dict = field(default_factory=dict)  # timeout_s, analyzer-specific keys
    slot: str = ""  # an analysis slot other than the kind's own (extras_for), e.g. protector


def targets_for(rt, game: Path, problems: list[str] | None = None) -> list[AnalysisTarget]:
    """Every plugin's proposals for this folder (doc 6.1), deduplicated by key. A hook that
    raises is reported in `problems` (when given) and never hides the other plugins."""
    probe = FolderProbe(game)
    out: dict[str, AnalysisTarget] = {}
    for plugin_id, plugin in sorted(rt.plugins.items()):
        try:
            found = list(plugin.analysis_targets(probe))
        except Exception as exc:  # noqa: BLE001
            if problems is not None:
                problems.append(f"plugin {plugin_id}: analysis_targets failed: {exc}")
            continue
        for target in found:
            out.setdefault(target.key, target)
    return list(out.values())


def _check_enabled(rt) -> None:
    if "analysis" not in rt.config.features:
        raise ViwoError(
            "refused",
            "static analysis is off",
            hint="add analysis to [startup] features in the ini (11 SETTINGS); first use shows "
            "the disclaimer: you are responsible for having the right to analyse the binaries",
        )


def _pick(rt, req: AnalysisRequest) -> tuple[AnalysisTarget, str]:
    """(target, slot id) for the request; unknown key or kind without a slot is an error."""
    targets = {t.key: t for t in targets_for(rt, req.game)}
    if req.target_key not in targets:
        raise ViwoError(
            "not_found",
            f"no analysis target {req.target_key!r} in {req.game}",
            hint="targets: " + ", ".join(sorted(targets)) if targets else "no target proposed",
        )
    target = targets[req.target_key]
    slot = req.slot or slot_for(target.kind)
    if slot not in rt.bindings or (req.slot and not _accepts(rt, slot, target.kind)):
        raise ViwoError("unavailable", f"no analyzer slot for {target.kind} targets yet")
    return target, slot


def _accepts(rt, slot: str, kind: str) -> bool:
    binding = rt.bindings.get(slot)
    backend = rt.backends.get(binding.main) if binding is not None and binding.bound else None
    return backend is not None and kind in getattr(backend, "kinds", ())


def _label(backend) -> str:
    return getattr(backend, "label", None) or backend.backend_id.replace("-", " ")


def extras_for(rt, kind: str) -> list[dict]:
    """The other bound analyzers that take this kind (doc 16.2b A3: identify before decompile)."""
    own = slot_for(kind)
    return [
        {
            "slot": slot,
            "backend": rt.bindings[slot].main,
            "label": _label(rt.backends[rt.bindings[slot].main]),
        }
        for slot in sorted(rt.bindings)
        if slot.startswith("analysis.") and slot != own and _accepts(rt, slot, kind)
    ]


def _context(rt, req: AnalysisRequest, out: Path, scratch: Path, sink, cancel):
    """Exports go to `out` (under .analysis/), emptied first so a failed rerun cannot pass on
    last time's artifacts; the copy of the input sits in `scratch`."""
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    ctx = core_context(rt, "analyze", req.game, scratch, sink, cancel)
    ctx.staging, ctx.scratch, ctx.options = out, scratch, req.options
    return ctx


def _copy_inputs(target: AnalysisTarget, scratch: Path) -> AnalysisTarget:
    """The analyzer reads a copy (doc 6.5): the game folder is never handed to a tool."""
    folder = scratch / "input"
    folder.mkdir(parents=True, exist_ok=True)
    copies: list[Path] = []
    for index, path in enumerate(target.paths):  # same-named chunks from different folders
        name = path.name if path.name not in {c.name for c in copies} else f"{index}-{path.name}"
        copies.append(Path(shutil.copy2(path, folder / name)))
    copies = tuple(copies)
    return AnalysisTarget(target.key, target.kind, copies, target.owner, target.label, target.hints)


def analyze(rt, req: AnalysisRequest, sink=None, cancel: CancelToken | None = None) -> dict:
    """One analyzer run as a job: copy the inputs, run the slot's backend, write the record."""
    _check_enabled(rt)
    target, slot = _pick(rt, req)
    binding, cancel = rt.bindings[slot], cancel or CancelToken()
    if not binding.bound:
        raise ViwoError(
            "unavailable",
            f"{slot} has no available backend",
            hint=binding.reasons[0] if binding.reasons else "see `viwo slots`",
        )
    rt.temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=rt.temp_root, prefix="viwo-analyze-") as tmp:
        scratch = Path(tmp)
        out = output_dir(req.workspace, binding.main, target.key)
        ctx = _context(rt, req, out, scratch, sink or (lambda e: None), cancel)
        with excluded(rt, (req.game, out, scratch), lambda m: ctx.log(m, "warn", "analyze")):
            inputs = _copy_inputs(target, scratch)
            outcome, used = run_with_failover(
                binding, rt.backends, lambda b: b.analyze(inputs, ctx)
            )
    if not outcome.ok:
        raise _failure(outcome, f"{slot} failed")
    if outcome.fallback:
        ctx.log(outcome.fallback, "warn", "analyze")
    artifacts = sorted(p.name for p in out.iterdir() if p.is_file())  # where the run wrote
    report = {
        "target": target.to_dict(),
        "backend": used,
        "outputDir": str(out),
        "artifacts": artifacts,
        "notes": list(outcome.notes),
        "fallback": outcome.fallback,
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "context": record_context(rt),
    }
    write_atomic(out / "record.json", json.dumps(report, indent=2, sort_keys=True))
    return report


def handoffs_for(rt, kind: str) -> list[dict]:
    """Every bound handoff that accepts this target kind (doc 8.3a), the kind's own first
    (Ghidra for a native binary), then the others (x64dbg, Cheat Engine)."""
    own = slot_for(kind).replace("analysis.", "handoff.")
    found = []
    for slot_id in sorted(rt.bindings, key=lambda s: (s != own, s)):
        binding = rt.bindings[slot_id]
        if not slot_id.startswith("handoff.") or not binding.bound:
            continue
        backend = rt.backends[binding.main]
        if kind in getattr(backend, "accepts", ()):
            found.append({"id": backend.backend_id, "label": backend.label, "slot": slot_id})
    return found


LAUNCHED: dict[int, object] = {}  # pid -> Child, for callers that wait on the tool


def wait_for(pid: int, cancel: CancelToken | None = None) -> bool:
    """Block until the launched tool exits (CLI); True when it ended by itself."""
    child = LAUNCHED.get(pid)
    while child is not None and child.alive():
        if cancel is not None and cancel.cancelled:
            child.kill()
            return False
        time.sleep(0.5)
    return True


def open_in(rt, req: AnalysisRequest, handoff_id: str = "") -> dict:
    """Prepare the target and start the GUI tool as a tracked child; returns the pid."""
    _check_enabled(rt)
    target, slot = _pick(rt, req)
    offered = {h["id"]: h for h in handoffs_for(rt, target.kind)}
    choice = handoff_id or next(iter(offered), "")
    if choice not in offered:
        raise ViwoError(
            "unavailable",
            f"no handoff {handoff_id or ''} for {target.kind} targets".replace("  ", " "),
        )
    backend = rt.backends[choice]
    own = offered[choice]["slot"] == slot.replace("analysis.", "handoff.")
    ctx = core_context(rt, "handoff", req.game, rt.temp_root)
    # the kind's own handoff opens the analyzer's project; the others get a folder of their own
    ctx.staging = output_dir(req.workspace, rt.bindings[slot].main if own else choice, target.key)
    spec = backend.prepare(target, ctx)
    if isinstance(spec, Outcome):
        raise _failure(spec, f"{choice} could not prepare the target")
    child = rt.os.process.launch(spec.argv, spec.cwd, spec.env)
    LAUNCHED[child.pid] = child
    return {
        "handoff": backend.backend_id,
        "label": backend.label,
        "pid": child.pid,
        "target": target.key,
    }
