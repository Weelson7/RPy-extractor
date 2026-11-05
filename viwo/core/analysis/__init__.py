"""Static analysis jobs (doc 6): targets proposed by the plugins, one analyzer run per target
into `<workspace>/.analysis/<analyzer>/<key>/`, and the static "continue in <tool>" handoffs
(doc 8.3a: Ghidra). Never part of an extraction; behind the `analysis` feature switch (a
capability switch). Nothing here runs the game: the debugger and memory tools that do are the
dynamic arm's (`core/capture/attach.py`)."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts.analysis import ANALYSIS_DIR, AnalysisTarget
from viwo.contracts.errors import ViwoError
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import CancelToken

from ..context import core_context
from ..handoff import failure, launch, offered
from ..pipeline.failover import run_with_failover
from ..pipeline.probe import FolderProbe
from ..records import record_context
from ..scan_exclusions import excluded
from ..workspace import write_atomic
from .emulate import AngrSymbolic, UnicornEmulate
from .ghidra import GhidraGui, GhidraHeadless
from .identify import DetectItEasy
from .managed import Cpp2Il, IlSpy, Unluac

_ANALYSIS_NAME = re.compile(r"[^A-Za-z0-9._-]")  # a copied binary's name a tool can take (Ghidra)


def slot_for(kind: str) -> str:
    """`analysis.<family>` for a target kind (doc 6.2): native_binary -> analysis.native."""
    return f"analysis.{kind.split('_')[0]}"


def output_dir(workspace: Path, backend_id: str, key: str) -> Path:
    return workspace / ANALYSIS_DIR / backend_id / key


SLOTS = (
    SlotDefinition("analysis.native", "analysis", "core", "ghidra-headless"),
    SlotDefinition("handoff.native", "handoff", "core", "ghidra-gui"),
    SlotDefinition("analysis.dotnet", "analysis", "core", "ilspycmd"),
    SlotDefinition("analysis.il2cpp", "analysis", "core", "cpp2il"),
    SlotDefinition("analysis.script", "analysis", "core", "unluac"),
    SlotDefinition("analysis.protector", "analysis", "core", "die"),
    SlotDefinition("analysis.emulate", "analysis", "core", "unicorn-emulate"),
    SlotDefinition("analysis.symbolic", "analysis", "core", "angr-symbolic"),
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
    from ..context import require

    more = "; you are responsible for having the right to analyse the binaries"
    require(rt, "analysis", "static analysis", more)


def find_target(rt, game: Path, key: str) -> AnalysisTarget:
    """The proposed target with this key; an unknown key names the ones there are."""
    targets = {t.key: t for t in targets_for(rt, game)}
    if key not in targets:
        raise ViwoError(
            "not_found",
            f"no analysis target {key!r} in {game}",
            hint="targets: " + ", ".join(sorted(targets)) if targets else "no target proposed",
        )
    return targets[key]


def _pick(rt, req: AnalysisRequest) -> tuple[AnalysisTarget, str]:
    """(target, slot id) for the request; unknown key or kind without a slot is an error."""
    target = find_target(rt, req.game, req.target_key)
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
    taken: set[str] = set()
    for index, path in enumerate(target.paths):
        # a name a tool can take: Ghidra's headless refuses an apostrophe, a space and more
        # ("Void's Cave.exe": "Please rename"); the extension is kept for format detection
        safe = _ANALYSIS_NAME.sub("_", path.stem) + path.suffix
        name = safe if safe not in taken else f"{index}-{safe}"  # same-named chunks of two folders
        taken.add(name)
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
        raise failure(outcome, f"{slot} failed")
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
    """Every bound static handoff (`handoff.*`, doc 8.3a) that accepts this target kind, the
    kind's own first (Ghidra for a native binary)."""
    return offered(rt, "handoff", kind, slot_for(kind).replace("analysis.", "handoff."))


def open_in(rt, req: AnalysisRequest, handoff_id: str = "") -> dict:
    """Prepare the target and start the GUI tool as a tracked child; returns the pid."""
    _check_enabled(rt)
    target, slot = _pick(rt, req)
    tools = {h["id"]: h for h in handoffs_for(rt, target.kind)}
    choice = handoff_id or next(iter(tools), "")
    if choice not in tools:
        raise ViwoError(
            "unavailable",
            f"no handoff {handoff_id or ''} for {target.kind} targets".replace("  ", " "),
        )
    own = tools[choice]["slot"] == slot.replace("analysis.", "handoff.")
    ctx = core_context(rt, "handoff", req.game, rt.temp_root)
    # the kind's own handoff opens the analyzer's project; the others get a folder of their own
    ctx.staging = output_dir(req.workspace, rt.bindings[slot].main if own else choice, target.key)
    return launch(rt, rt.backends[choice], target, ctx)
