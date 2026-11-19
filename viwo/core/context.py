"""The ExtractionContext handed to backends and plugin hooks: built here only. core_context
serves core-owned work (capture, repack, merger probe, analysis, agents); for_owner turns it
into one owner's view (the extraction pipeline and `viwo unpack`, per plugin or "core")."""

from dataclasses import replace
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.plugin import ExtractionContext
from viwo.contracts.types import CancelToken, DetectionResult, Outcome, OutcomeKind

from .pipeline.pool import budget, each

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
    ctx = ExtractionContext(
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
        each=each,
        memory=budget(rt),
    )
    return _with_keys(ctx, rt)


def for_owner(ctx: ExtractionContext, rt, owner: str, options: dict, **fields):
    """`ctx` as `owner` sees it: staging/<owner>, its ini options with `options` over them, its
    source tag and a placeholder detection; `fields` set the rest (detection, probe...)."""
    view = {
        "staging": ctx.staging / owner,
        "detection": DetectionResult(owner, 0.0, (), owner),
        "options": {**rt.owner_options(owner), **options},
        "source": "core" if owner == "core" else f"plugin:{owner}",
    }
    return _with_keys(replace(ctx, **{**view, **fields}), rt)


def _with_keys(ctx: ExtractionContext, rt) -> ExtractionContext:
    ctx.keys = lambda slot: candidate_keys(rt, slot, ctx)
    return ctx


def candidate_keys(rt, slot: str, ctx: ExtractionContext) -> list[bytes]:
    """The candidates of a `keys.*` slot (doc 14.2 #4): the main's, the spare's when the main
    finds none (or fails); [] for a slot that is not bound, which the plugin says. In memory
    only: nothing of a key reaches a log, an outcome or the disk."""
    from .pipeline.failover import run_with_failover

    binding, found = rt.bindings.get(slot), []
    if binding is None:
        return []

    def call(finder) -> Outcome:
        found[:] = list(finder.candidates(ctx.game_root, ctx))
        if not found:
            return Outcome(OutcomeKind.FAILED, error="no candidate key")
        return Outcome(OutcomeKind.OK, len(found))

    outcome, _ = run_with_failover(binding, rt.backends, call, into=None, cancel=ctx.cancel)
    if outcome.fallback:  # never silent; a count and a backend's name, never a key
        ctx.log(f"{slot}: {outcome.fallback}", "warn", "unpack")
    return found if outcome.ok else []
