"""10 CAPTURE: file picker, the warnings before a capture, and the capture itself as a job."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from viwo.contracts.errors import ViwoError
from viwo.core.capture import CaptureRequest, capture, warnings
from viwo.core.capture.policy import CONFIRMATION, DEFAULT_AUTO
from viwo.core.workspace import claim

from .app import App, failure


def browse_file(app: App, q: dict) -> dict:
    start = Path(q.get("initialPath") or Path.home()).expanduser()
    if start.is_file():
        start = start.parent
    chosen = app.rt.os.shell.pick_file(
        "Select the game executable", start if start.exists() else None, ()
    )
    if chosen is None:
        return {
            "success": False,
            "cancelled": True,
            "error": "No file selected",
            "code": "cancelled",
        }
    return {"success": True, "path": str(chosen)}


def capture_warnings(app: App, d: dict) -> dict:
    """What the user should know before capturing this game: information, never a block."""
    game = Path(str(d.get("gamePath", "")).strip())
    if not str(game) or not game.is_dir():
        return failure(ViwoError("not_found", f"Game folder not found: {game}"))
    binding = app.rt.bindings.get("capture.gpu")
    return {
        "success": True,
        "warnings": warnings(app.rt, game),
        "confirmation": CONFIRMATION,
        "enabled": "capture" in app.rt.config.features,
        "backend": binding.main if binding is not None and binding.bound else "",
    }


def run_capture(app: App, d: dict) -> dict:
    """Capture into the active workspace as a job (kind "capture"); error codes pass through."""
    game = Path(str(d.get("gamePath", "")).strip())
    exe = Path(str(d.get("exePath", "")).strip())
    if not str(game) or not game.is_dir():
        return failure(ViwoError("not_found", f"Game folder not found: {game}"))
    if not str(exe) or not exe.is_file():
        return failure(ViwoError("not_found", f"Executable not found: {exe}"))
    workspace = app.workspace
    if not workspace.exists() or not any(workspace.iterdir()):
        claim(workspace)  # the lock file lands inside it before capture() looks at it
    try:
        after = float(d.get("captureAfter") or DEFAULT_AUTO)
    except (TypeError, ValueError):
        return failure(ViwoError("invalid_request", "captureAfter must be a number of seconds"))
    request = CaptureRequest(game, exe, workspace, bool(d.get("confirmed")), after)

    def run(sink, cancel) -> dict:
        return {"success": True, **capture(app.rt, request, sink, cancel)}

    return app.locked_job("capture", workspace, run)


def runtime_job(app: App, d: dict, kind: str) -> dict:
    """POST /api/runtime/dump {pid|name} and /api/runtime/trace {pid|name, functions, seconds}:
    the D3 headless runs as jobs, written under the active workspace's .runtime/."""
    from viwo.core.capture import runtime

    pid, name = int(d.get("pid") or 0), str(d.get("name", ""))
    if kind in ("dump", "trace") and not pid and not name:
        return failure(ViwoError("invalid_request", "give pid or name"))
    functions = [str(f) for f in (d.get("functions") or ["CreateFileW"])]
    seconds = float(d.get("seconds") or 10)

    def run(sink, cancel) -> dict:
        if kind == "agent":
            from viwo.core.capture.agents import AgentRequest, run_agent

            game, exe = Path(str(d.get("gamePath", ""))), Path(str(d.get("exePath", "")))
            req = AgentRequest(game, exe, app.workspace)
            return {"success": True, **run_agent(app.rt, req, cancel)}
        if kind == "record":
            from viwo.core.capture.audio import record

            return {"success": True, **record(app.rt, app.workspace, seconds)}
        if kind == "dump":
            return {"success": True, **runtime.dump(app.rt, app.workspace, pid, name)}
        done = runtime.trace(app.rt, app.workspace, (pid, name), functions, seconds, cancel)
        return {"success": True, **done}

    return app.job(kind, lambda jid, s, c: run(s, c))


CAPTURE_GET: dict[str, Callable[[App, dict], Any]] = {"/api/browse-file": browse_file}
CAPTURE_POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/capture/warnings": capture_warnings,
    "/api/capture": run_capture,
    "/api/runtime/dump": lambda app, d: runtime_job(app, d, "dump"),
    "/api/runtime/trace": lambda app, d: runtime_job(app, d, "trace"),
    "/api/runtime/agent": lambda app, d: runtime_job(app, d, "agent"),
    "/api/runtime/record": lambda app, d: runtime_job(app, d, "record"),
}
