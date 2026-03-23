"""Log and filesystem utility API handlers."""
from pathlib import Path

from models import AppConfig, SESSIONS
from .common import open_folder_in_explorer


def list_all_logs(app_config: AppConfig) -> dict:
    """Get all logs from current session."""
    session = SESSIONS.get_current()
    if not session:
        return {"logs": []}

    return {"logs": session.get("logs", [])}


def clear_all_logs(app_config: AppConfig) -> dict:
    """Clear in-memory session logs used by Activity Log polling."""
    try:
        session = SESSIONS.get_current() or {}
        session["logs"] = []
        SESSIONS.set_current(session)
        return {"success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def load_log_file_entries(app_config: AppConfig, max_lines: int = 800) -> dict:
    """Load persisted log lines from the newest log file in configured logDir."""
    try:
        log_dir = app_config.log_dir.resolve()
        if not log_dir.exists() or not log_dir.is_dir():
            return {"success": False, "error": f"Log directory not found: {log_dir}"}

        candidates = sorted(
            (path for path in log_dir.glob("*.log") if path.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return {"success": True, "logs": [], "source": ""}

        source = candidates[0]
        with source.open("r", encoding="utf-8", errors="replace") as fh:
            lines = [line.rstrip("\n") for line in fh]

        if max_lines > 0:
            lines = lines[-max_lines:]

        return {
            "success": True,
            "logs": lines,
            "source": str(source),
            "count": len(lines),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def open_log_dir(app_config: AppConfig) -> dict:
    """Open configured logDir in file explorer."""
    try:
        log_dir = app_config.log_dir.resolve()
        ok, err = open_folder_in_explorer(log_dir)
        if not ok:
            return {"success": False, "error": err}
        return {"success": True, "path": str(log_dir)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def open_folder_path(path_str: str) -> dict:
    """Open arbitrary folder path in file explorer."""
    try:
        if not path_str.strip():
            return {"success": False, "error": "Folder path is required"}
        path = Path(path_str).expanduser().resolve()
        ok, err = open_folder_in_explorer(path)
        if not ok:
            return {"success": False, "error": err}
        return {"success": True, "path": str(path)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
