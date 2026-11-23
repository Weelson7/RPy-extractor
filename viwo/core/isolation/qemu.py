"""Tier 2: QEMU (doc 11.8). ViWo runs `qemu-system-x86_64` as a separate process (the pinned
portable build, `viwo install qemu`, or the user's own) and holds the guest behind a closed
boundary: the base image is never written (a disposable qcow2 overlay takes every change), the
network is off unless asked, and the control channels (QMP, gdbstub) listen on loopback only. The
accelerator is hardware (WHPX on Windows, KVM on Linux) when it really starts, else TCG, and which
one is said; WHPX cannot save a snapshot, so a session that wants snapshots runs on TCG. QEMU needs
no driver and no elevation. The session itself is qemu_session.QemuSession; what it boots from
(disk overlay, installer, UEFI, a shared folder) is qemu_media."""

import socket
import sys
import time

from viwo.contracts.errors import ViwoError
from viwo.contracts.patcher import PatcherBackend, PatchTarget, Wall, WallReport
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind
from viwo.os import pid_alive

from .guest import VOLATILITY
from .qemu_media import media
from .qemu_session import HOST, QemuSession
from .share import PYCDLIB

QEMU = DependencySpec.of("qemu")
HARDWARE = "whpx" if sys.platform == "win32" else "kvm"
BOOT_WAIT = 20.0  # seconds for QEMU's control channel to answer after the launch


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


def _up(session: QemuSession, child) -> bool:
    """Wait for QEMU's control channel; give up at once when the process has exited."""
    end = time.monotonic() + BOOT_WAIT
    while time.monotonic() < end:
        if session.answers():
            return True
        if not child.alive():
            return False
    return False


def accel_of(os, argv_prefix) -> str:
    """ "whpx" (Windows) or "kvm" (Linux) when this QEMU lists it, else the portable "tcg"."""
    return accelerators(os, argv_prefix, "", False)[0][0]


def accelerators(os, argv_prefix, wanted: str, snapshot: bool) -> tuple[list[str], str]:
    """(the accelerators to try in order, a note for the user). Hardware first when this QEMU
    has it and it can do what was asked; TCG always works and is last."""
    if wanted:
        return [wanted], ""
    result = os.process.run([*argv_prefix, "-accel", "help"], timeout=30)
    listed = ((result.stdout or "") + (result.stderr or "")).lower()
    if HARDWARE not in listed:
        return ["tcg"], f"this QEMU has no {HARDWARE}: TCG (slower)"
    if HARDWARE == "whpx" and snapshot:
        return ["tcg"], "WHPX cannot save a snapshot: TCG (slower), as a snapshot was asked for"
    return [HARDWARE, "tcg"], ""


def guest_args(target: PatchTarget, accel: str, ports: tuple[int, ...]) -> list[str]:
    qmp, gdb, *agent = ports
    args = ["-accel", accel, "-m", str(target.memory_mb), "-smp", str(target.cpus)]
    args += ["-name", f"viwo-{target.exe.stem or 'guest'}", "-usb", "-device", "usb-tablet"]
    args += ["-qmp", f"tcp:{HOST}:{qmp},server=on,wait=off", "-gdb", f"tcp:{HOST}:{gdb}"]
    if agent:  # the guest agent's virtio-serial channel (files inside the guest)
        args += ["-chardev", f"socket,id=qga0,host={HOST},port={agent[0]},server=on,wait=off",
                 "-device", "virtio-serial", "-device",
                 "virtserialport,chardev=qga0,name=org.qemu.guest_agent.0"]  # fmt: skip
    if not target.network:
        args += ["-nic", "none"]
    if target.headless:
        args += ["-display", "none"]
    if target.halted:
        args += ["-S"]
    return args


class QemuPatcher(PatcherBackend):
    backend_id, license, tier = "qemu", "GPL-2.0", 2
    requirement = "QEMU (qemu-system-x86_64): `viwo install qemu`, or your own install"
    requires = (QEMU, PYCDLIB, VOLATILITY)  # ready() needs QEMU only

    def ready(self, os) -> WallReport:
        if os.tools.locate(QEMU) is None:
            return WallReport(Wall.NOT_READY, self.requirement)
        return WallReport()

    def start(self, target: PatchTarget, ctx, *, snapshot: bool = False):
        tool = ctx.os.tools.locate(QEMU)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=self.requirement)
        if target.image is None or not target.image.is_file():
            return Outcome(OutcomeKind.UNAVAILABLE, error="QEMU needs a guest disk image (--image)")
        ctx.staging.mkdir(parents=True, exist_ok=True)
        drive = media(ctx.os, tool, target, ctx.staging, ctx.log)
        order, why = accelerators(ctx.os, tool.argv_prefix, target.accel, snapshot)
        if why:
            ctx.log(f"QEMU: {why}", "warn")
        session = self._boot(tool, target, ctx, (order, drive))
        if isinstance(session, QemuSession) and snapshot:
            made = session.snapshot("base")
            if not made.ok:
                ctx.log(f"QEMU base snapshot failed: {made.error}", "warn")
        return session

    def _boot(self, tool, target: PatchTarget, ctx, plan):
        order, drive = plan
        for accel in order:
            ports = (_free_port(), _free_port(), _free_port())
            argv = [*tool.argv_prefix, *guest_args(target, accel, ports), *drive, *target.args]
            child = ctx.os.process.launch(argv, ctx.staging)
            info = {"backend": self.backend_id, "qmp": ports[0], "gdb": ports[1], "qga": ports[2]}
            info.update(accel=accel, pid=child.pid, image=str(target.image), since=time.time())
            session = QemuSession(info, child, wait=1.0)
            if _up(session, child):
                net = "OPEN (asked for)" if target.network else "closed"
                ctx.log(f"QEMU started on {accel}; network {net}; control on loopback", "info")
                return session
            child.kill()
            ctx.log(f"QEMU did not start on {accel}", "warn")
        return Outcome(OutcomeKind.FAILED, error="QEMU exited at once (image, memory or arguments)")

    def reattach(self, record: dict, ctx):
        session = QemuSession(dict(record), None, wait=2.0)
        if session.answers():
            return session
        if pid_alive(int(record.get("pid") or 0)):
            raise ViwoError("busy", "QEMU runs but its control channel does not answer yet")
        return Outcome(OutcomeKind.UNAVAILABLE, error="the QEMU of this session has exited")
