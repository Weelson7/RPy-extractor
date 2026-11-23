"""Tier 1: VirtualBox (doc 11.8). ViWo drives `VBoxManage` as a separate process (VirtualBox
base package, GPL-3.0 for 7.x; never imported, and NOT the proprietary Extension Pack) and the
VM's own gdb stub (vbox_session.py). The guest boots from a copy of the image in the session's
folder (VirtualBox rewrites a disk's header as soon as it registers it, so the user's image is
never attached): a raw image or any format qemu-img reads is converted to VDI, a VDI/VMDK/VHD is
copied and given a new identity; an .iso is an installer, booted with a new empty disk. The copy
is kept between sessions (snapshots live with it) unless `fresh`. No network unless asked, the
gdb stub on loopback only, UEFI with a virtual TPM 2.0 when asked (`efi`), snapshots live on
hardware acceleration. A `share` folder is a read-only VirtualBox shared folder (the guest needs
VirtualBox's Guest Additions to see it; their CD is attached for that). ViWo does not install
VirtualBox (a kernel driver): it locates the user's install. Reference build: VirtualBox
7.2.22-175245, VirtualBox-7.2.22-175245-Win.exe, 178,101,352 bytes, sha256
afd0ff1656cbe04ed88ce619594ae021419d97cce89fa9bdc443e9a963f1713f; proven on it with a long-mode
guest (tests/test_isolation_real.py)."""

import hashlib
import shutil
import socket
import time
from pathlib import Path

from viwo.contracts.patcher import PatcherBackend, PatchTarget, Wall, WallReport
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from .guest import VOLATILITY
from .vbox_session import HOST, LIVE, VBoxSession, _tail

VBOX = DependencySpec.of("virtualbox")
QEMU = DependencySpec.of("qemu")
RAW = (".img", ".raw", ".bin")
OWN = (".vdi", ".vmdk", ".vhd")  # VirtualBox's own formats: copied, given a new UUID
NEW_DISK_MB = 65536


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


def vm_name(target: PatchTarget, staging: Path) -> str:
    """One VM per workspace: the program's name plus a short hash of the session folder."""
    tag = hashlib.sha256(str(staging.resolve()).encode()).hexdigest()[:6]
    return f"viwo-{target.exe.stem or 'guest'}-{tag}"


class VirtualBoxPatcher(PatcherBackend):
    backend_id, license, tier = "vbox", "GPL-3.0", 1
    requirement = "VirtualBox base package (VBoxManage); a kernel driver and one-time elevation"
    requires = (VBOX, VOLATILITY)  # ready() needs VirtualBox only

    def ready(self, os) -> WallReport:
        if os.tools.locate(VBOX) is None:
            return WallReport(Wall.NOT_READY, self.requirement)
        return WallReport()

    def start(self, target: PatchTarget, ctx, *, snapshot: bool = False):
        tool = ctx.os.tools.locate(VBOX)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=self.requirement)
        if target.image is None or not target.image.is_file():
            return Outcome(
                OutcomeKind.UNAVAILABLE, error="VirtualBox needs a guest image (--image)"
            )
        ctx.staging.mkdir(parents=True, exist_ok=True)
        vm = vm_name(target, ctx.staging)
        info = {"backend": self.backend_id, "vm": vm, "gdb": _free_port(), "since": time.time()}
        info.update(type="headless" if target.headless else "gui", image=str(target.image))
        session = VBoxSession(ctx.os, tool.argv_prefix, info)
        outcome = _machine(session, target, ctx)
        if outcome.ok:
            outcome = session._step("startvm", "startvm", vm, "--type", info["type"])
        if not outcome.ok:
            session.close()
            return outcome
        net = "OPEN (NAT, asked for)" if target.network else "closed"
        ctx.log(f"VirtualBox VM {vm} started; network {net}; gdb stub on loopback", "info")
        if snapshot and not (made := session.snapshot("base")).ok:
            ctx.log(f"VirtualBox base snapshot failed: {made.error}", "warn")
        return session

    def reattach(self, record: dict, ctx):
        tool = ctx.os.tools.locate(VBOX)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=self.requirement)
        session = VBoxSession(ctx.os, tool.argv_prefix, dict(record))
        if session.state() in LIVE:
            return session
        return Outcome(OutcomeKind.UNAVAILABLE, error="the VirtualBox VM of this session is off")


def _machine(session: VBoxSession, target: PatchTarget, ctx) -> Outcome:
    """Register the workspace's VM (created once, kept), then set this start's options."""
    vm, folder = session.vm, ctx.staging / session.vm
    settings = folder / f"{vm}.vbox"
    session._run("unregistervm", vm)  # a VM left registered by a session that died
    if target.fresh and folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
        ctx.log(f"VirtualBox: the earlier VM of this workspace is discarded ({folder})", "info")
    if settings.is_file():
        ctx.log(f"VirtualBox: the VM kept from before ({folder})", "info")
        outcome = session._step("registervm", "registervm", str(settings))
    else:
        outcome = _create(session, target, ctx, folder)
    return outcome if not outcome.ok else _configure(session, target, ctx)


