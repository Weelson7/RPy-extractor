"""One VirtualBox VM as a PatchSession (doc 11.8 T1). VBoxManage holds the run state (pause,
resume), snapshots (live, so on hardware acceleration) and the core dump. Memory goes through the
VM's own gdb stub on loopback (`--guest-debug-provider gdb`), found by trying it on the real thing:
the stub halts the vCPUs while a client is connected and lets them go when it leaves (a pause by
VBoxManage stays a pause), it reads but does not write memory (`M` and `X` are refused), and its
console (`qRcmd`) reads and writes guest PHYSICAL memory (`db`/`eb`/`eq` on `%%` addresses) and
the control registers (`r cr3`). So every access is physical: an address is walked through the
paging of vCPU 0 (its CR3), or through a located process's (core.isolation.guest)."""

import re
import time
from contextlib import contextmanager
from pathlib import Path

from viwo.contracts.patcher import MemoryFault, PatchSession, Wall, WallReport
from viwo.contracts.types import Outcome, OutcomeKind

from . import guest, paging
from .gdb import GdbClient, GdbError

HOST = "127.0.0.1"
HEXBYTE = re.compile(r"[0-9a-fA-F]{2}")
REGISTER = re.compile(r"=\s*(?:0x)?([0-9a-fA-F]+)")
LIVE = ("running", "paused", "stuck", "teleporting", "livesnapshotting")


def _tail(result) -> str:
    return (result.stderr or result.stdout or "").strip()[-200:]


class Console:
    """Guest physical memory and registers through the stub's console."""

    def __init__(self, gdb: GdbClient) -> None:
        self._gdb = gdb

    def _say(self, line: str) -> str:
        text = self._gdb.monitor(line)
        said = [t for t in text.splitlines() if not t.startswith("%%")]  # not a memory dump line
        if any("error" in t.lower() or t.startswith("Syntax") for t in said):
            raise MemoryFault(f"{line}: {' '.join(said).strip()[:200]}")
        return text

    def read(self, pa: int, n: int) -> bytes:
        out = bytearray()
        for line in self._say(f"db %%{pa:x} L{n:x}").splitlines():
            if ":" in line:  # "%%addr: 16 bytes, a dash after 8  ascii" -> the 16 bytes only
                out += bytes(int(h, 16) for h in HEXBYTE.findall(line.split(":", 1)[1][:49]))
        if len(out) < n:
            raise MemoryFault(f"read {n} bytes at physical {pa:#x}: got {len(out)}")
        return bytes(out[:n])

    def write(self, pa: int, data: bytes) -> None:
        at = 0
        while at < len(data):
            if (pa + at) % 8 == 0 and len(data) - at >= 8:
                value = int.from_bytes(data[at : at + 8], "little")
                self._say(f"eq %%{pa + at:x} {value:#x}")
                at += 8
            else:
                self._say(f"eb %%{pa + at:x} {data[at]:#x}")
                at += 1

    def register(self, name: str) -> int:
        found = REGISTER.search(self._say(f"r {name}"))
        if found is None:
            raise MemoryFault(f"register {name} unreadable")
        return int(found.group(1), 16)


class VBoxSession(PatchSession):
    def __init__(self, os, argv, info: dict) -> None:
        self._os, self._argv, self.info = os, tuple(argv), info
        self.vm = str(info["vm"])
        self._wall = WallReport()

    def _run(self, *args: str, timeout: int = 120):
        return self._os.process.run([*self._argv, *args], timeout=timeout)

    def _step(self, what: str, *args: str) -> Outcome:
        result = self._run(*args)
        if result.ok:
            return Outcome(OutcomeKind.OK)
        return Outcome(OutcomeKind.FAILED, error=f"VBoxManage {what}: {_tail(result)}")

    def state(self) -> str:
        """VirtualBox's VMState ("running", "paused", "poweroff", ...; "" when unknown)."""
        result = self._run("showvminfo", self.vm, "--machinereadable", timeout=60)
        found = re.search(r'^VMState="([^"]+)"', result.stdout or "", re.M)
        return found.group(1) if found else ""

    def running(self) -> bool:
        return self.state() == "running"

    def alive(self) -> bool:
        return self.state() in LIVE

    def suspend(self) -> None:
        if self.running():
            self._run("controlvm", self.vm, "pause")

    def resume(self) -> None:
        if self.state() == "paused":
            self._run("controlvm", self.vm, "resume")

    @contextmanager
    def physical(self):
        try:
            gdb = GdbClient.connect(HOST, int(self.info["gdb"]), 5.0)
        except OSError as exc:
            raise MemoryFault(f"VirtualBox gdb stub: {exc}") from exc
        try:
            yield Console(gdb)
        except (GdbError, OSError) as exc:
            raise MemoryFault(f"VirtualBox gdb stub: {exc}") from exc
        finally:
            gdb.drop()  # the stub lets the vCPUs go; a VBoxManage pause stays

    def cpu_paging(self) -> dict | None:
        try:
            with self.physical() as console:
                regs = {name: console.register(name) for name in ("cr0", "cr3", "cr4", "efer")}
        except MemoryFault:
            return None
        return {"dtb": regs["cr3"], "mode": paging.mode_of(regs["cr0"], regs["cr4"], regs["efer"])}

    def _cpu(self) -> guest.ProcessView:
        """vCPU 0's own address space (its CR3 and paging mode), read from its registers."""
        cpu = self.cpu_paging()
        if cpu is None:
            raise MemoryFault("VirtualBox gdb stub: vCPU 0's registers are unreadable")
        return guest.ProcessView(self, {"pid": 0, **cpu})

    def read_mem(self, addr: int, size: int) -> bytes:
        try:
            view = self._cpu()
        except MemoryFault as exc:
            self._wall = WallReport(Wall.NOT_READY, str(exc))
            return b""
        data = view.read_mem(addr, size)
        self._wall = view.wall()
        return data

    def write_mem(self, addr: int, data: bytes) -> WallReport:
        try:
            view = self._cpu()
        except MemoryFault as exc:
            self._wall = WallReport(Wall.NOT_READY, str(exc))
            return self._wall
        self._wall = view.write_mem(addr, data)
        return self._wall

    def snapshot(self, name: str) -> Outcome:
        return self._step("snapshot take", "snapshot", self.vm, "take", name, "--live")

    def _off(self) -> None:
        """Power off and wait until VirtualBox has let go of the machine (else it is locked)."""
        if self.alive():
            self._run("controlvm", self.vm, "poweroff")
        end = time.monotonic() + 30.0
        while self.state() in (*LIVE, "stopping") and time.monotonic() < end:
            time.sleep(0.3)

    def rollback(self, name: str) -> Outcome:
        """A snapshot is restored with the VM off, then the VM starts from it again."""
        self._off()
        restored = self._step("snapshot restore", "snapshot", self.vm, "restore", name)
        if not restored.ok:
            return restored
        return self._step("startvm", "startvm", self.vm, "--type", self.info.get("type", "gui"))

    def dump(self, out: Path) -> Outcome:
        return self._step("dumpvmcore", "debugvm", self.vm, "dumpvmcore", f"--filename={out}")

    def wall(self) -> WallReport:
        return self._wall

    def record(self) -> dict:
        return dict(self.info)

    def close(self) -> None:
        """Power off and unregister; the VM's folder (its disk, snapshots) stays for the next
        start in this workspace, unless that start asks for a fresh one."""
        self._off()
        self._run("unregistervm", self.vm)
