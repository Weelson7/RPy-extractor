"""The ExtractionContext handed to backends and plugin hooks: built here only. core_context
serves core-owned work (capture, repack, merger probe, analysis, agents); for_owner turns it
into one owner's view (the extraction pipeline and `viwo unpack`, per plugin or "core")."""

from dataclasses import replace
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.plugin import ExtractionContext
from viwo.contracts.types import CancelToken, DetectionResult

CORE = DetectionResult("core", 1.0, (), "core")


def require(rt, feature: str, what: str, more: str = "") -> None:
    """A capability switch ([startup] features): when off, the request is refused with the way
    to switch it on (never a judgement: the switch is the user's)."""
    if feature not in rt.config.features:
        hint = f"add {feature} to [startup] features in the ini (SETTINGS){more}"
        raise ViwoError("refused", f"{what} is off", hint=hint)


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


def for_owner(ctx: ExtractionContext, rt, owner: str, options: dict, **fields):
    """`ctx` as `owner` sees it: staging/<owner>, its ini options with `options` over them, its
    source tag and a placeholder detection; `fields` set the rest (detection, probe...)."""
    view = {
        "staging": ctx.staging / owner,
        "detection": DetectionResult(owner, 0.0, (), owner),
        "options": {**rt.owner_options(owner), **options},
        "source": "core" if owner == "core" else f"plugin:{owner}",
    }
    return replace(ctx, **{**view, **fields})
