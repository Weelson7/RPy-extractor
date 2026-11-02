"""Slot binder: main/spare resolution, promotion, unbound slots (doc 8.2)."""

from __future__ import annotations

from viwo.contracts.os import OS
from viwo.contracts.slots import Backend, SlotBinding, SlotDefinition


def _check(backend_id: str, slot: SlotDefinition, backends: dict[str, Backend], os: OS):
    """(usable, reason) for one candidate backend in one slot."""
    if not backend_id:
        return False, ""
    backend = backends.get(backend_id)
    if backend is None:
        return False, f"{slot.slot_id}: unknown backend '{backend_id}'"
    if slot.family not in backend.families:
        return False, f"{slot.slot_id}: backend '{backend_id}' does not serve {slot.family}"
    ok, reason = backend.available(os)
    return ok, "" if ok else f"{slot.slot_id}: {backend_id} unavailable ({reason})"


def bind_slot(
    slot: SlotDefinition,
    backends: dict[str, Backend],
    override: tuple[str, str] | None,
    os: OS,
) -> SlotBinding:
    main, spare = override or (slot.default_main, slot.default_spare)
    source = "ini" if override else "default"
    main_ok, main_reason = _check(main, slot, backends, os)
    spare_ok, spare_reason = _check(spare, slot, backends, os)
    reasons = tuple(r for r in (main_reason, spare_reason) if r)
    if main_ok:
        return SlotBinding(slot.slot_id, main, spare if spare_ok else "", False, source, reasons)
    if spare_ok:
        return SlotBinding(slot.slot_id, spare, "", True, source, reasons)
    return SlotBinding(slot.slot_id, "", "", False, source, reasons)


def bind_all(
    slots: dict[str, SlotDefinition],
    backends: dict[str, Backend],
    overrides: dict[str, tuple[str, str]],
    os: OS,
) -> tuple[dict[str, SlotBinding], list[str]]:
    problems = [f"[slots] unknown slot '{s}' ignored" for s in overrides if s not in slots]
    bindings = {
        sid: bind_slot(slot, backends, overrides.get(sid), os) for sid, slot in slots.items()
    }
    return bindings, problems
