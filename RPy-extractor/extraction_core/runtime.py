"""Runtime helpers for extraction core."""
import subprocess
from pathlib import Path
from typing import Callable

from logging_utils import emit_log


def tlog(message: str) -> None:
    """Log with timestamp."""
    emit_log(message)


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run subprocess and capture output."""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def command_exists(name: str) -> bool:
    """Check if command exists."""
    import shutil
    return shutil.which(name) is not None


def log_append(logs: list[str], message: str, progress: Callable[[str], None] | None = None) -> None:
    """Add to log and call progress callback."""
    logs.append(message)
    if progress:
        progress(message)
