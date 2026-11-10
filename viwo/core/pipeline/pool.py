"""The worker budget of every parallel stage (owner): 80 % of the logical processors this
process may use, counted when asked, on any OS; VIWO_WORKERS overrides. One number for the
whole pipeline, so stages never oversubscribe the machine."""

import contextlib
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Iterator


def workers() -> int:
    if os.environ.get("VIWO_WORKERS", "").isdigit():
        return max(1, int(os.environ["VIWO_WORKERS"]))
    count = getattr(os, "process_cpu_count", os.cpu_count)() or 1  # 3.13+: the affinity's
    return max(1, int(count * 0.8))


_SKIPPED = object()


def each(fn: Callable, items: Iterable, cancel=None, count: int = 0) -> Iterator:
    """fn over items on the worker pool (`count` workers when given), results in the items'
    order (so what follows is the same on every run). After a cancel nothing more starts; what
    had started is still handed on, so no finished work is lost. At most 2 x count results
    wait for the reader: memory stays bounded."""
    stopped = lambda: cancel is not None and cancel.cancelled  # noqa: E731
    guarded = lambda item: _SKIPPED if stopped() else fn(item)  # noqa: E731
    count, ahead = count or workers(), deque()
    with ThreadPoolExecutor(count) as pool:
        try:
            for item in items:
                if stopped():
                    break
                ahead.append(pool.submit(guarded, item))
                if len(ahead) >= count * 2:
                    if (result := ahead.popleft().result()) is _SKIPPED:
                        return
                    yield result
            while ahead:
                if (result := ahead.popleft().result()) is _SKIPPED:
                    return
                yield result
        finally:
            for future in ahead:
                future.cancel()


PATIENCE = 15.0  # seconds a large ask lets smaller ones pass it


class Budget:
    """ViWo's share of the machine's memory, handed out to the tools that run at once (doc 9.2):
    a run holds what its cap allows it to take and waits while the share is out, so however
    many run, together they cannot ask for more than the share. An ask that fits goes ahead
    of a larger one still waiting, until that one has waited PATIENCE: then nothing passes
    it, so a large run is never put off for ever and a line of small ones never stands idle
    behind it."""

    def __init__(self, share: int) -> None:
        self.share, self._free, self._turn = share, share, threading.Condition()
        self._line: list[list] = []  # [since, amount] of those waiting, in the order asked

    def _may(self, mine: list) -> bool:
        late = time.monotonic() - PATIENCE
        ahead = self._line[: self._line.index(mine)]
        return self._free >= mine[1] and not any(since <= late for since, _ in ahead)

    @contextlib.contextmanager
    def hold(self, amount: int):
        amount = min(amount, self.share)
        mine = [time.monotonic(), amount]
        with self._turn:
            self._line.append(mine)
            while not self._may(mine):
                self._turn.wait(0.5)
            self._line.remove(mine)
            self._free -= amount
            self._turn.notify_all()  # the next in line may fit beside this one
        try:
            yield
        finally:
            with self._turn:
                self._free += amount
                self._turn.notify_all()


_BUDGETS: dict[int, Budget] = {}


def budget(rt) -> Budget:
    """The one budget of this process: memory_limit percent of the machine (50 when the owner
    lifted ViWo's own ceiling: tools are still scheduled), 8 GB when the machine cannot tell."""
    total = rt.os.memory_bytes() or 16 << 30
    share = total * (rt.config.memory_limit or 50) // 100
    return _BUDGETS.setdefault(share, Budget(share))
