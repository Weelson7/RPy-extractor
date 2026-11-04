"""Byte ranges for /preview/ (media seeks): parsing a Range header and copying a span."""

from __future__ import annotations

import re

RANGE = re.compile(r"bytes=(\d*)-(\d*)")

# The player seeked away or the tab closed mid-stream: normal, never worth a traceback.
ABORTED = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


def byte_range(header: str, size: int) -> tuple[int, int] | None:
    """Parse a single "bytes=a-b" range; None means "send everything", (-1, -1) unsatisfiable."""
    match = RANGE.fullmatch(header.strip())
    if not match or not any(match.groups()):
        return None
    first, last = match.groups()
    if not first:  # suffix range: the last N bytes
        start, end = max(0, size - int(last)), size - 1
    else:
        start, end = int(first), min(size - 1, int(last)) if last else size - 1
    return (start, end) if start <= end and start < size else (-1, -1)


def _copy(src, dst, remaining: int) -> None:
    try:
        while remaining > 0:
            chunk = src.read(min(1 << 16, remaining))
            if not chunk:
                return
            dst.write(chunk)
            remaining -= len(chunk)
    except ABORTED:
        pass
