"""Runtime helpers for legacy code."""
from logging_utils import emit_log


def tlog(message: str) -> None:
    """Log with timestamp."""
    emit_log(message)
