"""JSON route handlers for the web UI (v1-compatible shapes; doc 4.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.core.curation import sorting, trash
from viwo.core.merger import media
from viwo.core.merger.build import build

from .app import App


def safe(fn: Callable[[], dict]) -> dict:
    try:
        return fn()
    except ViwoError as exc:
        return {"success": False, "error": exc.message, "code": exc.code, "hint": exc.hint}


def _int(query: dict, key: str, default: int) -> int:
    try:
        return int((query.get(key) or [default])[0])
    except (TypeError, ValueError):
        return default


def status(app: App, q: dict) -> dict:
    return {
        "success": True,
        **trash.summary(app.workspace),
        "assetPath": str(app.workspace),
        "allExtensions": trash.all_extensions(app.workspace),
    }


def workspace(app: App, q: dict) -> dict:
    return {
        "success": True,
        "path": str(app.workspace),
        "isDefault": app.workspace.resolve() == app.server.workspace.resolve(),
        "owned": app.workspace.is_dir() and ws.has_marker(app.workspace),
    }


def open_workspace(app: App, d: dict) -> dict:
    path = Path(str(d.get("path", ""))).expanduser()
    if path.resolve() == app.server.workspace.resolve():
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        return {"success": False, "error": f"Folder not found: {path}", "code": "not_found"}
    app.set_workspace(path.resolve())
    return workspace(app, {})


def dependencies(app: App, q: dict) -> dict:
    return {
        "success": True,
        "requiredOk": True,
        "dependencies": app.rt.dependency_report(),
        "problems": list(app.rt.problems),
    }


def pick_folder(app: App, q: dict) -> dict:
    start = Path((q.get("initialPath") or [""])[0] or Path.home()).expanduser()
    chosen = app.rt.os.shell.pick_folder("Select folder", start if start.exists() else None)
    if chosen is None:
        return {"success": False, "cancelled": True, "error": "No folder selected"}
    return {"success": True, "path": str(chosen)}


def _group(kind: str, op) -> Callable[[App, dict], dict]:
    def handler(app: App, d: dict) -> dict:
        folder = str(d.get("folder", ""))

        def run() -> dict:
            ok, message = op(app.workspace, folder)
            app.log(f"[WORKSPACE] {message}")
            result = {
                "success": ok,
                "message": message,
                "type": kind,
                "folder": folder,
                "logs": [message],
            }
            return {**result, "summary": trash.summary(app.workspace)} if ok else result

        return app.locked(run)

    return handler


def clear_trash(app: App, d: dict) -> dict:
    def run() -> dict:
        count, logs = trash.clear(app.workspace)
        return {
            "success": True,
            "type": "clear_all_trash",
            "cleared": count,
            "logs": logs,
            "summary": trash.summary(app.workspace),
        }

    return app.locked(run)


def keep_selected(app: App, d: dict) -> dict:
    keep = {str(e).lstrip(".") for e in d.get("selectedExts") or []}

    def run() -> dict:
        moved = [e for e in trash.kept(app.workspace) if e not in keep]
        for ext in moved:
            trash.trash_group(app.workspace, ext)
        return {
            "success": True,
            "message": f"Kept {len(keep)} types, moved {len(moved)} to trash",
            "summary": trash.summary(app.workspace),
        }

    return app.locked(run)


def _sorting(op, *keys: str) -> Callable[[App, dict], dict]:
    def handler(app: App, d: dict) -> dict:
        args = [str(d.get(k, "")) for k in keys]
        extra = (app.rt.os.fs,) if op is sorting.rename else ()
        return app.locked(lambda: safe(lambda: op(app.workspace, *args, app.history, *extra)))

    return handler


def save_remaining(app: App, d: dict) -> dict:
    target = Path(str(d.get("destinationPath", "")).strip() or ".").expanduser().resolve()
    paths = [str(p) for p in d.get("paths") or []]
    if d.get("all"):  # every remaining asset, not only the visible page
        paths = [sorting.encode(app.workspace, p) for p in sorting.asset_files(app.workspace)]
    return app.locked(lambda: safe(lambda: sorting.save_remaining(app.workspace, paths, target)))


def assets_window(app: App, q: dict) -> dict:
    return sorting.list_window(app.workspace, _int(q, "offset", 0), _int(q, "limit", 100))


def asset_preview(app: App, q: dict) -> dict:
    return safe(lambda: sorting.preview(app.workspace, (q.get("path") or [""])[0]))


def open_folder(app: App, d: dict) -> dict:
    path = Path(str(d.get("path", ""))).expanduser()
    ok, error = app.rt.os.shell.open_folder(path)
    return {"success": ok, "path": str(path)} if ok else {"success": False, "error": error}


def merger_state(app: App, q: dict) -> dict:
    return {
        "success": True,
        "workingDir": str(app.workspace),
        "mergerDir": str(app.server.merged),
        "defaultPattern": media.PATTERNS[0],
        "defaultTransition": "diapo",
        "defaultDiapoDelay": 3.0,
        "defaultFadeCrossTime": 0.7,
        "defaultEndFadeoutTime": 0.0,
        "defaultEndLastImageTime": 0.0,
        "supportedOverlayAudioExts": sorted(media.AUDIO),
        "encoder": app.rt.bindings["media.encode"].main or None,
    }


def _workdir(app: App, d: dict) -> Path:
    raw = str(d.get("workingDir", "")).strip()
    return Path(raw).expanduser().resolve() if raw and Path(raw).is_dir() else app.workspace


def merger_list(app: App, d: dict) -> dict:
    folder = _workdir(app, d)
    pattern = str(d.get("namingPattern", media.PATTERNS[0])).lower()
    pattern = pattern if pattern in media.PATTERNS else media.PATTERNS[0]
    raw = d.get("allowedExts")
    allowed = (
        {f".{str(e).lower().lstrip('.')}" for e in raw if str(e).strip()}
        if isinstance(raw, list)
        else None
    )
    entries = media.list_entries(folder, allowed or None)
    groups = media.candidates(entries, pattern, include_files=bool(d.get("includeFiles")))
    offset, limit = (
        max(0, int(d.get("offset", 0) or 0)),
        max(1, min(300, int(d.get("limit", 120) or 120))),
    )
    return {
        "success": True,
        "workingDir": str(folder),
        "namingPattern": pattern,
        "extensions": media.summarize(media.list_entries(folder)),
        "candidates": groups[offset : offset + limit],
        "fileCount": len(entries),
        "offset": offset,
        "limit": limit,
        "totalCount": len(groups),
        "truncated": offset + limit < len(groups),
        "supportedMediaExts": sorted(media.TIMELINE),
    }


def merger_build(app: App, d: dict) -> dict:
    folder = _workdir(app, d)
    return app.locked_job(
        "merge", folder, lambda sink: build(app.rt, folder, app.server.merged, d, sink)
    )


def merger_overlay(app: App, d: dict) -> dict:
    start = Path(str(d.get("initialPath", "")) or Path.home()).expanduser()
    patterns = [f"*{e}" for e in sorted(media.AUDIO)]
    chosen = app.rt.os.shell.pick_file("Select overlay sound", start, patterns)
    if chosen is None:
        return {"success": False, "cancelled": True, "error": "No file selected"}
    if chosen.suffix.lower() not in media.AUDIO:
        return {"success": False, "error": "Selected file is not a supported audio format"}
    return {"success": True, "path": str(chosen.resolve())}


GET: dict[str, Callable[[App, dict], Any]] = {
    "/api/status": status,
    "/api/workspace": workspace,
    "/api/dependencies": dependencies,
    "/api/browse-folder": pick_folder,
    "/api/assets-window": assets_window,
    "/api/assets-window-preview": asset_preview,
    "/api/media-merger/state": merger_state,
    "/api/logs": lambda app, q: {"logs": app.logs()},
}
POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/extract": lambda app, d: app.extract(d),
    "/api/workspace": open_workspace,
    "/api/trash": _group("move_to_trash", trash.trash_group),
    "/api/restore": _group("restore_from_trash", trash.restore_group),
    "/api/delete": _group("delete_from_trash", trash.delete_group),
    "/api/clear-trash": clear_trash,
    "/api/keep-selected": keep_selected,
    "/api/sort-keep": _sorting(sorting.keep, "path"),
    "/api/sort-trash": _sorting(sorting.trash_item, "path"),
    "/api/sort-undo": _sorting(sorting.undo),
    "/api/sort-rename": _sorting(sorting.rename, "path", "newName"),
    "/api/save-remaining-assets": save_remaining,
    "/api/open-folder": open_folder,
    "/api/logs/clear": lambda app, d: (app.clear_logs(), {"success": True})[1],
    "/api/media-merger/list": merger_list,
    "/api/media-merger/build": merger_build,
    "/api/media-merger/browse-overlay": merger_overlay,
}
