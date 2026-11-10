"""Recursive unpack loop (doc 3.1 UNPACK); keeps v1's queue/seen/subfolder behavior."""

import shutil
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import ExtractionContext

from .failover import run_with_failover
from .identify import carve, identify
from .pool import each, workers
from .ticker import Ticker

MAX_DEPTH = 10
SAID_FROM = 200  # files in one round from which identifying them is announced and counted


@dataclass
class UnpackReport:
    found: int = 0
    extracted: int = 0
    files: int = 0
    by_backend: Counter = field(default_factory=Counter)
    origins: dict[Path, str] = field(default_factory=dict)  # unpack dir -> origin label
    failures: list[str] = field(default_factory=list)


def _candidates(root: Path, skip: set[str]) -> Iterable[Path]:
    """Files under root, never through a junction or link; skip names folders inside root."""
    for path in ws.files(root):
        if not skip.intersection(p.lower() for p in path.relative_to(root).parts[:-1]):
            yield path


def files_under(root: Path, label: str, skip: set[str]) -> list[tuple[Path, str]]:
    return [(p, f"{label}:{p.relative_to(root).as_posix()}") for p in _candidates(root, skip)]


def unpack_all(
    runtime,
    items: list[tuple[Path, str]],
    out_root: Path,
    make_ctx: Callable[[str], ExtractionContext],
    cancel=None,
) -> UnpackReport:
    """items: (file, origin label). Nested archives are unpacked up to MAX_DEPTH; a cancel
    stops the queue (the stage after says it)."""
    report = UnpackReport()
    seen: set[str] = set()
    stopped = lambda: cancel is not None and cancel.cancelled  # noqa: E731
    queue, depth = list(items), 0
    while queue and not stopped():  # one round per nesting depth, in the queue's order
        nested: list[tuple[Path, str]] = []
        for (path, origin), match in zip(queue, _identified(runtime, queue, make_ctx, cancel)):
            key = runtime.os.fs.path_key(path.resolve())
            if match is None or key in seen or stopped():
                continue
            seen.add(key)
            report.found += 1
            if depth > MAX_DEPTH:
                report.failures.append(f"{origin}: nesting deeper than {MAX_DEPTH}")
                continue
            dest = out_root / f"archive_{report.found:05d}_{uuid.uuid4().hex[:8]}"
            if _unpack_one(runtime, match, dest, make_ctx, report, origin):
                inside = _candidates(dest, set())
                nested += [(p, f"{origin}!{p.relative_to(dest).as_posix()}") for p in inside]
        queue, depth = nested, depth + 1
    return report


def _identified(runtime, queue: list, make_ctx, cancel) -> Iterable:
    """Which of the files are archives (their matches, in order). A large round (the files of
    the archives just unpacked) runs on the worker pool and is announced and counted: each
    file is opened for its head and tail, minutes on a large game (never silent)."""
    slots = list(runtime.slots.values())
    if len(queue) < SAID_FROM:
        return (identify(path, slots) for path, _ in queue)
    ctx = make_ctx("core")
    say = lambda message: ctx.log(message, stage="identify")  # noqa: E731
    say(f"Looking for nested archives in {len(queue):,} extracted file(s) on {workers()} workers")
    ticker = Ticker(say, "Identified files:", len(queue))
    return (ticker.tick() or m for m in each(lambda item: identify(item[0], slots), queue, cancel))


def _unpack_one(runtime, match, dest: Path, make_ctx, report: UnpackReport, origin: str) -> bool:
    slot = runtime.slots[match.slot_id]
    ctx = make_ctx(slot.owner)
    ctx.log(f"Extracting {match.path.name} ({match.slot_id})", stage="unpack")
    source = carve(match, ctx.scratch)

    def reset() -> None:
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)

    reset()
    outcome, used = run_with_failover(
        runtime.bindings[match.slot_id],
        runtime.backends,
        lambda backend: backend.extract(source, dest, ctx),
        reset,
        getattr(ctx, "cancel", None),
    )
    if not outcome.ok:
        report.failures.append(f"{origin}: {outcome.kind.value}: {outcome.error}")
        ctx.log(f"FAILED {match.path.name}: {outcome.error}", "warn", "unpack")
        shutil.rmtree(dest, ignore_errors=True)
        return False
    if outcome.fallback:
        ctx.log(f"{match.path.name}: {outcome.fallback}", "warn", "unpack")
    for note in outcome.notes:  # what the unpacker skipped or could not read: never silent
        ctx.log(f"{match.path.name}: {note}", "warn", "unpack")
        report.failures.append(f"{origin}: {note}")
    report.extracted += 1
    report.files += outcome.files
    report.by_backend[used] += 1
    report.origins[dest] = origin
    ctx.log(f"OK {match.path.name}: {outcome.files} file(s) via {used}", stage="unpack")
    return True
