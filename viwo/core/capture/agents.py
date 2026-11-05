"""D2 runner: the engine's runtime agent in a patched copy of the game. The copy is made (or
reused), the agent installs itself and its settings there, the copy's executable runs as a
tracked child until the agent says it is finished (or the timeout), then it is stopped and the
agent's files are collected into `<workspace>/.runtime/agent/<agent>/`. The game folder is only
read. Audio (`viwo record`) records the system output while a game plays."""

import shutil
import time
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.runtime import RuntimeAgent

from ..context import core_context
from ..pipeline.probe import FolderProbe
from ..pipeline.runner import detect_all
from ..roundtrip import prepare_copy
from .runtime import RuntimeRequest, _enabled, runtime_dir

REPORT_EVERY = 30  # seconds between "still waiting" events


def agent_for(rt, game: Path) -> RuntimeAgent:
    """The bound `runtime.<plugin>` agent of the plugins that detected this game (a game plugin's
    before its engine's); a plugin that did not detect the game never lends its agent."""
    found = detect_all(rt, FolderProbe(game))
    ranked = sorted(
        (p for p in found if found[p].confidence >= 0.5 and p != "generic"),
        key=lambda p: (not rt.plugins[p].manifest.engine, -found[p].confidence),
    )
    for plugin in ranked:
        binding = rt.bindings.get(f"runtime.{plugin}")
        if binding is not None and binding.bound:
            return rt.backends[binding.main]
    engines = ", ".join(ranked) or "no engine detected"
    raise ViwoError(
        "unavailable",
        f"no runtime agent for this game ({engines})",
        hint="Unity (BepInEx) and Unreal (UE4SS) have one",
    )


def _wait(agent: RuntimeAgent, copy: Path, exe: Path, child, req: RuntimeRequest, ctx) -> bool:
    start = last = time.monotonic()
    while time.monotonic() - start < req.timeout and child.alive():
        if agent.finished(copy, exe):
            return True
        if ctx.cancel.cancelled:
            break
        if time.monotonic() - last >= REPORT_EVERY:
            last = time.monotonic()
            waited = f"{last - start:.0f} / {req.timeout:.0f} s"
            ctx.log(f"Waiting for {agent.backend_id}: {waited}", stage="agent")
        time.sleep(1)
    return agent.finished(copy, exe)


def _exe_in_game(req: RuntimeRequest) -> Path:
    """`exe` relative to the game: the copy's executable sits at the same place in the copy."""
    try:
        return req.exe.resolve().relative_to(req.game.resolve())
    except ValueError:
        raise ViwoError(
            "invalid_request",
            f"{req.exe} is not inside the game folder {req.game}",
            hint="give the game's own executable; the agent runs it from the patched copy",
        ) from None


def _unfinished(agent: str, files: list[Path], req: RuntimeRequest, ctx) -> list[str]:
    """Never silent: an agent that did not finish is a warning, or a failure with no files."""
    why = f"the game closed, the run was cancelled or {req.timeout:.0f} s passed"
    if not files:
        raise ViwoError(
            "failed",
            f"{agent} did not finish ({why}) and wrote nothing",
            hint="let the game run until the agent is done, or raise --timeout",
        )
    text = f"{agent} did not finish ({why}): what it wrote so far was kept"
    ctx.log(text, "warn", "agent")
    return [text]


def run_agent(rt, req: RuntimeRequest, sink=None, cancel=None) -> dict:
    _enabled(rt)
    agent = agent_for(rt, req.game)
    copy = (req.copy or req.workspace.parent / f"{req.workspace.name}.agent-copy").resolve()
    target = copy / _exe_in_game(req)  # refused before anything is copied
    left = prepare_copy(rt, req.game, copy, sink, "agent", reuse=True)
    why = agent.accepts(copy, target)
    if why:
        raise ViwoError("unavailable", f"{agent.backend_id}: {why}")
    ctx = core_context(rt, "agent", copy, rt.temp_root, sink, cancel)
    ctx.log(f"Installing {agent.backend_id} into {copy}", stage="agent")
    args = agent.install(copy, target, ctx)
    ctx.log(f"Running {target.name} until {agent.backend_id} is done", stage="agent")
    child = rt.os.process.launch([str(target), *args], target.parent)
    try:
        done = _wait(agent, copy, target, child, req, ctx)
    finally:
        child.kill()
    found = agent.outputs(copy, target)
    warnings = [] if done else _unfinished(agent.backend_id, found, req, ctx)
    out = runtime_dir(req.workspace, "agent", agent.backend_id)
    files = [Path(shutil.copy2(f, out / f.name)) for f in found]
    ctx.log(f"Collected {len(files)} file(s) into {out}", stage="agent")
    return {
        "agent": agent.backend_id,
        "finished": done,
        "copy": str(copy),
        "outputDir": str(out),
        "files": [f.name for f in files],
        "notCopied": left,  # files the OS refused to copy (also a warn event)
        "warnings": warnings,
    }
