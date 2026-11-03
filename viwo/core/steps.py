"""A named step of a long job: throttled "label: i / N" events plus one final line."""

from __future__ import annotations

from viwo.contracts.errors import ViwoError
from viwo.contracts.types import ProgressEvent

from .pipeline.ticker import Ticker


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
