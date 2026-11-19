"""Tier 2: QEMU (doc 11.8). ViWo drives the user's own `qemu-system-x86_64` as a separate process
with its gdbstub (`-gdb tcp::PORT -S`) and QMP control channel: it reads and writes guest memory
and stops/continues the target out of the guest over the GDB remote serial protocol (a stdlib
client, viwo.core.isolation.gdb), and snapshots and dumps through QMP. WHPX hardware acceleration
is used when QEMU reports it, else TCG, and which one is said (owner: never silent). ViWo authors
no hypervisor code and does not install QEMU (kernel driver, elevation): it locates the user's own
install (the `qemu` dependency). No real VM has run here; the orchestration is unit-tested with a
fake qemu-system-x86_64 and an in-process loopback gdbstub / QMP."""

import socket
from pathlib import Path

from viwo.contracts.patcher import PatcherBackend, PatchSession, PatchTarget, Wall, WallReport
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from .gdb import GdbClient, GdbError
from .qmp import QmpClient, QmpError

QEMU = DependencySpec.of("qemu")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def accel_of(os, argv_prefix) -> str:
    """ "whpx" when this QEMU lists Windows hardware acceleration, else the portable "tcg"."""
    result = os.process.run([*argv_prefix, "-accel", "help"], timeout=30)
    return "whpx" if "whpx" in ((result.stdout or "") + (result.stderr or "")).lower() else "tcg"


class QemuSession(PatchSession):
    """One QEMU process driven out-of-guest: memory over the gdbstub, snapshots/dump over QMP."""

    def __init__(self, child, gdb: GdbClient, qmp: QmpClient, accel: str) -> None:
        self._child, self._gdb, self._qmp, self.accel = child, gdb, qmp, accel
        self._wall = WallReport()
        self._running = False  # QEMU is started with -S: halted at reset

    def suspend(self) -> None:
        if self._running:
            self._gdb.interrupt()
            self._running = False

    def resume(self) -> None:
        if not self._running:
            self._gdb.cont()
            self._running = True

    def read_mem(self, addr: int, size: int) -> bytes:
        try:
            data = self._gdb.read_mem(addr, size)
            self._wall = WallReport()
            return data
        except GdbError as exc:
            self._wall = WallReport(Wall.NOT_READY, f"gdbstub read refused: {exc}")
            return b""

    def write_mem(self, addr: int, data: bytes) -> WallReport:
        try:
            self._gdb.write_mem(addr, data)
            self._wall = WallReport()
        except GdbError as exc:
            self._wall = WallReport(Wall.NOT_READY, f"gdbstub write refused: {exc}")
        return self._wall

    def snapshot(self, name: str) -> Outcome:
        return self._monitor("savevm", name)

    def rollback(self, name: str) -> Outcome:
        return self._monitor("loadvm", name)

    def _monitor(self, command: str, name: str) -> Outcome:
        try:
            out = self._qmp.monitor(f"{command} {name}")
        except QmpError as exc:
            return Outcome(OutcomeKind.FAILED, error=f"QMP {command}: {exc}")
        if "rror" in out:  # savevm/loadvm print nothing on success, "Error: ..." on failure
            return Outcome(OutcomeKind.FAILED, error=out.strip()[:200])
        return Outcome(OutcomeKind.OK)

    def dump(self, out: Path) -> Outcome:
        try:
            self._qmp.execute("dump-guest-memory", paging=False, protocol=f"file:{out}")
        except QmpError as exc:
            return Outcome(OutcomeKind.FAILED, error=f"QMP dump-guest-memory: {exc}")
        return Outcome(OutcomeKind.OK)

    def wall(self) -> WallReport:
        return self._wall

    def close(self) -> None:
        for shut in (self._gdb.close, self._qmp.close):
            try:
                shut()
            except OSError:
                pass
        if self._child is not None:
            self._child.kill()


class QemuPatcher(PatcherBackend):
    backend_id, license, tier = "qemu", "GPL-2.0", 2
    requirement = "QEMU (qemu-system-x86_64) with its gdbstub; WHPX acceleration or TCG"
    requires = (QEMU,)

    def ready(self, os) -> WallReport:
        if os.tools.locate(QEMU) is None:
            return WallReport(Wall.NOT_READY, self.requirement)
        return WallReport()

    def start(self, target: PatchTarget, ctx, *, snapshot: bool = False):
        tool = ctx.os.tools.locate(QEMU)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=self.requirement)
        if target.image is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error="QEMU needs a guest disk image (--image)")
        return self._boot(tool, target, ctx, snapshot)

    def _boot(self, tool, target: PatchTarget, ctx, snapshot: bool):
        ctx.staging.mkdir(parents=True, exist_ok=True)
        accel = accel_of(ctx.os, tool.argv_prefix)
        gdb_port, qmp_port = _free_port(), _free_port()
        argv = [*tool.argv_prefix, "-accel", accel, "-S", "-gdb", f"tcp::{gdb_port}",
                "-qmp", f"tcp::{qmp_port},server,nowait", "-drive",
                f"file={target.image}", *target.args]  # fmt: skip
        child = ctx.os.process.launch(argv, ctx.staging)
        try:
            session = QemuSession(child, GdbClient.connect("127.0.0.1", gdb_port),
                                  QmpClient.connect("127.0.0.1", qmp_port), accel)  # fmt: skip
        except (OSError, GdbError, QmpError) as exc:
            child.kill()
            return Outcome(OutcomeKind.FAILED, error=f"QEMU gdbstub/QMP did not come up: {exc}")
        ctx.log(f"QEMU started ({accel}); gdbstub :{gdb_port}, QMP :{qmp_port}", "info")
        if snapshot and not session.snapshot("base").ok:
            ctx.log("QEMU base snapshot failed (a qcow2 image is needed for savevm)", "warn")
        return session
