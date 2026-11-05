"""Slot binder: main/spare resolution, promotion, unbound slots (doc 8.2, 9.4).

A `[slots]` entry that names an unknown backend, or one that does not serve the slot's family,
is an error for that entry only: the problem is recorded and the slot's default is used instead.
A default spare that is unknown (its plugin is switched off) is simply absent.
"""

from viwo.contracts.os import OS
from viwo.contracts.slots import Backend, SlotBinding, SlotDefinition


def _config_error(backend_id: str, slot: SlotDefinition, backends: dict[str, Backend]) -> str:
    """Why `backend_id` can never serve `slot` (independent of what is installed)."""
    if not backend_id:
        return ""
    backend = backends.get(backend_id)
    if backend is None:
        return f"unknown backend '{backend_id}'"
    if slot.family not in backend.families:
        return f"backend '{backend_id}' does not serve {slot.family}"
    return ""


def _resolve(
    slot: SlotDefinition, override: tuple[str, str] | None, backends: dict[str, Backend]
) -> tuple[str, str, list[str]]:
    """(main, spare, problems): the ini entry with every bad id replaced by the default."""
    defaults = (slot.default_main, slot.default_spare)
    if override is None:
        main, spare = defaults
        problems = [f"{slot.slot_id}: {e}" for e in (_config_error(main, slot, backends),) if e]
        spare = "" if _config_error(spare, slot, backends) else spare
        return main, spare, problems
    chosen, problems = [], []
    for position, (wanted, default) in enumerate(zip(override, defaults)):
        error = _config_error(wanted, slot, backends)
        if error and position == 1 and wanted == default:
            chosen.append("")  # the default spare's plugin is off: simply absent (doc 8.2)
            continue
        if error:
            name = ("main", "spare")[position]
            problems.append(f"[slots] {slot.slot_id}: {error}; default {name} '{default}' used")
            wanted = "" if _config_error(default, slot, backends) else default
        chosen.append(wanted)
    return chosen[0], chosen[1], problems


def _usable(backend_id: str, slot: SlotDefinition, backends: dict[str, Backend], os: OS):
    """(usable, reason) for one resolved candidate."""
    if not backend_id:
        return False, ""
    ok, reason = backends[backend_id].available(os)
    return ok, "" if ok else f"{slot.slot_id}: {backend_id} unavailable ({reason})"


def bind_slot(
    slot: SlotDefinition,
    backends: dict[str, Backend],
    override: tuple[str, str] | None,
    os: OS,
) -> SlotBinding:
    main, spare, problems = _resolve(slot, override, backends)
    source = "ini" if override else "default"
    main_ok, main_reason = _usable(main, slot, backends, os)
    spare_ok, spare_reason = _usable(spare, slot, backends, os)
    reasons = tuple(problems + [r for r in (main_reason, spare_reason) if r])
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
