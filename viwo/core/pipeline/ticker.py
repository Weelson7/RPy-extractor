"""Throttled progress for long loops: real counts, at most one event per interval."""

import time
from typing import Callable


class Ticker:
    def __init__(
        self, say: Callable[[str], None] | None, label: str, total: int = 0, every: float = 1.0
    ):
        self.say, self.label, self.total, self.every = say, label, total, every
        self.done, self.last = 0, time.monotonic()

    def tick(self, count: int = 1, note: str = "") -> None:
        self.done += count
        now = time.monotonic()
        if self.say is not None and now - self.last >= self.every:
            self.last = now
            of = f" / {self.total:,}" if self.total else ""
            self.say(f"{self.label} {self.done:,}{of}" + (f" ({note})" if note else ""))


def clock(seconds: float) -> str:
    """A duration as a person says it: 8 s, 3 min 20 s, 1 h 02 min."""
    whole = int(round(seconds))
    if whole < 60:
        return f"{whole} s"
    if whole < 3600:
        return f"{whole // 60} min {whole % 60:02d} s"
    return f"{whole // 3600} h {whole % 3600 // 60:02d} min"
