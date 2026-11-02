"""Main -> spare failover for one slot call (doc 8.2)."""

from __future__ import annotations

from typing import Callable

from viwo.contracts.slots import Backend, SlotBinding
from viwo.contracts.types import Outcome, OutcomeKind


def run_with_failover(
    binding: SlotBinding,
    backends: dict[str, Backend],
    call: Callable[[Backend], Outcome],
    reset: Callable[[], None] | None = None,
) -> tuple[Outcome, str]:
    """Try main, then spare when the outcome is retryable. Returns (outcome, backend id)."""
    if not binding.bound:
        reasons = "; ".join(binding.reasons) or "no backend available"
        return Outcome(OutcomeKind.UNAVAILABLE, error=reasons), ""
    last = Outcome(OutcomeKind.FAILED, error="not attempted")
    used = ""
    for backend_id in (binding.main, binding.spare):
        if not backend_id:
            continue
        if reset is not None and used:
            reset()
        used = backend_id
        try:
            last = call(backends[backend_id])
        except Exception as exc:  # a backend bug is a failed outcome, not a crash
            last = Outcome(OutcomeKind.FAILED, error=f"{type(exc).__name__}: {exc}"[:300])
        if last.ok or not last.retryable:
            break
    return last, used
