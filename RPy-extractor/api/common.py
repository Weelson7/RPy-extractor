"""Shared helpers for API handler modules."""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

from models import AppConfig, SESSIONS


def assets_dir(app_config: AppConfig) -> Path:
    """Resolve active assets directory path."""
    session = SESSIONS.get_current()
    if isinstance(session, dict):
        current_asset_path = session.get("assetPath")
        if isinstance(current_asset_path, str) and current_asset_path.strip():
            path = Path(current_asset_path)
            if path.exists() and path.is_dir():
                return path

    return app_config.temp_path / app_config.output_dir_name


def set_session_asset_path(path: Path) -> None:
    """Persist active assets path in current session."""
    session = SESSIONS.get_current() or {}
    session["assetPath"] = str(path)
    SESSIONS.set_current(session)


def resume_assets_candidate_paths(app_config: AppConfig) -> list[Path]:
    """Return ordered candidate paths for resume."""
    project_assets = Path(__file__).resolve().parent.parent / "assets"
    configured_assets = app_config.temp_path / app_config.output_dir_name

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in (project_assets, configured_assets):
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)

    return unique


def trash_operation_endpoint(
    operation: str,
    app_config: AppConfig,
    ext_folder: str,
    operation_func: Callable,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Generic helper for trash operations (move, restore, delete)."""
    if not operation or not ext_folder:
        return {
            "success": False,
            "error": f"Missing {operation} or folder parameter",
            "type": operation,
            "folder": ext_folder,
        }

    try:
        out_dir = assets_dir(app_config)
        return operation_func(out_dir, ext_folder, progress_callback)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "type": operation,
            "folder": ext_folder,
        }


def get_sort_history_session() -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Get session and mutable sort history list."""
    session = SESSIONS.get_current() or {}
    history = session.get("sortingHistory")
    if not isinstance(history, list):
        history = []
    session["sortingHistory"] = history
    return session, history


def resolve_asset_path_for_action(out_dir: Path, encoded_path: str) -> tuple[Path | None, str | None]:
    """Resolve and validate encoded asset path under active assets root."""
    if not encoded_path:
        return None, "Missing asset path"

    decoded = unquote(encoded_path)
    candidate = (out_dir / decoded).resolve()
    try:
        candidate.relative_to(out_dir.resolve())
    except Exception:
        return None, "Invalid asset path"

    if not candidate.exists() or not candidate.is_file():
        return None, f"Asset not found: {decoded}"

    return candidate, None


def open_folder_in_explorer(path: Path) -> tuple[bool, str]:
    """Open folder in the system file explorer."""
    if not path.exists() or not path.is_dir():
        return False, f"Folder not found: {path}"

    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True, ""

        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return True, ""

        subprocess.Popen(["xdg-open", str(path)])
        return True, ""
    except Exception as exc:
        return False, str(exc)
