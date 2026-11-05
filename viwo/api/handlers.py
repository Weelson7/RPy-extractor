"""JSON route handlers for the web UI (v1-compatible shapes; doc 4.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.core.curation import sorting, trash
from viwo.core.merger import media
from viwo.core.merger.build import Settings, build

from .app import App, failure, path_param, picked, safe
from .plugin_assets import ui_modules

DEFAULTS = Settings()  # the merger's own defaults, once


def _int(query: dict, key: str, default: int) -> int:
    try:
        return int(query.get(key, default))
    except (TypeError, ValueError):
        return default


def status(app: App, q: dict) -> dict:
    folder = app.workspace  # every handler reads it once: it can be switched concurrently
    return {
        "success": True,
        **trash.summary(folder),
        "assetPath": str(folder),
        "allExtensions": trash.all_extensions(folder),
    }


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


def dependencies(app: App, q: dict) -> dict:
    return {
        "success": True,
        "requiredOk": True,
        "dependencies": app.rt.dependency_report(),
        "problems": list(app.rt.problems),
    }


def pick_folder(app: App, q: dict) -> dict:
    start = Path(q.get("initialPath") or Path.home()).expanduser()
    chosen = app.rt.os.shell.pick_folder("Select folder", start if start.exists() else None)
    return picked(chosen, "folder")


def _group(kind: str, op) -> Callable[[App, dict], dict]:
    def handler(app: App, d: dict) -> dict:
        folder, work = str(d.get("folder", "")), app.workspace

        def run() -> dict:
            ok, message = op(work, folder)
            app.log(f"[WORKSPACE] {message}")
            result = {
                "success": ok,
                "message": message,
                "type": kind,
                "folder": folder,
                "logs": [message],
            }
            return {**result, "summary": trash.summary(work)} if ok else result

        return app.locked(run, work)

    return handler


def clear_trash(app: App, d: dict) -> dict:
    folder = app.workspace

    def run() -> dict:
        count, logs = trash.clear(folder)
        return {
            "success": True,
            "type": "clear_all_trash",
            "cleared": count,
            "logs": logs,
            "summary": trash.summary(folder),
        }

    return app.locked(run, folder)


def keep_selected(app: App, d: dict) -> dict:
    keep = {str(e).lstrip(".") for e in d.get("selectedExts") or []}
    folder = app.workspace

    def run() -> dict:
        moved = [e for e in trash.kept(folder) if e not in keep]
        for ext in moved:
            trash.trash_group(folder, ext)
        return {
            "success": True,
            "message": f"Kept {len(keep)} types, moved {len(moved)} to trash",
            "summary": trash.summary(folder),
        }

    return app.locked(run, folder)


def gated(feature: str, fn: Callable[[App, dict], dict]) -> Callable[[App, dict], dict]:
    """A route behind a [startup] features switch: refused, with the way to switch it on."""
    from viwo.core.context import require

    def handler(app: App, d: dict) -> dict:
        try:
            require(app.rt, feature, feature)
        except ViwoError as exc:
            return failure(exc)
        return fn(app, d)

    return handler


def _sorting(op, *keys: str) -> Callable[[App, dict], dict]:
    def handler(app: App, d: dict) -> dict:
        args, folder = [str(d.get(k, "")) for k in keys], app.workspace
        extra = (app.rt.os.fs,) if op is sorting.rename else ()
        return app.locked(lambda: safe(lambda: op(folder, *args, app.history, *extra)), folder)

    return handler


def save_remaining(app: App, d: dict) -> dict:
    raw = Path(str(d.get("destinationPath", "")).strip()).expanduser()
    if not raw.is_absolute():  # "" or a relative path would land in the server's own folder
        return failure(ViwoError("invalid_request", "give an absolute destinationPath"))
    target = raw.resolve()
    paths, folder = [str(p) for p in d.get("paths") or []], app.workspace
    if d.get("all"):  # every remaining asset, not only the visible page
        paths = [sorting.encode(folder, p) for p in sorting.asset_files(folder)]
    return app.locked(lambda: safe(lambda: sorting.save_remaining(folder, paths, target)), folder)


def assets_window(app: App, q: dict) -> dict:
    """One page of files plus the type counts of the whole workspace (a cheap listing)."""
    folder = app.workspace
    window = sorting.list_window(folder, _int(q, "offset", 0), _int(q, "limit", 100))
    counts: dict[str, int] = {}
    for path in sorting.asset_files(folder) if folder.is_dir() else []:
        kind = sorting.media_type(path.suffix.lower())
        counts[kind] = counts.get(kind, 0) + 1
    return {**window, "typeCounts": counts, "total": sum(counts.values())}


def asset_preview(app: App, q: dict) -> dict:
    return safe(lambda: sorting.preview(app.workspace, q.get("path", "")))


def open_folder(app: App, d: dict) -> dict:
    path = path_param(d, "path")
    if path is None:
        return failure(ViwoError("not_found", "give the folder as an absolute path"))
    ok, error = app.rt.os.shell.open_folder(path)
    if ok:
        return {"success": True, "path": str(path)}
    return {"success": False, "error": error, "code": "failed", "hint": "open the folder by hand"}


def merger_state(app: App, q: dict) -> dict:
    return {
        "success": True,
        "workingDir": str(app.workspace),  # one read
        "mergerDir": str(app.server.merged),
        "defaultPattern": media.PATTERNS[0],
        "defaultTransition": DEFAULTS.transition,
        "defaultDiapoDelay": DEFAULTS.delay,
        "defaultFadeCrossTime": DEFAULTS.cross,
        "defaultEndFadeoutTime": DEFAULTS.fadeout,
        "defaultEndLastImageTime": DEFAULTS.hold_last,
        "supportedOverlayAudioExts": sorted(media.AUDIO),
        "encoder": app.rt.bindings["media.encode"].main or None,
    }


def _workdir(app: App, d: dict) -> Path:
    """The folder asked for (absolute, existing), or the workspace when none was given; a
    mistyped one is said, never swapped for the workspace."""
    if not str(d.get("workingDir", "") or "").strip():
        return app.workspace
    raw = path_param(d, "workingDir")
    if raw is None or not raw.is_dir():
        raise ViwoError("not_found", f"no such folder: {d.get('workingDir')}")
    return raw.resolve()


def merger_list(app: App, d: dict) -> dict:
    try:
        folder = _workdir(app, d)
    except ViwoError as exc:
        return failure(exc)
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
    """Reads the folder, writes the video to [server] merged; only trashAfterBuild writes into
    the folder, and that needs a ViWo workspace."""
    try:
        folder = _workdir(app, d)
    except ViwoError as exc:
        return failure(exc)
    return app.locked_job(
        "merge",
        folder,
        lambda sink, cancel: build(app.rt, folder, app.server.merged, d, sink),
        writes=bool(d.get("trashAfterBuild")),
    )


def merger_overlay(app: App, d: dict) -> dict:
    start = Path(str(d.get("initialPath", "")) or Path.home()).expanduser()
    patterns = [f"*{e}" for e in sorted(media.AUDIO)]
    chosen = app.rt.os.shell.pick_file("Select overlay sound", start, patterns)
    if chosen is not None and chosen.suffix.lower() not in media.AUDIO:
        hint = "pick an .ogg, .mp3, .wav, .flac, .m4a or .opus file"
        return failure(ViwoError("invalid_request", "not a supported audio format", hint=hint))
    return picked(chosen.resolve() if chosen else None, "file")


GET: dict[str, Callable[[App, dict], Any]] = {
    "/api/status": status,
    "/api/workspace": workspace,
    "/api/dependencies": dependencies,
    "/api/browse-folder": pick_folder,
    "/api/assets-window": assets_window,
    "/api/assets-window-preview": asset_preview,
    "/api/media-merger/state": merger_state,
    "/api/logs": lambda app, q: {"logs": app.logs()},
    "/api/ui-modules": lambda app, q: {"success": True, "modules": ui_modules(app.rt)},
}


POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/extract": lambda app, d: app.extract(d),
    "/api/workspace": open_workspace,
    "/api/trash": _group("move_to_trash", trash.trash_group),
    "/api/restore": _group("restore_from_trash", trash.restore_group),
    "/api/delete": _group("delete_from_trash", trash.delete_group),
    "/api/clear-trash": gated("sorting", clear_trash),
    "/api/keep-selected": gated("sorting", keep_selected),
    "/api/sort-keep": gated("sorting", _sorting(sorting.keep, "path")),
    "/api/sort-trash": gated("sorting", _sorting(sorting.trash_item, "path")),
    "/api/sort-undo": gated("sorting", _sorting(sorting.undo)),
    "/api/sort-rename": gated("sorting", _sorting(sorting.rename, "path", "newName")),
    "/api/save-remaining-assets": gated("sorting", save_remaining),
    "/api/open-folder": open_folder,
    "/api/logs/clear": lambda app, d: (app.clear_logs(), {"success": True})[1],
    "/api/media-merger/list": gated("merger", merger_list),
    "/api/media-merger/build": gated("merger", merger_build),
    "/api/media-merger/browse-overlay": merger_overlay,
}


from .handlers_analysis import ANALYSIS_GET, ANALYSIS_POST  # noqa: E402
from .handlers_capture import CAPTURE_GET, CAPTURE_POST  # noqa: E402
from .handlers_jobs import JOBS_POST  # noqa: E402
from .handlers_runbooks import RUNBOOKS_GET, RUNBOOKS_POST  # noqa: E402
from .handlers_settings import SETTINGS_GET, SETTINGS_POST  # noqa: E402
from .handlers_system import SYSTEM_GET, SYSTEM_POST  # noqa: E402
from .handlers_tools import TOOL_GET, TOOL_POST  # noqa: E402  (tables merged last)

for table in (TOOL_GET, CAPTURE_GET, SETTINGS_GET, SYSTEM_GET, ANALYSIS_GET, RUNBOOKS_GET):
    GET.update(table)
for table in (TOOL_POST, CAPTURE_POST, SETTINGS_POST, SYSTEM_POST, JOBS_POST, ANALYSIS_POST):
    POST.update(table)
POST.update(RUNBOOKS_POST)
