"""One QEMU guest as a PatchSession (doc 11.8 T2), driven from outside the guest through QEMU's
own two channels: QMP (stop/cont, savevm/loadvm, dump-guest-memory, quit) and the gdbstub (memory
read/write, a stdlib client: gdb.py). The handle holds nothing but two loopback ports, so any
later call (another `viwo isolate`, the API) rejoins the same guest from its record. A gdbstub
client stops the guest when it connects, so memory is touched with the guest stopped and the
connection is dropped, not detached, to leave the run state to QMP alone. Guest physical memory
is the same gdbstub in QEMU's physical-memory mode (`Qqemu.PhyMemMode`), which is QEMU-wide, so
it is switched off again before the connection goes and at the start of every virtual access."""

import re
import time
from contextlib import contextmanager
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.patcher import MemoryFault, PatchSession, Wall, WallReport
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.os import pid_alive

from .gdb import GdbClient, GdbError
from .paging import mode_of
from .qmp import QmpBusy, QmpClient, QmpError

HOST = "127.0.0.1"
GONE = (GdbError, QmpError, OSError)
NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")
PHYS = "Qqemu.PhyMemMode:"
REGISTER = re.compile(r"\b(CR0|CR3|CR4|EFER)=([0-9a-fA-F]+)")
NO_SAVE = "this accelerator cannot save state (WHPX): start the session with a snapshot or TCG"


class _Physical:
    """Guest physical memory through a gdbstub already in physical-memory mode."""

    def __init__(self, gdb: GdbClient) -> None:
        self._gdb = gdb

    def read(self, pa: int, n: int) -> bytes:
        return self._gdb.read_mem(pa, n)

    def write(self, pa: int, data: bytes) -> None:
        self._gdb.write_mem(pa, data)


class QemuSession(PatchSession):
    def __init__(self, info: dict, child=None, wait: float = 5.0) -> None:
        self.info, self._child, self._wait = info, child, wait
        self._qmp: QmpClient | None = None
        self._wall = WallReport()

    def _q(self) -> QmpClient:
        if self._qmp is None:
            try:
                self._qmp = QmpClient.connect(HOST, self.info["qmp"], self._wait)
            except QmpBusy as exc:
                raise ViwoError("busy", f"{exc}; try again when the other action is done") from exc
        return self._qmp

    def answers(self) -> bool:
        """Whether QEMU's control channel answers (waits up to the session's `wait`)."""
        try:
            self._q().execute("query-status")
            return True
        except GONE:
            self.release()
            return False

    def running(self) -> bool:
        return bool(self._q().execute("query-status").get("running"))

    def suspend(self) -> None:
        self._q().execute("stop")

    def resume(self) -> None:
        self._q().execute("cont")

    @contextmanager
    def _memory(self):
        """The gdbstub with the guest stopped; the guest runs again after only if it ran before."""
        was = self.running()
        self.suspend()
        gdb = None
        try:
            gdb = GdbClient.connect(HOST, self.info["gdb"], 5.0)
            gdb.command(PHYS + "0")  # virtual addresses, whatever an earlier client left
            yield gdb
        finally:
            if gdb is not None:
                gdb.drop()
            if was:
                self.resume()

    def read_mem(self, addr: int, size: int) -> bytes:
        try:
            with self._memory() as gdb:
                data = gdb.read_mem(addr, size)
            self._wall = WallReport()
            return data
        except GONE as exc:
            self._wall = WallReport(Wall.NOT_READY, f"gdbstub read refused: {exc}")
            return b""

    def write_mem(self, addr: int, data: bytes) -> WallReport:
        try:
            with self._memory() as gdb:
                gdb.write_mem(addr, data)
            self._wall = WallReport()
        except GONE as exc:
            self._wall = WallReport(Wall.NOT_READY, f"gdbstub write refused: {exc}")
        return self._wall

    def cpu_paging(self) -> dict | None:
        try:
            text = self._q().monitor("info registers")
        except GONE:
            return None
        regs = {k.lower(): int(v, 16) for k, v in REGISTER.findall(text)}
        if not {"cr0", "cr3", "cr4", "efer"} <= regs.keys():
            return None
        return {"dtb": regs["cr3"], "mode": mode_of(regs["cr0"], regs["cr4"], regs["efer"])}

    @contextmanager
    def physical(self):
        try:
            with self._memory() as gdb:
                if gdb.command(PHYS + "1") != "OK":
                    raise MemoryFault("this QEMU's gdbstub has no physical-memory mode")
                try:
                    yield _Physical(gdb)
                finally:
                    gdb.command(PHYS + "0")
        except GONE as exc:
            raise MemoryFault(f"gdbstub: {exc}") from exc

    def snapshot(self, name: str) -> Outcome:
        return self._monitor("savevm", name)

    def rollback(self, name: str) -> Outcome:
        return self._monitor("loadvm", name)

    def _monitor(self, command: str, name: str) -> Outcome:
        if not NAME.fullmatch(name):
            return Outcome(OutcomeKind.FAILED, error="a snapshot name is letters, digits, _ . -")
        try:
            out = self._q().monitor(f"{command} {name}")
        except GONE as exc:
            return Outcome(OutcomeKind.FAILED, error=f"QMP {command}: {exc}")
        if "State blocked" in out:
            return Outcome(OutcomeKind.UNAVAILABLE, error=NO_SAVE)
        if "rror" in out:  # savevm/loadvm print nothing on success, "Error: ..." on failure
            return Outcome(OutcomeKind.FAILED, error=out.strip()[:200])
        return Outcome(OutcomeKind.OK)

    def dump(self, out: Path) -> Outcome:
        try:
            self._q().execute("dump-guest-memory", paging=False, protocol=f"file:{out}")
        except GONE as exc:
            return Outcome(OutcomeKind.FAILED, error=f"QMP dump-guest-memory: {exc}")
        if out.is_file():
            out.chmod(0o644)  # QEMU creates it read-only, which Windows then refuses to delete
        return Outcome(OutcomeKind.OK)

    def wall(self) -> WallReport:
        return self._wall

    def record(self) -> dict:
        return dict(self.info)

    def alive(self) -> bool:
        return self._child.alive() if self._child is not None else self.answers()

    def release(self) -> None:
        qmp, self._qmp = self._qmp, None
        if qmp is not None:
            qmp.close()

    def close(self) -> None:
        """Quit QEMU and return once it has exited, so its files are free (Windows locks them)."""
        try:
            self._q().execute("quit")  # QEMU closes the overlay cleanly
        except GONE:
            pass
        self.release()
        end = time.monotonic() + 10.0
        while pid_alive(int(self.info.get("pid") or 0)) and time.monotonic() < end:
            time.sleep(0.1)
        if self._child is not None:
            self._child.kill()
