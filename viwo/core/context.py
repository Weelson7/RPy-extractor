"""The ExtractionContext core-owned work hands to backends (capture, repack, merger probe,
analysis, forced unpack): one builder instead of a hand-written record per caller."""

from __future__ import annotations

from pathlib import Path

from viwo.contracts.plugin import ExtractionContext
from viwo.contracts.types import CancelToken, DetectionResult

CORE = DetectionResult("core", 1.0, (), "core")


def core_context(rt, job: str, root: Path, work: Path, sink=None, cancel=None):
    """`staging` = work/staging, `scratch` = work/scratch; callers that write elsewhere set
    `ctx.staging` after. `root` is the folder the work reads (a game, a workspace)."""
    return ExtractionContext(
        job,
        root,
        work / "staging",
        work / "scratch",
        rt.os,
        CORE,
        None,
        {},
        sink or (lambda e: None),
        cancel or CancelToken(),
    )
