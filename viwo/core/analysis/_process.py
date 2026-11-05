"""The one way an analyzer runs its tool: timeout from the request options, lines relayed to
the activity log (ANSI stripped), and the failure outcome built from the tail of its output."""

import re

from viwo.contracts.types import Outcome, OutcomeKind

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def run_tool(ctx, argv: list[str], env: dict | None, default_timeout: int, relay=None):
    """`relay(line)` replaces the default (every line, ANSI stripped) for chatty tools."""
    timeout = int(ctx.options.get("timeout_s") or default_timeout)
    relay = relay or (lambda line: ctx.log(ANSI.sub("", line)[:200], stage="analyze"))
    return ctx.os.process.run(argv, timeout=timeout, cancel=ctx.cancel, env=env, on_line=relay)


def failed(result, fallback: str) -> Outcome:
    if result.timed_out:
        return Outcome(OutcomeKind.FAILED, error="the analyzer timed out or was cancelled")
    return Outcome(OutcomeKind.FAILED, error=(result.stderr or result.stdout or fallback)[-400:])
