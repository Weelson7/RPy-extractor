"""Tier 1: VirtualBox (doc 11.8). ViWo drives `VBoxManage` as a separate process (VirtualBox
base package, GPL-3.0 for 7.x; never imported, and NOT the proprietary Extension Pack): it
registers a VM with a virtual TPM 2.0, boots the target, takes and restores snapshots for
iterative patch retries, pauses and resumes it, and dumps its memory core to a patchable file.
The in-guest debugger (x64dbg inside the guest) does the byte-level read/write; VBoxManage has
no host-side poke, so write_mem reports a NOT_READY wall that says so (the live edit is driven
inside the guest). ViWo does NOT install VirtualBox: a hypervisor needs a kernel driver and a
one-time elevation, which the minimal-prompts and third_party-only rules forbid, so the backend
locates the user's own install (the `virtualbox` dependency). Reference build, located not
downloaded: VirtualBox 7.2.22-175245, VirtualBox-7.2.22-175245-Win.exe, 178,101,352 bytes,
sha256 afd0ff1656cbe04ed88ce619594ae021419d97cce89fa9bdc443e9a963f1713f. Real in-VM proof is
deferred; the orchestration is unit-tested with a fake VBoxManage."""

from pathlib import Path

from viwo.contracts.patcher import PatcherBackend, PatchSession, PatchTarget, Wall, WallReport
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

VBOX = DependencySpec.of("virtualbox")
GUEST_IO = "VBoxManage has no host-side memory write; the in-guest debugger does the byte edit"


def _tail(result) -> str:
    return (result.stderr or result.stdout or "").strip()[-200:]


def _vm_name(target: PatchTarget) -> str:
    return "viwo-" + (target.exe.stem or "target")


class VBoxSession(PatchSession):
    """One registered VM driven through VBoxManage. read_mem / write_mem are the guest
    debugger's job (GUEST_IO wall); the rest are real VBoxManage subcommands."""

    def __init__(self, os, argv, vm: str, base: Path) -> None:
        self._os, self._argv, self.vm, self.base = os, tuple(argv), vm, base
        self._wall = WallReport()

    def _run(self, *args: str, timeout: int = 120):
        return self._os.process.run([*self._argv, *args], timeout=timeout)

    def _step(self, what: str, *args: str) -> Outcome:
        result = self._run(*args)
        if result.ok:
            return Outcome(OutcomeKind.OK)
        return Outcome(OutcomeKind.FAILED, error=f"VBoxManage {what}: {_tail(result)}")

    def boot(self, *, snapshot: bool) -> Outcome:
        steps = (
            ("createvm", self.vm, "--basefolder", str(self.base), "--register"),
            ("modifyvm", self.vm, "--firmware", "efi", "--tpm-type", "2.0"),
            ("startvm", self.vm, "--type", "headless"),
        )
        for args in steps:
            outcome = self._step(args[0], *args)
            if not outcome.ok:
                return outcome
        return self.snapshot("base") if snapshot else Outcome(OutcomeKind.OK)

    def suspend(self) -> None:
        self._run("controlvm", self.vm, "pause")

    def resume(self) -> None:
        self._run("controlvm", self.vm, "resume")

    def read_mem(self, addr: int, size: int) -> bytes:
        self._wall = WallReport(Wall.NOT_READY, GUEST_IO)
        return b""

    def write_mem(self, addr: int, data: bytes) -> WallReport:
        self._wall = WallReport(Wall.NOT_READY, GUEST_IO)
        return self._wall

    def snapshot(self, name: str) -> Outcome:
        return self._step("snapshot take", "snapshot", self.vm, "take", name)

    def rollback(self, name: str) -> Outcome:
        return self._step("snapshot restore", "snapshot", self.vm, "restore", name)

    def dump(self, out: Path) -> Outcome:
        return self._step("dumpvmcore", "debugvm", self.vm, "dumpvmcore", "--filename", str(out))

    def wall(self) -> WallReport:
        return self._wall

    def close(self) -> None:
        self._run("controlvm", self.vm, "poweroff")
        self._run("unregistervm", self.vm, "--delete")


class VirtualBoxPatcher(PatcherBackend):
    backend_id, license, tier = "vbox", "GPL-3.0", 1
    requirement = "VirtualBox base package (VBoxManage); a kernel driver and one-time elevation"
    requires = (VBOX,)

    def ready(self, os) -> WallReport:
        if os.tools.locate(VBOX) is None:
            return WallReport(Wall.NOT_READY, self.requirement)
        return WallReport()

    def start(self, target: PatchTarget, ctx, *, snapshot: bool = False):
        tool = ctx.os.tools.locate(VBOX)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=self.requirement)
        ctx.staging.mkdir(parents=True, exist_ok=True)
        session = VBoxSession(ctx.os, tool.argv_prefix, _vm_name(target), ctx.staging)
        outcome = session.boot(snapshot=snapshot)
        if not outcome.ok:
            session.close()
            return outcome
        ctx.log(f"VirtualBox VM {session.vm} started with a virtual TPM 2.0", "info")
        return session
