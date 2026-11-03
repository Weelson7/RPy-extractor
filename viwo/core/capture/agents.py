"""D2 runner: the engine's runtime agent in a patched copy of the game. The copy is made (or
reused), the agent installs itself and its settings there, the copy's executable runs as a
tracked child until the agent says it is finished (or the timeout), then it is stopped and the
agent's files are collected into `<workspace>/.runtime/agent/<agent>/`. The game folder is only
read. Audio (`capture.audio`) records the system output while a game plays."""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.runtime import RuntimeAgent

from ..pipeline.probe import FolderProbe
from ..pipeline.runner import detect_all
from ..roundtrip import MARKER, prepare_copy
from .runtime import _enabled


def agent_for(rt, game: Path) -> RuntimeAgent:
    """The bound `runtime.<engine>` agent of the best-detected engine."""
    found = detect_all(rt, FolderProbe(game))
    for engine in sorted(found, key=lambda p: -found[p].confidence):
        binding = rt.bindings.get(f"runtime.{engine}")
        if binding is not None and binding.bound:
            return rt.backends[binding.main]
    raise ViwoError(
        "unavailable", "no runtime agent for this engine", hint="Unity IL2CPP and Unreal have one"
    )


def _wait(agent: RuntimeAgent, copy: Path, exe: Path, child, timeout: float, cancel) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and child.alive():
        if agent.finished(copy, exe):
            return True
        if cancel is not None and cancel.cancelled:
            break
        time.sleep(1)
    return agent.finished(copy, exe)


@dataclass(frozen=True)
class AgentRequest:
    game: Path
    exe: Path
    workspace: Path
    copy: Path | None = None  # the patched copy to use (default: beside the workspace)
    timeout: float = 600


def run_agent(rt, req: AgentRequest, cancel=None) -> dict:
    game, exe, workspace, copy, timeout = req.game, req.exe, req.workspace, req.copy, req.timeout
    _enabled(rt)
    agent = agent_for(rt, game)
    copy = (copy or workspace.parent / f"{workspace.name}.agent-copy").resolve()
    left: list[str] = []
    if not (copy / MARKER).is_dir():
        rt.temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=rt.temp_root) as tmp:
            left = prepare_copy(game, copy, Path(tmp))  # antivirus-held files stay out
    target = copy / exe.resolve().relative_to(game.resolve())
    why = agent.accepts(copy, target)
    if why:
        raise ViwoError("unavailable", f"{agent.backend_id}: {why}")
    from ..context import core_context

    ctx = core_context(rt, "agent", copy, rt.temp_root)
    args = agent.install(copy, target, ctx)
    child = rt.os.process.launch([str(target), *args], target.parent)
    try:
        done = _wait(agent, copy, target, child, timeout, cancel)
    finally:
        child.kill()
    out = workspace.resolve() / ".runtime" / "agent" / agent.backend_id
    out.mkdir(parents=True, exist_ok=True)
    files = [Path(shutil.copy2(f, out / f.name)) for f in agent.outputs(copy, target)]
    return {
        "agent": agent.backend_id,
        "finished": done,
        "copy": str(copy),
        "outputDir": str(out),
        "files": [f.name for f in files],
        "notCopied": left,  # files the antivirus held back from the copy
    }
