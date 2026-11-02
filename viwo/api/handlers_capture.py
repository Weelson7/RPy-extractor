"""10 CAPTURE: file picker, the warnings before a capture, and the capture itself as a job."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from viwo.core.capture import CaptureRequest, capture
from viwo.core.capture.policy import CONFIRMATION, warnings_for
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import detect_all
from viwo.core.workspace import claim

from .app import App


def browse_file(app: App, q: dict) -> dict:
    start = Path((q.get("initialPath") or [""])[0] or Path.home()).expanduser()
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


def _sensitive(app: App, game: Path) -> list[str]:
    found = detect_all(app.rt, FolderProbe(game))
    plugins = app.rt.plugins
    return [
        p for p, d in found.items() if d.confidence >= 0.5 and plugins[p].manifest.tos_sensitive
    ]


def capture_warnings(app: App, d: dict) -> dict:
    """What the user should know before capturing this game: information, never a block."""
    game = Path(str(d.get("gamePath", "")).strip())
    if not str(game) or not game.is_dir():
        return {"success": False, "error": f"Game folder not found: {game}", "code": "not_found"}
    binding = app.rt.bindings.get("capture.gpu")
    return {
        "success": True,
        "warnings": warnings_for(game, _sensitive(app, game)),
        "confirmation": CONFIRMATION,
        "enabled": "capture" in app.rt.config.features,
        "backend": binding.main if binding is not None and binding.bound else "",
    }


def run_capture(app: App, d: dict) -> dict:
    """Capture into the active workspace as a job (kind "capture"); error codes pass through."""
    game = Path(str(d.get("gamePath", "")).strip())
    exe = Path(str(d.get("exePath", "")).strip())
    if not str(game) or not game.is_dir():
        return {"success": False, "error": f"Game folder not found: {game}", "code": "not_found"}
    if not str(exe) or not exe.is_file():
        return {"success": False, "error": f"Executable not found: {exe}", "code": "not_found"}
    workspace = app.workspace
    if not workspace.exists() or not any(workspace.iterdir()):
        claim(workspace)  # the lock file lands inside it before capture() looks at it
    request = CaptureRequest(game, exe, workspace, bool(d.get("confirmed")))

    def run(sink, cancel) -> dict:
        return {"success": True, **capture(app.rt, request, sink, cancel)}

    return app.locked_job("capture", workspace, run)


CAPTURE_GET: dict[str, Callable[[App, dict], Any]] = {"/api/browse-file": browse_file}
CAPTURE_POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/capture/warnings": capture_warnings,
    "/api/capture": run_capture,
}
