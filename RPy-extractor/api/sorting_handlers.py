"""Sorting window API handlers, now served by viwo.core.curation.sorting."""
from pathlib import Path

from models import AppConfig, SESSIONS
from viwo.api.legacy import locked, runtime
from viwo.contracts.errors import ViwoError
from viwo.core.curation import sorting

from .common import assets_dir, get_sort_history_session


def _call(fn, *args) -> dict:
    try:
        return fn(*args)
    except ViwoError as exc:
        return {"success": False, "error": exc.message, "code": exc.code}


def _with_history(app_config: AppConfig, fn, *args) -> dict:
    workspace = assets_dir(app_config)

    def run() -> dict:
        session, history = get_sort_history_session()
        result = _call(fn, workspace, *args, history)
        SESSIONS.set_current(session)
        return result

    return locked(workspace, run)


def get_assets_for_preview(app_config: AppConfig, ext_folder: str) -> dict:
    """First 100 files of one extension group."""
    workspace = assets_dir(app_config)
    folder = workspace / ext_folder
    if not folder.is_dir() or ext_folder.startswith("."):
        return {"success": False, "error": f"Folder not found: {ext_folder}", "assets": []}
    files = sorted((p for p in folder.rglob("*") if p.is_file()), key=lambda p: p.name)[:100]
    assets = [{"name": p.name, "path": sorting.encode(workspace, p), "size": p.stat().st_size}
              for p in files]
    return {"success": True, "assets": assets}


def list_assets_for_sorting_window(app_config: AppConfig, max_assets: int = 100, offset: int = 0) -> dict:
    return sorting.list_window(assets_dir(app_config), offset, max_assets)


def sort_keep_asset(app_config: AppConfig, encoded_path: str) -> dict:
    return _with_history(app_config, sorting.keep, encoded_path)


def sort_trash_asset(app_config: AppConfig, encoded_path: str) -> dict:
    return _with_history(app_config, sorting.trash_item, encoded_path)


def sort_undo_last_action(app_config: AppConfig) -> dict:
    return _with_history(app_config, sorting.undo)


def sort_rename_asset(app_config: AppConfig, encoded_path: str, new_name: str) -> dict:
    workspace = assets_dir(app_config)

    def run() -> dict:
        session, history = get_sort_history_session()
        result = _call(sorting.rename, workspace, encoded_path, new_name, history, runtime().os.fs)
        SESSIONS.set_current(session)
        return result

    return locked(workspace, run)


def save_remaining_assets(app_config: AppConfig, encoded_paths: list[str], destination_path: str) -> dict:
    if not destination_path.strip():
        return {"success": False, "error": "Destination path is required"}
    workspace = assets_dir(app_config)
    destination = Path(destination_path).expanduser().resolve()
    return locked(workspace, lambda: _call(sorting.save_remaining, workspace, encoded_paths, destination))


def get_asset_preview_content(app_config: AppConfig, encoded_path: str, max_lines: int = 50) -> dict:
    return _call(sorting.preview, assets_dir(app_config), encoded_path, max_lines)
