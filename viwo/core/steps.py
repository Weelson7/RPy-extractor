"""A named step of a long job: throttled "label: i / N" events plus one final line."""

from __future__ import annotations

from viwo.contracts.errors import ViwoError
from viwo.contracts.types import ProgressEvent

from .pipeline.ticker import Ticker


def teller(sink, stage: str, level: str = "info", source: str = "core"):
    """`say(message)` for one stage, or None without a sink: the ad-hoc lambdas, once."""
    if sink is None:
        return None
    return lambda message: sink(ProgressEvent(message, level, source, stage))


def tell(sink, message: str, stage: str, level: str = "info") -> None:
    """One core event, when there is a sink."""
    if sink is not None:
        sink(ProgressEvent(message, level, "core", stage))


class Step:
    def __init__(self, sink, stage: str, label: str, total: int = 0) -> None:
        self.sink, self.stage, self.label, self.total = sink, stage, label, total
        self.ticker = Ticker(self.tell if sink else None, label, total)

    def tell(self, message: str) -> None:
        if self.sink is not None:
            self.sink(ProgressEvent(message, "info", "core", self.stage))

    def tick(self, cancel=None) -> None:
        if cancel is not None and cancel.cancelled:
            raise ViwoError("cancelled", f"{self.stage} cancelled")
        self.ticker.tick()

    def done(self, count: int | None = None) -> None:
        n = self.ticker.done if count is None else count
        self.tell(f"{self.label} {n:,}" + (f" / {self.total:,}" if self.total else ""))
