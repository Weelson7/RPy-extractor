"""Continue in x64dbg / Cheat Engine (doc 11.2, D3): the dynamic arm's attach tools. They work
on the game itself while it runs, so they sit behind the `capture` switch with one confirmation
per game and its warnings (doc 11.1), not behind `analysis`. x64dbg attaches to the game's
running process, or starts the game's own executable when none runs: a patch made live in the
debugger lands in the real process. The targets are the plugins' analysis targets (doc 6.1);
files a tool needs (the Cheat Engine table) go to `<workspace>/.runtime/<tool>/<target key>/`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from viwo.contracts.errors import ViwoError

from ..analysis import find_target, targets_for
from ..context import core_context
from ..handoff import launch, offered
from . import sensitive_plugins
from .policy import check


@dataclass(frozen=True)
class AttachRequest:
    game: Path
    workspace: Path
    target_key: str
    tool: str = ""  # a backend id from attach_for; the first one offered when empty
    pid: int = 0  # the debugger: this process, not the one found by the executable's name
    confirm: bool = False  # the once-per-game confirmation (doc 11.1)


def attach_for(rt, kind: str) -> list[dict]:
    """Every bound `attach.*` tool that accepts this target kind."""
    return offered(rt, "attach", kind)


def listing(rt, game: Path, problems: list[str] | None = None) -> list[dict]:
    """The plugins' targets an attach tool accepts, each with its tools (`attach`)."""
    found = (
        {**t.to_dict(), "attach": attach_for(rt, t.kind)} for t in targets_for(rt, game, problems)
    )
    return [t for t in found if t["attach"]]


def _pid(rt, req: AttachRequest, exe: Path) -> int:
    """The game's process for the debugger: the one given, else the one running the target's
    executable; 0 when none runs (the debugger starts it)."""
    if req.pid:
        return req.pid
    found = rt.os.pids_of(exe.name)
    if len(found) > 1:
        raise ViwoError(
            "needs_decision",
            f"{len(found)} running processes named {exe.name}",
            hint="give the pid",
        )
    return found[0] if found else 0


def attach(rt, req: AttachRequest) -> dict:
    """Start the tool on the game as a tracked child; the warnings come with the result."""
    target = find_target(rt, req.game, req.target_key)
    tools = {t["id"]: t for t in attach_for(rt, target.kind)}
    choice = req.tool or next(iter(tools), "")
    if choice not in tools:
        raise ViwoError("unavailable", f"no attach tool {choice!r} for {target.kind} targets")
    warnings = check(rt, req.game, req.confirm, sensitive_plugins(rt, req.game))
    ctx = core_context(rt, "attach", req.game, rt.temp_root)
    ctx.staging = req.workspace / ".runtime" / choice / target.key
    if tools[choice]["slot"] == "attach.debug":
        ctx.options = {"pid": _pid(rt, req, target.paths[0])}
    opened = launch(rt, rt.backends[choice], target, ctx)
    return {**opened, "attached": int(ctx.options.get("pid") or 0), "warnings": warnings}
