"""The worker budget of every parallel stage (owner): 80 % of the logical processors this
process may use, counted when asked, on any OS; VIWO_WORKERS overrides. One number for the
whole pipeline, so stages never oversubscribe the machine."""

import os
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