def _create(session: VBoxSession, target: PatchTarget, ctx, folder: Path) -> Outcome:
    vm = session.vm
    steps = [("createvm", "--name", vm, "--basefolder", str(ctx.staging), "--register",
              "--ostype", "Other_64"),
             ("storagectl", vm, "--name", "SATA", "--add", "sata", "--portcount", "4")]  # fmt: skip
    for args in steps:
        if not (outcome := session._step(args[0], *args)).ok:
            return outcome
    disk = _disk(session, target, ctx, folder)
    if isinstance(disk, Outcome):
        return disk
    attach = ("storageattach", vm, "--storagectl", "SATA", "--device", "0")
    outcome = session._step(
        "attach disk", *attach, "--port", "0", "--type", "hdd", "--medium", disk
    )
    if outcome.ok and target.image.suffix.lower() == ".iso":
        dvd = ("--port", "1", "--type", "dvddrive", "--medium", str(target.image))
        outcome = session._step("attach installer", *attach, *dvd)
    return outcome


def _disk(session: VBoxSession, target: PatchTarget, ctx, folder: Path):
    """The session's own disk (path) for the image, or an Outcome saying why there is none."""
    image, suffix = target.image, target.image.suffix.lower()
    folder.mkdir(parents=True, exist_ok=True)
    disk = folder / "disk.vdi"
    if suffix == ".iso":
        ctx.log(
            f"VirtualBox: installer {image.name}, a new empty {NEW_DISK_MB >> 10} GB disk", "info"
        )
        args = ("createmedium", "disk", "--filename", str(disk), "--size", str(NEW_DISK_MB))
        return _made(session._step("createmedium", *args, "--format", "VDI"), disk)
    size = image.stat().st_size >> 20
    ctx.log(
        f"VirtualBox: copying {image.name} ({size} MB) into {folder}; it is never written", "info"
    )
    qemu = ctx.os.tools.locate(QEMU)
    img = Path(qemu.path).with_name("qemu-img" + Path(qemu.path).suffix) if qemu else None
    if img is not None and img.is_file():
        result = ctx.os.process.run(
            [str(img), "convert", "-O", "vdi", str(image), str(disk)], timeout=7200
        )
        why = f"qemu-img convert: {_tail(result)}"
        return disk if result.ok else Outcome(OutcomeKind.FAILED, error=why)
    if suffix in RAW:
        args = ("convertfromraw", str(image), str(disk), "--format", "VDI")
        return _made(session._step("convertfromraw", *args), disk)
    if suffix in OWN:
        own = folder / f"disk{suffix}"
        shutil.copyfile(image, own)
        return _made(session._step("sethduuid", "internalcommands", "sethduuid", str(own)), own)
    why = f"{suffix} needs qemu-img to become a VirtualBox disk: `viwo install qemu`"
    return Outcome(OutcomeKind.UNAVAILABLE, error=why)


def _made(outcome: Outcome, disk: Path):
    return str(disk) if outcome.ok else outcome


def _graphics(target: PatchTarget) -> tuple[str, ...]:
    """VMSVGA with 3D (Direct3D/OpenGL through the host GPU) when asked."""
    if not target.gpu:
        return ()
    return ("--graphicscontroller", "vmsvga", "--accelerate-3d", "on", "--vram", "256")


def _configure(session: VBoxSession, target: PatchTarget, ctx) -> Outcome:
    """This start's options (memory, CPUs, network, firmware, TPM, the gdb stub, a share)."""
    vm = session.vm
    args = ["modifyvm", vm, "--memory", str(target.memory_mb), "--cpus", str(target.cpus),
            "--nic1", "nat" if target.network else "none", "--audio-enabled", "off",
            "--mouse", "usbtablet", "--usb-ohci", "on",
            "--firmware", "efi" if target.efi else "bios", *_graphics(target),
            "--tpm-type", "2.0" if target.efi else "none",
            "--guest-debug-provider", "gdb", "--guest-debug-io-provider", "tcp",
            "--guest-debug-address", HOST,
            "--guest-debug-port", str(session.info["gdb"])]  # fmt: skip
    if not (outcome := session._step("modifyvm", *args)).ok:
        return outcome
    if target.efi:
        ctx.log("VirtualBox: UEFI with a virtual TPM 2.0", "info")
    session._run("sharedfolder", "remove", vm, "--name", "viwo-share")
    if target.share is None:
        return outcome
    share = ("--name", "viwo-share", "--hostpath", str(target.share), "--readonly", "--automount")
    outcome = session._step("sharedfolder", "sharedfolder", "add", vm, *share)
    if outcome.ok:
        ctx.log(f"VirtualBox: {target.share} shared read-only as viwo-share (Guest Additions "
                "in the guest see it; their CD is on the third drive)", "info")  # fmt: skip
        attach = ("storageattach", vm, "--storagectl", "SATA", "--port", "2", "--device", "0")
        cd = session._step(
            "Guest Additions CD", *attach, "--type", "dvddrive", "--medium", "additions"
        )
        if not cd.ok:
            ctx.log(f"VirtualBox: {cd.error}; the share needs Guest Additions in the guest", "warn")
    return outcome
