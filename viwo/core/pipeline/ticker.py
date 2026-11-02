"""Throttled progress for long loops: real counts, at most one event per interval."""

from __future__ import annotations

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
