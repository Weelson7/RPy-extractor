"""Shared logging helpers for console and file logging."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import threading


_LOG_LOCK = threading.Lock()
_LOG_FILE: Path | None = None


def configure_log_directory(log_dir: Path) -> Path:
    """Configure log directory and active log file path."""
    global _LOG_FILE
    log_dir.mkdir(parents=True, exist_ok=True)
    # One file per day keeps logs easy to locate and avoids excessive file churn.
    _LOG_FILE = log_dir / f"rpy-extractor-{datetime.now().strftime('%Y-%m-%d')}.log"
    return _LOG_FILE


def emit_log(message: str) -> None:
    """Emit log line to stdout and active log file (if configured)."""
    stamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)

    with _LOG_LOCK:
        if _LOG_FILE is None:
            return
        try:
            with _LOG_FILE.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")
        except OSError:
            # Never let file logging failures break app execution.
            return
