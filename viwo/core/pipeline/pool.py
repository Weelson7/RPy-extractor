"""The worker budget of every parallel stage (owner): 80 % of the logical processors this
process may use, counted when asked, on any OS; VIWO_WORKERS overrides. One number for the
whole pipeline, so stages never oversubscribe the machine."""

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Iterator


def workers() -> int:
    if os.environ.get("VIWO_WORKERS", "").isdigit():
        return max(1, int(os.environ["VIWO_WORKERS"]))
    count = getattr(os, "process_cpu_count", os.cpu_count)() or 1  # 3.13+: the affinity's
    return max(1, int(count * 0.8))


def each(fn: Callable, items: Iterable, cancel=None) -> Iterator:
    """fn over items on the worker pool, results in the items' order (so what follows is the
    same on every run); a cancel drops what has not started and ends the results early."""
    with ThreadPoolExecutor(workers()) as pool:
        for result in pool.map(fn, items):
            if cancel is not None and cancel.cancelled:
                pool.shutdown(wait=True, cancel_futures=True)
                return
            yield result
