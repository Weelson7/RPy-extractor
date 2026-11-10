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


def each(fn: Callable, items: Iterable, cancel=None, count: int = 0) -> Iterator:
    """fn over items on the worker pool (`count` workers when given), results in the items'
    order (so what follows is the same on every run); after a cancel the result in hand is
    still handed on, then what has not started is dropped and the results end."""
    count, ahead = count or workers(), deque()
    with ThreadPoolExecutor(count) as pool:
        try:  # at most 2 x count results wait for the reader: memory stays bounded
            for item in items:
                if cancel is not None and cancel.cancelled:
                    return  # nothing starts after a cancel
                ahead.append(pool.submit(fn, item))
                if len(ahead) >= count * 2:
                    yield ahead.popleft().result()
                    if cancel is not None and cancel.cancelled:
                        return
            while ahead:
                yield ahead.popleft().result()
                if cancel is not None and cancel.cancelled:
                    return
        finally:
            for future in ahead:
                future.cancel()
