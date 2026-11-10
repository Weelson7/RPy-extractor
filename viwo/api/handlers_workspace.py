"""The active workspace: which it is, switching to another, converting a folder (doc 4.3)."""

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.core import adopt

from .app import App, failure, path_param


def workspace(app: App, q: dict) -> dict:
    folder = app.workspace
    return {
        "success": True,
        "path": str(folder),
        "isDefault": folder.resolve() == app.server.workspace.resolve(),
        "owned": folder.is_dir() and ws.has_marker(folder),
    }


def open_workspace(app: App, d: dict) -> dict:
    path = path_param(d, "path")
    if path is None:
        return failure(ViwoError("not_found", "give the workspace as an absolute folder"))
    if path.resolve() == app.server.workspace.resolve():
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        return {"success": False, "error": f"Folder not found: {path}", "code": "not_found"}
    app.set_workspace(path.resolve())
    return workspace(app, {})


def adopt_workspace(app: App, d: dict) -> dict:
    """A folder ViWo did not create, made a workspace (doc 4.3): without `confirm` what it
    would do; with it, the conversion, and the folder becomes the active workspace."""
    path = path_param(d, "path")
    if path is None:
        return failure(ViwoError("not_found", "give the folder as an absolute path"))
    if not d.get("confirm"):
        return {"success": True, **adopt.preview(path)}
    try:
        done = adopt.adopt(path)
    except ViwoError as exc:
        return failure(exc)
    app.set_workspace(path.resolve())
    return {"success": True, **done}
