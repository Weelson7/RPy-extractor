"""What a QEMU guest boots from (doc 11.8 T2): its disk, its firmware and a shared folder. The
user's image is never written: a disk image runs on a qcow2 overlay beside the session (kept
between sessions so snapshots survive, unless `fresh`), an installer .iso boots with a new empty
qcow2 disk and the .iso read-only. `efi` boots QEMU's own UEFI build (edk2, shipped with QEMU)
with its variables in the session folder; QEMU on Windows has no virtual TPM (no swtpm), which is
said. A `share` folder becomes a read-only CD (share.py)."""

import json
import shutil
from pathlib import Path

from viwo.contracts.patcher import PatchTarget

from . import share

NEW_DISK = "64G"


def qemu_img(tool) -> Path:
    return Path(tool.path).with_name("qemu-img" + Path(tool.path).suffix)


def _format(os, img: Path, image: Path) -> str:
    info = os.process.run([str(img), "info", "--output=json", str(image)], timeout=60)
    try:
        return str(json.loads(info.stdout or "")["format"]) if info.ok else ""
    except (ValueError, KeyError, TypeError):
        return ""


def overlay_of(os, tool, target: PatchTarget, staging: Path) -> tuple[list[str], str]:
    """(the -drive arguments, a note). Every write goes to a qcow2 overlay beside the session;
    without qemu-img it is QEMU's own throwaway overlay (`snapshot=on`), which cannot hold a
    snapshot. An installer .iso gets a new empty disk and stays a read-only CD."""
    img, over = qemu_img(tool), staging / "overlay.qcow2"
    installer = target.image.suffix.lower() == ".iso"
    if target.fresh and over.is_file():
        over.unlink()
    cd = ["-drive", f"file={target.image},media=cdrom,readonly=on", "-boot", "order=cd"]
    tail = cd if installer else []
    if over.is_file():
        return ["-drive", f"file={over},format=qcow2", *tail], f"disk kept from before ({over})"
    if installer and img.is_file():
        if os.process.run([str(img), "create", "-f", "qcow2", str(over), NEW_DISK], timeout=60).ok:
            return ["-drive", f"file={over},format=qcow2", *cd], f"installer, new {NEW_DISK} disk"
    elif img.is_file() and (fmt := _format(os, img, target.image)):
        argv = [str(img), "create", "-f", "qcow2", "-F", fmt, "-b", str(target.image), str(over)]
        if os.process.run(argv, timeout=60).ok:
            return ["-drive", f"file={over},format=qcow2"], f"new overlay on the {fmt} image"
    if installer:
        return cd, "installer only: no qemu-img to make a disk, so nothing can be installed"
    return ["-drive", f"file={target.image},snapshot=on"], "throwaway overlay (no qemu-img)"


def firmware(tool, target: PatchTarget, staging: Path, log) -> list[str]:
    """UEFI (QEMU's edk2) when asked: read-only code, writable variables of the session."""
    if not target.efi:
        return []
    share_dir = Path(tool.path).parent / "share"
    code, blank = share_dir / "edk2-x86_64-code.fd", share_dir / "edk2-i386-vars.fd"
    if not code.is_file() or not blank.is_file():
        log(f"QEMU: no UEFI firmware beside this QEMU ({code.name}); booting BIOS", "warn")
        return []
    variables = staging / "efi-vars.fd"
    if target.fresh or not variables.is_file():
        shutil.copyfile(blank, variables)
    log("QEMU: UEFI; no virtual TPM on this QEMU (a guest that insists on one: the vbox tier)",
        "warn")  # fmt: skip
    return ["-drive", f"if=pflash,format=raw,readonly=on,file={code}",
            "-drive", f"if=pflash,format=raw,file={variables}"]  # fmt: skip


def media(os, tool, target: PatchTarget, staging: Path, log) -> list[str]:
    """Every -drive the guest gets: disk (or installer), firmware, the shared folder."""
    if target.gpu:
        log("QEMU: no 3D acceleration on this host (no virgl on Windows); 3D: the vbox tier",
            "warn")  # fmt: skip
    drive, note = overlay_of(os, tool, target, staging)
    log(f"QEMU disk: {note}; the image itself is not written", "info")
    args = [*drive, *firmware(tool, target, staging, log)]
    if target.share is not None:
        cd = share.build(target.share, staging / "share.iso", log)
        args += ["-drive", f"file={cd},media=cdrom,readonly=on"]
    return args
