"""Tier 3: DRAKVUF / LibVMI (doc 11.8). On a bare-metal Linux KVM/Xen host ViWo drives LibVMI's
own CLI tools from outside the guest: it reads guest physical memory with `vmi-dump-memory`, pauses
and resumes the domain with the hypervisor's control (`virsh suspend`/`resume` on KVM, `xl pause`/
`xl unpause` on Xen) and can start DRAKVUF introspection against a named domain. LibVMI ships no
stock memory-write CLI, so `write_mem` is a `not_ready` wall that says a DRAKVUF/LibVMI write helper
is needed. On Windows and WSL2 there is no such host, so `ready()`/`start()`/`wall()` report
not-ready with the requirement, never silently (owner). ViWo authors no introspection or hypervisor
code; it orchestrates the located tools. No such host exists here; the command construction and the
not-ready path are unit-tested with fakes."""

import platform
from pathlib import Path

from viwo.contracts.patcher import PatcherBackend, PatchSession, PatchTarget, Wall, WallReport
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

DRAKVUF = DependencySpec("drakvuf", "DRAKVUF", executables=("drakvuf",),
                         hint="install DRAKVUF on the Linux KVM/Xen host")  # fmt: skip
VMI_READ = DependencySpec("vmi-dump-memory", "LibVMI dump-memory", executables=("vmi-dump-memory",),
                          hint="install LibVMI (its example tools) on the host")  # fmt: skip
VIRSH = DependencySpec("virsh", "libvirt virsh", executables=("virsh",), hint="install libvirt")
XL = DependencySpec("xl", "Xen xl", executables=("xl",), hint="install the Xen tool stack")
NO_WRITE = "LibVMI ships no stock memory-write CLI; a DRAKVUF/LibVMI write helper is needed"
NO_SNAP = "a snapshot is the hypervisor's own tool (virsh snapshot / xl save), not wired here"


def _no_host() -> bool:
    """True where there is no bare-metal Linux VMI host: Windows, or a WSL2 kernel."""
    return platform.system() != "Linux" or "microsoft" in platform.uname().release.lower()


def control_of(os):
    """(argv prefix, (pause verb, resume verb)) of the located hypervisor control, or None."""
    if (tool := os.tools.locate(VIRSH)) is not None:
        return tool.argv_prefix, ("suspend", "resume")
    if (tool := os.tools.locate(XL)) is not None:
        return tool.argv_prefix, ("pause", "unpause")
    return None


class VmiSession(PatchSession):
    """One introspected domain: read and dump through vmi-dump-memory, pause/resume through the
    hypervisor control. A host-side write is not a stock LibVMI capability (a not_ready wall)."""

    def __init__(self, os, domain: str, read_argv, control) -> None:
        self._os, self.domain, self._read_argv = os, domain, read_argv
        self._ctrl, self._verbs = control
        self._wall = WallReport()

    def _ctrl_run(self, verb: str):
        return self._os.process.run([*self._ctrl, verb, self.domain], timeout=60)

    def suspend(self) -> None:
        self._ctrl_run(self._verbs[0])

    def resume(self) -> None:
        self._ctrl_run(self._verbs[1])

    def read_mem(self, addr: int, size: int) -> bytes:
        self._wall = WallReport(
            Wall.NOT_READY, "vmi-dump-memory writes a full physical image; dump() then slice it"
        )
        return b""

    def write_mem(self, addr: int, data: bytes) -> WallReport:
        self._wall = WallReport(Wall.NOT_READY, NO_WRITE)
        return self._wall

    def snapshot(self, name: str) -> Outcome:
        return Outcome(OutcomeKind.UNAVAILABLE, error=NO_SNAP)

    def rollback(self, name: str) -> Outcome:
        return Outcome(OutcomeKind.UNAVAILABLE, error=NO_SNAP)

    def dump(self, out: Path) -> Outcome:
        result = self._os.process.run([*self._read_argv, self.domain, str(out)], timeout=600)
        if result.ok:
            return Outcome(OutcomeKind.OK)
        return Outcome(OutcomeKind.FAILED, error=(result.stderr or result.stdout or "")[-200:])

    def wall(self) -> WallReport:
        return self._wall


class VmiPatcher(PatcherBackend):
    backend_id, license, tier = "libvmi", "GPL-3.0", 3
    requirement = "a bare-metal Linux KVM/Xen host with DRAKVUF/LibVMI (not available on Windows)"
    requires = ()

    def ready(self, os) -> WallReport:
        if _no_host():
            return WallReport(Wall.NOT_READY, self.requirement)
        if os.tools.locate(VMI_READ) is None and os.tools.locate(DRAKVUF) is None:
            return WallReport(Wall.NOT_READY, "install DRAKVUF/LibVMI (vmi-* tools) on the host")
        if control_of(os) is None:
            return WallReport(
                Wall.NOT_READY, "install libvirt (virsh) or Xen (xl) to pause the domain"
            )
        return WallReport()

    def start(self, target: PatchTarget, ctx, *, snapshot: bool = False):
        report = self.ready(ctx.os)
        if report.blocked:
            return Outcome(OutcomeKind.UNAVAILABLE, error=report.detail)
        domain = (target.args[0] if target.args else target.exe.stem) or "guest"
        read = ctx.os.tools.locate(VMI_READ)
        read_argv = read.argv_prefix if read is not None else ("vmi-dump-memory",)
        ctx.log(f"LibVMI session on domain {domain} (read via vmi-dump-memory)", "info")
        return VmiSession(ctx.os, domain, read_argv, control_of(ctx.os))
