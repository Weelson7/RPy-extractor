"""One QEMU guest as a PatchSession (doc 11.8 T2), driven from outside the guest through QEMU's
own two channels: QMP (stop/cont, savevm/loadvm, dump-guest-memory, quit) and the gdbstub (memory
read/write, a stdlib client: gdb.py). The handle holds nothing but two loopback ports, so any
later call (another `viwo isolate`, the API) rejoins the same guest from its record. A gdbstub
client stops the guest when it connects, so memory is touched with the guest stopped and the
connection is dropped, not detached, to leave the run state to QMP alone."""

import re
from contextlib import contextmanager
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.patcher import PatchSession, Wall, WallReport
from viwo.contracts.types import Outcome, OutcomeKind

from .gdb import GdbClient, GdbError
from .qmp import QmpBusy, QmpClient, QmpError

HOST = "127.0.0.1"
GONE = (GdbError, QmpError, OSError)
NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")
NO_SAVE = "this accelerator cannot save state (WHPX): start the session with a snapshot or TCG"


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
        gdb = GdbClient.connect(HOST, self.info["gdb"], 5.0)
        try:
            yield gdb
        finally:
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
        try:
            self._q().execute("quit")  # QEMU closes the overlay cleanly
        except GONE:
            pass
        self.release()
        if self._child is not None:
            self._child.kill()
