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


def get_sort_history_session() -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Get session and mutable sort history list."""
    session = SESSIONS.get_current() or {}
    history = session.get("sortingHistory")
    if not isinstance(history, list):
        history = []
    session["sortingHistory"] = history
    return session, history


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
