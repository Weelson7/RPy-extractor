"""Pluggable patcher / isolation arm (doc 11.8). One slot family, `isolation.<tier>`: VirtualBox
(T1, VBoxManage, in-guest debugger byte edits), QEMU (T2, out-of-guest over its gdbstub and QMP)
and DRAKVUF/LibVMI (T3, bare-metal Linux VMI; not-ready elsewhere). The atomic live edit (suspend
-> write -> verify -> resume) lives here so every backend's session shares it, and the cold+live
bridge (live.py) turns one located patch into either a cold byte write or a live one. A session
starts only when a caller asks for it (`viwo isolate`, `/api/runtime/isolation`)."""

import time

from viwo.contracts.patcher import PatchSession, Wall, WallReport
from viwo.contracts.slots import SlotDefinition

from .qemu import QemuPatcher
from .scylla import ScyllaDump
from .vbox import VirtualBoxPatcher
from .vmi import VmiPatcher

__all__ = ["SLOTS", "ScyllaDump", "atomic_write", "backends", "tiers"]

SLOTS = (
    SlotDefinition("isolation.vbox", "isolation", "core", "vbox"),
    SlotDefinition("isolation.qemu", "isolation", "core", "qemu"),
    SlotDefinition("isolation.vmi", "isolation", "core", "libvmi"),
)


def backends() -> list:
    """The three tier backends. Scylla's dump-to-patch handoff is an attach-family tool, wired
    in core/capture (so it rides `viwo attach`), not an isolation backend."""
    return [VirtualBoxPatcher(), QemuPatcher(), VmiPatcher()]


def tiers(rt) -> list[dict]:
    """Every isolation backend with its tier, slot, requirement and readiness wall (for SYSTEM /
    a CLI): announces what each tier needs and whether it can run here, never silently missing."""
    out = []
    for sid, slot in sorted(rt.slots.items()):
        backend = rt.backends.get(slot.default_main) if slot.family == "isolation" else None
        if backend is None:
            continue
        report = backend.ready(rt.os)
        out.append(
            {
                "slot": sid,
                "backend": backend.backend_id,
                "tier": backend.tier,
                "requirement": backend.requirement,
                "ready": not report.blocked,
                "wall": report.wall.value,
                "detail": report.detail,
            }
        )
    return out


def atomic_write(session: PatchSession, addr: int, data: bytes, settle: float = 0.0) -> WallReport:
    """A live edit that is never seen half-applied: suspend the target, write, read the bytes
    back to prove they held, and resume whatever happened. With `settle`, read once more that
    many seconds after the target runs again: a self-check that puts its bytes back is an
    integrity-check wall, said and not mistaken for a patch that landed. The suspend/resume and
    the I/O are the session's own (the boundary's tool); this is only the order (doc 11.8)."""
    session.suspend()
    try:
        blocked = session.write_mem(addr, data)
        if not blocked.blocked and session.read_mem(addr, len(data)) != data:
            blocked = WallReport(Wall.INTEGRITY_CHECK, "the write did not hold on readback")
    finally:
        session.resume()
    if blocked.blocked or settle <= 0:
        return blocked
    time.sleep(settle)
    if session.read_mem(addr, len(data)) != data:
        return WallReport(Wall.INTEGRITY_CHECK, "the target put its bytes back once it ran again")
    return WallReport()
