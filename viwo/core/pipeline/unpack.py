"""Recursive unpack loop (doc 3.1 UNPACK); keeps v1's queue/seen/subfolder behavior."""

from __future__ import annotations

import shutil
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from viwo.contracts.plugin import ExtractionContext

from .failover import run_with_failover
from .identify import carve, identify

MAX_DEPTH = 10


@dataclass
class UnpackReport:
    found: int = 0
    extracted: int = 0
    files: int = 0
    by_backend: Counter = field(default_factory=Counter)
    origins: dict[Path, str] = field(default_factory=dict)  # unpack dir -> origin label
    failures: list[str] = field(default_factory=list)


def _candidates(root: Path, skip: set[str]) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and not skip.intersection(p.lower() for p in path.parts):
            yield path


def files_under(root: Path, label: str, skip: set[str]) -> list[tuple[Path, str]]:
    return [(p, f"{label}:{p.relative_to(root).as_posix()}") for p in _candidates(root, skip)]


def unpack_all(
    runtime,
    items: list[tuple[Path, str]],
    out_root: Path,
    make_ctx: Callable[[str], ExtractionContext],
) -> UnpackReport:
    """items: (file, origin label). Nested archives are unpacked up to MAX_DEPTH."""
    report = UnpackReport()
    seen: set[str] = set()
    queue = deque((path, origin, 0) for path, origin in items)
    while queue:
        path, origin, depth = queue.popleft()
        match = identify(path, runtime.slots.values())
        key = runtime.os.fs.path_key(path.resolve())
        if match is None or key in seen:
            continue
        seen.add(key)
        report.found += 1
        if depth > MAX_DEPTH:
            report.failures.append(f"{origin}: nesting deeper than {MAX_DEPTH}")
            continue
        dest = out_root / f"archive_{report.found:05d}_{uuid.uuid4().hex[:8]}"
        if _unpack_one(runtime, match, dest, make_ctx, report, origin):
            for nested in _candidates(dest, set()):
                queue.append((nested, f"{origin}!{nested.relative_to(dest).as_posix()}", depth + 1))
    return report


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
    )
    if not outcome.ok:
        report.failures.append(f"{origin}: {outcome.kind.value}: {outcome.error}")
        ctx.log(f"FAILED {match.path.name}: {outcome.error}", "warn", "unpack")
        shutil.rmtree(dest, ignore_errors=True)
        return False
    report.extracted += 1
    report.files += outcome.files
    report.by_backend[used] += 1
    report.origins[dest] = origin
    ctx.log(f"OK {match.path.name}: {outcome.files} file(s) via {used}", stage="unpack")
    return True
