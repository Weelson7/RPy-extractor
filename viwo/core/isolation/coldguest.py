"""Cold patching inside the guest (doc 11.8): the same patch set `viwo patch` writes into a copy,
written into the files of the guest itself, before the program runs, so a check that runs once
at start sees the patched file. Every file the set touches is pulled from the guest through the
tier's file channel (VirtualBox: `guestcontrol`, Guest Additions; QEMU: its guest agent), kept
as the original once, staged in the session folder and patched there with the cold writer
(core.patchsets: located, verified byte for byte), then pushed back. All or nothing: a set that
does not plan clean writes nothing. `restore` pushes the originals back. A guest password is
used for that one call and never kept or said."""

import shutil
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

from .. import patchsets


def guest_path(guest_dir: str, rel: str) -> str:
    """`rel` (a patch's file, with /) under the guest folder, in the guest's own spelling."""
    windows = "\\" in guest_dir or (len(guest_dir) > 1 and guest_dir[1] == ":")
    sep = "\\" if windows else "/"
    return guest_dir.rstrip("\\/") + sep + rel.replace("/", sep).lstrip("\\/")


def _files(patch_set: dict) -> list[str]:
    names = sorted({str(p.get("file", "")) for p in patch_set["patches"]})
    unsafe = [n for n in names if ws.safe_member(n) is None]
    if unsafe:
        raise ViwoError("invalid_request", f"unsafe file names in the set: {', '.join(unsafe)}")
    return names


def deploy(rt, session, where: Path, patch_set: dict, guest: dict, log) -> dict:
    """`guest`: {"dir": the program's folder in the guest, "creds": a guest account or {}}."""
    guest_dir, creds = guest["dir"], guest.get("creds") or {}
    files = _files(patch_set)
    stage, originals = where / "cold" / "game", where / "cold" / "originals"
    shutil.rmtree(stage, ignore_errors=True)
    for rel in files:
        data = session.get_file(guest_path(guest_dir, rel), creds)
        for root in (stage, originals):
            path = ws.member_path(root, rel)
            if path is not None and (root is stage or not path.exists()):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        log(f"Pulled {rel} from the guest ({len(data)} bytes)", "info")
    report = patchsets.plan(stage, patch_set, rt.os)
    if not report["ok"]:
        return {**report, "deployed": []}
    for patch, result in zip(patch_set["patches"], report["results"]):
        if result["status"] == "ready" and not patchsets.write(stage, patch, result):
            raise ViwoError("failed", f"the staged copy of {result['file']} did not verify")
    for rel in files:
        session.put_file(guest_path(guest_dir, rel), ws.member_path(stage, rel).read_bytes(), creds)
        log(f"Wrote the patched {rel} into the guest", "info")
    return {**report, "deployed": files, "guest_dir": guest_dir}


def restore(session, where: Path, guest: dict, log) -> dict:
    """Push every kept original back into the guest; the originals stay until a fresh start."""
    guest_dir, creds = guest["dir"], guest.get("creds") or {}
    originals = where / "cold" / "originals"
    files = sorted(p.relative_to(originals).as_posix() for p in originals.rglob("*") if p.is_file())
    for rel in files:
        session.put_file(guest_path(guest_dir, rel), (originals / rel).read_bytes(), creds)
        log(f"Put the original {rel} back into the guest", "info")
    return {"restored": files}
