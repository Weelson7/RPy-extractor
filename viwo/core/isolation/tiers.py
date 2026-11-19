"""Tiers 2 and 3 (doc 11.8), declared interfaces only. QEMU (T2) runs the target out-of-guest
behind its gdbstub (WHPX acceleration when present, else TCG); DRAKVUF/LibVMI (T3) watches and
patches from outside the guest and needs a bare-metal Linux KVM/Xen host. Neither is implemented
here: start() refuses with the backend's requirement and ready()/wall() announce what is missing,
never silently. QEMU is located (the user's own `qemu-system-x86_64`); VMI has no Windows tool at
all. Pins are deferred to the tier's implementation (QEMU has no single authoritative Windows
checksum; VMI's host tools are Linux-only)."""

from viwo.contracts.patcher import PatcherBackend, Wall, WallReport
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

QEMU = DependencySpec.of("qemu")
QEMU_TODO = "QEMU out-of-guest patcher is declared, not implemented (doc 11.8 T2)"


class QemuPatcher(PatcherBackend):
    backend_id, license, tier = "qemu", "GPL-2.0", 2
    requirement = "QEMU (qemu-system-x86_64) with its gdbstub; WHPX acceleration or TCG"
    requires = (QEMU,)

    def ready(self, os) -> WallReport:
        if os.tools.locate(QEMU) is None:
            return WallReport(Wall.NOT_READY, self.requirement)
        return WallReport(Wall.NOT_READY, QEMU_TODO)

    def start(self, target, ctx, *, snapshot: bool = False):
        return Outcome(OutcomeKind.UNAVAILABLE, error=self.ready(ctx.os).detail)


class VmiPatcher(PatcherBackend):
    backend_id, license, tier = "libvmi", "GPL-3.0", 3
    requirement = "a bare-metal Linux KVM/Xen host with DRAKVUF/LibVMI (not available on Windows)"
    requires = ()

    def ready(self, os) -> WallReport:
        return WallReport(Wall.NOT_READY, self.requirement)

    def start(self, target, ctx, *, snapshot: bool = False):
        return Outcome(OutcomeKind.UNAVAILABLE, error=self.requirement)
