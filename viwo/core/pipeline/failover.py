"""Main -> spare failover for one slot call (doc 8.2)."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from viwo.contracts.slots import Backend, SlotBinding
from viwo.contracts.types import Outcome, OutcomeKind


def run_with_failover(
    binding: SlotBinding,
    backends: dict[str, Backend],
    call: Callable[[Backend], Outcome],
    reset: Callable[[], None] | None = None,
    cancel=None,
) -> tuple[Outcome, str]:
    """Try main, then spare when the outcome is retryable. Returns (outcome, backend id). A
    cancelled run never starts the spare (the main failed because it was stopped)."""
    if not binding.bound:
        reasons = "; ".join(binding.reasons) or "no backend available"
        return Outcome(OutcomeKind.UNAVAILABLE, error=reasons), ""
    last = Outcome(OutcomeKind.FAILED, error="not attempted")
    used, failed = "", ""
    for backend_id in (binding.main, binding.spare):
        if not backend_id:
            continue
        if used and cancel is not None and cancel.cancelled:
            break
        if used:
            failed = f"{used} {last.kind.value}: {last.error or 'no reason given'}"
            if reset is not None:
                reset()
        used = backend_id
        try:
            last = call(backends[backend_id])
        except Exception as exc:  # a backend bug is a failed outcome, not a crash
            last = Outcome(OutcomeKind.FAILED, error=f"{type(exc).__name__}: {exc}"[:300])
        if last.ok or not last.retryable:
            break
    if failed:  # never silent: the main backend's failure travels with the outcome
        error = f"{last.error} (after {failed})" if not last.ok else last.error
        last = replace(last, error=error, fallback=f"{failed}; used {used}")
    return last, used
