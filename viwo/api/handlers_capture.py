"""CAPTURE: file picker, the warnings before a capture, and the capture itself as a job."""

from pathlib import Path
from typing import Any, Callable

from viwo.contracts.errors import ViwoError
from viwo.core.capture import CaptureRequest, capture, warnings
from viwo.core.capture.policy import CONFIRMATION, DEFAULT_AUTO
from viwo.core.workspace import claim

from .app import App, existing, failure, foreign, path_param, picked


def browse_file(app: App, q: dict) -> dict:
    start = Path(q.get("initialPath") or Path.home()).expanduser()
    if start.is_file():
        start = start.parent
    chosen = app.rt.os.shell.pick_file(
        "Select the game executable", start if start.exists() else None, ()
    )
    return picked(chosen, "file")


def capture_warnings(app: App, d: dict) -> dict:
    """What the user should know before capturing this game: information, never a block."""
    if isinstance(game := existing(d, "gamePath", "Game folder"), dict):
        return game
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
    game, exe = existing(d, "gamePath", "Game folder"), existing(d, "exePath", "Executable", False)
    for given in (game, exe):
        if isinstance(given, dict):
            return given
    workspace = app.workspace
    if not workspace.exists() or not any(workspace.iterdir()):
        claim(workspace)  # the lock file lands inside it before capture() looks at it
    try:
        raw = d.get("captureAfter")  # 0 means attended: the user presses F12 in the game
        after = DEFAULT_AUTO if raw in (None, "") else float(raw)
    except (TypeError, ValueError):
        return failure(ViwoError("invalid_request", "captureAfter must be a number of seconds"))
    request = CaptureRequest(game, exe, workspace, bool(d.get("confirmed")), after)

    def run(sink, cancel) -> dict:
        return {"success": True, **capture(app.rt, request, sink, cancel)}

    return app.locked_job("capture", workspace, run)


def runtime_job(app: App, d: dict, kind: str) -> dict:
    """POST /api/runtime/<kind>: dump {pid|name}, trace {pid|name, functions, seconds}, hook
    {pid|name, scriptPath, seconds}, agent {gamePath, exePath}, record {seconds}; jobs that
    write under the active workspace's .runtime/."""
    from viwo.core.capture.runtime import RuntimeRequest, run

    try:
        _ours(app)
        pid, seconds = _number(d, "pid", int, 0), _number(d, "seconds", float, 10)
    except ViwoError as exc:
        return failure(exc)
    name = str(d.get("name", ""))
    if kind in ("dump", "trace", "hook", "profile") and not pid and not name:
        return failure(ViwoError("invalid_request", "give pid or name"))
    req = RuntimeRequest(
        app.workspace,
        pid,
        name,
        tuple(str(f) for f in (d.get("functions") or ["CreateFileW"])),
        seconds,
        path_param(d, "gamePath") or Path(""),
        path_param(d, "exePath") or Path(""),
        script=path_param(d, "scriptPath") or Path(""),
    )
    return app.job(kind, lambda jid, s, c: {"success": True, **run(app.rt, kind, req, s, c)})


def _number(d: dict, key: str, cast, default):
    """A number from the request (a runbook's input arrives as text); anything else is named,
    never a 500 (a boolean is not a pid)."""
    raw = d.get(key)
    if raw in (None, ""):
        return default
    try:
        if isinstance(raw, bool):
            raise TypeError(key)
        return cast(raw)
    except (TypeError, ValueError) as exc:
        raise ViwoError("invalid_request", f"{key} must be a number, not {raw!r}") from exc


def _ours(app: App) -> None:
    """Runtime files go under the active workspace's .runtime/: never into a game folder or a
    folder of the user's opened as the workspace."""
    if foreign(app.workspace):
        raise ViwoError(
            "refused",
            f"{app.workspace} is not a ViWo workspace: nothing is written into it",
            hint="extract a game into it first, or open a workspace ViWo made",
        )


def runtime_routes(prefix: str) -> dict[str, Callable[[App, dict], Any]]:
    """`<prefix><kind>` -> runtime_job for every dynamic-arm kind (routes and job kinds)."""
    kinds = ("dump", "trace", "hook", "profile", "agent", "record")
    return {f"{prefix}{k}": (lambda app, d, k=k: runtime_job(app, d, k)) for k in kinds}


def attach_targets(app: App, q: dict) -> dict:
    """GET /api/runtime/attach?gamePath=: the targets x64dbg or Cheat Engine can take."""
    from viwo.core.capture.attach import listing

    if isinstance(game := existing(q, "gamePath", "Game folder"), dict):
        return game
    problems: list[str] = []
    targets = listing(app.rt, game, problems)
    enabled = "capture" in app.rt.config.features
    return {"success": True, "targets": targets, "enabled": enabled, "problems": problems}


def run_attach(app: App, d: dict) -> dict:
    """POST /api/runtime/attach {gamePath, targetKey, tool?, pid?, confirm?}: the tool starts
    as a tracked child (no job: it runs until the user closes it)."""
    from viwo.core.capture.attach import AttachRequest, attach

    if isinstance(game := existing(d, "gamePath", "Game folder"), dict):
        return game
    key = str(d.get("targetKey", "")).strip()
    if not key:
        return failure(ViwoError("invalid_request", "targetKey is required"))
    try:
        _ours(app)  # the Cheat Engine table is written under the workspace
        pid = _number(d, "pid", int, 0)
    except ViwoError as exc:
        return failure(exc)
    req = AttachRequest(
        game, app.workspace, key, str(d.get("tool", "")), pid, bool(d.get("confirm"))
    )
    return {"success": True, **attach(app.rt, req)}


CAPTURE_GET: dict[str, Callable[[App, dict], Any]] = {
    "/api/browse-file": browse_file,
    "/api/runtime/attach": attach_targets,
}
CAPTURE_POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/capture/warnings": capture_warnings,
    "/api/capture": run_capture,
    "/api/runtime/attach": run_attach,
    **runtime_routes("/api/runtime/"),
}
