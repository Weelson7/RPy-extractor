"""Continue in <tool> (doc 8.3a): a prepared GUI tool started as a tracked child of ViWo. Shared
by the static arm's handoffs (`handoff.*`: Ghidra, core/analysis) and the dynamic arm's attach
tools (`attach.*`: x64dbg, Cheat Engine, core/capture/attach.py)."""

from __future__ import annotations

import time

from viwo.contracts.errors import ViwoError
from viwo.contracts.types import CancelToken, Outcome

LAUNCHED: dict[int, object] = {}  # pid -> Child, for callers that wait on the tool


def failure(outcome: Outcome, default: str) -> ViwoError:
    """A failed outcome as an error: its kind is the code ("failed" for a stray "ok")."""
    kind = outcome.kind.value
    return ViwoError(kind if kind != "ok" else "failed", outcome.error or default)


def offered(rt, family: str, kind: str, own: str = "") -> list[dict]:
    """Every bound `<family>.*` slot whose backend accepts this target kind, `own` first."""
    found = []
    for slot_id in sorted(rt.bindings, key=lambda s: (s != own, s)):
        binding = rt.bindings[slot_id]
        if not slot_id.startswith(f"{family}.") or not binding.bound:
            continue
        backend = rt.backends[binding.main]
        if kind in getattr(backend, "accepts", ()):
            found.append({"id": backend.backend_id, "label": backend.label, "slot": slot_id})
    return found


def launch(rt, backend, target, ctx) -> dict:
    """Prepare the target and start the tool as a tracked child; what was started."""
    spec = backend.prepare(target, ctx)
    if isinstance(spec, Outcome):
        raise failure(spec, f"{backend.backend_id} could not prepare the target")
    child = rt.os.process.launch(spec.argv, spec.cwd, spec.env)
    LAUNCHED[child.pid] = child
    tool = {"handoff": backend.backend_id, "label": backend.label}
    return {**tool, "pid": child.pid, "target": target.key}


def wait_for(pid: int, cancel: CancelToken | None = None) -> bool:
    """Block until the launched tool exits (CLI); True when it ended by itself."""
    child = LAUNCHED.get(pid)
    while child is not None and child.alive():
        if cancel is not None and cancel.cancelled:
            child.kill()
            return False
        time.sleep(0.5)
    return True
