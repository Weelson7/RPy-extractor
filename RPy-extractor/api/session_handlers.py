"""Session and initial state API handlers."""
from pathlib import Path

from models import AppConfig, SESSIONS
from sorting import get_summary, list_all_extensions
from .common import set_session_asset_path, resume_assets_candidate_paths


def browse_folder(initial_path: str = "") -> dict:
    """Open native folder picker and return selected path."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        initial_dir = Path(initial_path).expanduser() if initial_path else Path.home()
        if not initial_dir.exists() or not initial_dir.is_dir():
            probe = initial_dir
            while True:
                parent = probe.parent
                if probe.exists() and probe.is_dir():
                    break
                if parent == probe:
                    probe = Path.home()
                    break
                probe = parent
            initial_dir = probe

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        selected = filedialog.askdirectory(
            initialdir=str(initial_dir),
            title="Select Game Folder",
            mustexist=True,
        )
        root.destroy()

        if not selected:
            return {
                "success": False,
                "cancelled": True,
                "error": "Folder selection cancelled",
            }

        return {
            "success": True,
            "path": selected,
        }
    except Exception as exc:
        return {
            "success": False,
            "cancelled": False,
            "error": f"Could not open folder dialog: {exc}",
        }


def get_initial_state(app_config: AppConfig) -> dict:
    """Get initial UI state."""
    return {
        "step1": {
            "gamePath": "",
            "status": "idle",
        },
        "step2": {
            "extensions": [],
            "status": "scan_first",
            "detectedExtensions": [],
        },
        "step3": {
            "keptByExt": {},
            "trashedByExt": {},
            "allExtensions": [],
            "status": "no_extraction",
        },
        "logs": [],
        "appConfig": {
            "host": app_config.host,
            "port": app_config.port,
            "tempPath": str(app_config.temp_path),
            "mergerDir": str(app_config.merger_dir),
        },
    }


def get_session_state(app_config: AppConfig) -> dict:
    """Get current session state."""
    session = SESSIONS.get_current()
    if not session:
        return {
            "hasSession": False,
            "step1": {"gamePath": "", "status": "idle"},
            "step2": {"extensions": [], "status": "scan_first", "detectedExtensions": []},
            "step3": {"status": "no_extraction"},
        }

    return {
        "hasSession": True,
        "step1": session.get("step1", {}),
        "step2": session.get("step2", {}),
        "step3": session.get("step3", {}),
    }


def resume_session(app_config: AppConfig, game_path: str) -> dict:
    """Resume extraction with new or existing path."""
    try:
        for candidate in resume_assets_candidate_paths(app_config):
            if candidate.exists() and candidate.is_dir():
                set_session_asset_path(candidate)
                summary = get_summary(candidate)
                all_exts = list_all_extensions(candidate)
                return {
                    "success": True,
                    "assets_exist": True,
                    "gamePath": game_path,
                    "assetPath": str(candidate),
                    "summary": summary,
                    "allExtensions": all_exts,
                }

        if game_path:
            game_root = Path(game_path)
            if not game_root.exists():
                return {
                    "success": False,
                    "error": f"Path does not exist: {game_path}",
                }

        fallback_path = app_config.temp_path / app_config.output_dir_name
        return {
            "success": True,
            "assets_exist": False,
            "gamePath": game_path,
            "assetPath": str(fallback_path),
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }
