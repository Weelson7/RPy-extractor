"""Tier 3: LibVMI (DRAKVUF's introspection layer; doc 11.8). On a bare-metal Linux host running
Xen, or KVM with KVMi, ViWo introspects a running domain from outside it: guest physical memory
through the host's own LibVMI (the libvmi_io worker, LibVMI's calls in a process of their own),
so a located process (core.isolation.guest) is read and written through its own page tables as on
T1 and T2; the RAM image Volatility reads comes from LibVMI's `vmi-dump-memory`; the domain is
paused, resumed, snapshotted and restored by the hypervisor's own control (`virsh` on KVM, `xl`
on Xen). The domain is the user's: ViWo attaches to it by name (`--domain`, and on KVM its
`--kvmi-socket`), never boots or destroys it, and closing the session leaves it running. A raw
address is not translated here (T3 reads no vCPU register): locate the program first. On Windows
and WSL2 there is no such host, so the tier is not ready and says why. The real-host run is still
to do (on a bootable Linux stick); everything here is unit-tested with fakes."""

import json
import platform
import queue
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

from viwo.contracts.patcher import (
    MemoryFault,
    PatcherBackend,
    PatchSession,
    PatchTarget,
    Wall,
    WallReport,
)  # fmt: skip
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from .guest import VOLATILITY

VMI_READ = DependencySpec("vmi-dump-memory", "LibVMI dump-memory", executables=("vmi-dump-memory",),
                          hint="install LibVMI (its example tools) on the host")  # fmt: skip
VIRSH = DependencySpec("virsh", "libvirt virsh", executables=("virsh",), hint="install libvirt")
XL = DependencySpec("xl", "Xen xl", executables=("xl",), hint="install the Xen tool stack")
WORKER = Path(__file__).resolve().parents[2] / "data" / "workers" / "libvmi_io.py"
NO_VA = "T3 addresses guest memory through a located program: `isolate locate NAME` first"
LIVE = ("running", "paused", "blocked", "idle", "in shutdown")
ANSWER = 60.0  # seconds LibVMI may take to open a domain or answer one access


def _no_host() -> bool:
    """True where there is no bare-metal Linux VMI host: Windows, or a WSL2 kernel."""
    return platform.system() != "Linux" or "microsoft" in platform.uname().release.lower()


def has_libvmi() -> bool:
    import ctypes.util

    return ctypes.util.find_library("vmi") is not None


def control_of(os):
    """(argv prefix, kind "virsh" | "xl") of the located hypervisor control, or None."""
    if (tool := os.tools.locate(VIRSH)) is not None:
        return tool.argv_prefix, "virsh"
    if (tool := os.tools.locate(XL)) is not None:
        return tool.argv_prefix, "xl"
    return None


def _pump(stream, lines: queue.Queue) -> None:
    for line in stream:
        lines.put(line)
    lines.put("")


class _Remote:
    """Guest physical memory through one running libvmi_io worker; every answer has a deadline
    (a LibVMI that hangs is said, never waited on forever)."""

    def __init__(self, proc, lines: queue.Queue) -> None:
        self._proc, self._lines = proc, lines

    def line(self) -> str:
        try:
            return self._lines.get(timeout=ANSWER)
        except queue.Empty as exc:
            raise MemoryFault(f"LibVMI did not answer within {ANSWER:g} s") from exc

    def ask(self, **request) -> dict:
        self._proc.stdin.write(json.dumps(request) + "\n")
        self._proc.stdin.flush()
        line = self.line()
        reply = json.loads(line) if line.strip() else {"error": "the LibVMI worker ended"}
        if not reply.get("ok"):
            raise MemoryFault(f"LibVMI: {reply.get('error')}")
        return reply

    def read(self, pa: int, n: int) -> bytes:
        return bytes.fromhex(self.ask(op="read", pa=pa, n=n)["hex"])

    def write(self, pa: int, data: bytes) -> None:
        self.ask(op="write", pa=pa, hex=data.hex())


class VmiSession(PatchSession):
    def __init__(self, os, info: dict, control) -> None:
        self._os, self.info = os, info
        self.domain = str(info["domain"])
        self._ctrl, self.kind = control
        self._wall = WallReport()

    def _ctrl_run(self, *args: str, timeout: int = 120):
        return self._os.process.run([*self._ctrl, *args], timeout=timeout)

    def state(self) -> str:
        if self.kind == "virsh":
            result = self._ctrl_run("domstate", self.domain, timeout=30)
            return (result.stdout or "").strip().lower() if result.ok else ""
        result = self._ctrl_run("list", self.domain, timeout=30)
        rows = (result.stdout or "").splitlines()[1:] if result.ok else []
        flags = rows[0].split()[-2] if rows and len(rows[0].split()) >= 6 else ""
        return "" if not result.ok else "paused" if "p" in flags else "running"

    def running(self) -> bool:
        return self.state() == "running"

    def alive(self) -> bool:
        return self.state() in LIVE

    def suspend(self) -> None:
        self._ctrl_run("suspend" if self.kind == "virsh" else "pause", self.domain)

    def resume(self) -> None:
        self._ctrl_run("resume" if self.kind == "virsh" else "unpause", self.domain)

    @contextmanager
    def physical(self):
        argv = [sys.executable, "-I", str(WORKER), self.domain]
        argv += [self.info["kvmi"]] if self.info.get("kvmi") else []
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        except OSError as exc:
            raise MemoryFault(f"LibVMI worker: {exc}") from exc
        lines: queue.Queue = queue.Queue()
        threading.Thread(target=_pump, args=(proc.stdout, lines), daemon=True).start()
        try:
            remote = _Remote(proc, lines)
            hello = json.loads(remote.line() or "{}")
            if not hello.get("ok"):
                raise MemoryFault(f"LibVMI: {hello.get('error') or 'no answer'}")
            yield remote
        except (OSError, ValueError) as exc:
            raise MemoryFault(f"LibVMI worker: {exc}") from exc
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            proc.stdout.close()

    def read_mem(self, addr: int, size: int) -> bytes:
        self._wall = WallReport(Wall.NOT_READY, NO_VA)
        return b""

    def write_mem(self, addr: int, data: bytes) -> WallReport:
        self._wall = WallReport(Wall.NOT_READY, NO_VA)
        return self._wall

    def _saved(self, name: str) -> Path:
        return Path(self.info["folder"]) / f"{name}.xl"

    def snapshot(self, name: str) -> Outcome:
        if self.kind == "virsh":
            return self._step("snapshot-create-as", self.domain, name)
        return self._step("save", "-c", self.domain, str(self._saved(name)))  # -c: keeps running

    def rollback(self, name: str) -> Outcome:
        if self.kind == "virsh":
            return self._step("snapshot-revert", self.domain, name)
        if not self._saved(name).is_file():
            return Outcome(OutcomeKind.FAILED, error=f"no saved state {name!r} of {self.domain}")
        self._ctrl_run("destroy", self.domain)
        return self._step("restore", str(self._saved(name)))

    def _step(self, *args: str) -> Outcome:
        result = self._ctrl_run(*args, timeout=600)
        if result.ok:
            return Outcome(OutcomeKind.OK)
        tail = (result.stderr or result.stdout or "").strip()[-200:]
        return Outcome(OutcomeKind.FAILED, error=f"{self.kind} {args[0]}: {tail}")

    def dump(self, out: Path) -> Outcome:
        tool = self._os.tools.locate(VMI_READ)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=VMI_READ.hint)
        result = self._os.process.run([*tool.argv_prefix, self.domain, str(out)], timeout=1800)
        if result.ok:
            return Outcome(OutcomeKind.OK)
        return Outcome(OutcomeKind.FAILED, error=(result.stderr or result.stdout or "")[-200:])

    def wall(self) -> WallReport:
        return self._wall

    def record(self) -> dict:
        return dict(self.info)


class VmiPatcher(PatcherBackend):
    backend_id, license, tier = "libvmi", "LGPL-3.0", 3
    requirement = "a bare-metal Linux Xen or KVMi host with LibVMI (not available on Windows)"
    requires = (VOLATILITY,)

    def ready(self, os) -> WallReport:
        if _no_host():
            return WallReport(Wall.NOT_READY, self.requirement)
        if not has_libvmi():
            return WallReport(Wall.NOT_READY, "install LibVMI (libvmi.so) on the host")
        if control_of(os) is None:
            return WallReport(Wall.NOT_READY, "install libvirt (virsh) or Xen (xl)")
        return WallReport()

    def start(self, target: PatchTarget, ctx, *, snapshot: bool = False):
        report = self.ready(ctx.os)
        if report.blocked:
            return Outcome(OutcomeKind.UNAVAILABLE, error=report.detail)
        domain = (target.args[0] if target.args else target.exe.stem) or "guest"
        info = {"backend": self.backend_id, "domain": domain, "folder": str(ctx.staging)}
        info["kvmi"] = target.args[1] if len(target.args) > 1 else ""
        ctx.staging.mkdir(parents=True, exist_ok=True)
        session = VmiSession(ctx.os, info, control_of(ctx.os))
        if not session.alive():
            return Outcome(OutcomeKind.UNAVAILABLE, error=f"domain {domain} is not running")
        try:
            with session.physical():
                pass  # LibVMI opens the domain: the probe of the whole path
        except MemoryFault as exc:
            return Outcome(OutcomeKind.UNAVAILABLE, error=str(exc))
        ctx.log(f"LibVMI on domain {domain} ({session.kind}); it keeps running when the session "
                "closes", "info")  # fmt: skip
        if snapshot and not (made := session.snapshot("base")).ok:
            ctx.log(f"Base snapshot failed: {made.error}", "warn")
        return session

    def reattach(self, record: dict, ctx):
        control = control_of(ctx.os)
        if control is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error="virsh / xl is gone")
        session = VmiSession(ctx.os, dict(record), control)
        if session.alive():
            return session
        return Outcome(OutcomeKind.UNAVAILABLE, error=f"domain {session.domain} is not running")
