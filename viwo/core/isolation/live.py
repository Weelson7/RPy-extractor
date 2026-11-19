"""The cold+live bridge (doc 11.8): one located patch recipe applied either way. A patch set
locates an edit in a PE as a file offset (core.patchsets / core.patch_tools); cold it is written
into the patched copy (core.patchsets.write), live it is written at the virtual address the same
offset loads to (patch_tools.address_of), under the atomic suspend -> write -> verify -> resume
(core.isolation.atomic_write). So the same recipe, or its AOB signature, drives both arms. `drive`
starts a tier and applies a set live; with no set it starts and closes (a readiness probe)."""

from dataclasses import dataclass
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.contracts.patcher import PatchTarget
from viwo.contracts.types import Outcome

from .. import patchsets
from ..context import core_context
from ..patch_tools import address_of, pe
from . import atomic_write

RUNTIME_DIR = ".runtime"


def located_va(data: bytes, offset: int, base: int = 0) -> int:
    """The virtual address a file offset loads at. `base` rebases onto the module's live load
    address when ASLR moved it; 0 keeps the PE's own preferred image base."""
    va = address_of(data, offset)
    info = pe(data)
    if base and info:
        return base + (va - info["base"])
    return va


def write_located(session, data: bytes, offset: int, new: bytes, base: int = 0):
    """Apply one located edit to the live target atomically, at its virtual address."""
    return atomic_write(session, located_va(data, offset, base), new)


def apply_live(rt, session, game: Path, patch_set: dict, base: int = 0) -> dict:
    """Plan the set against the game's files, then write every ready patch into the live target
    (the same located offset the cold writer uses, turned into a virtual address)."""
    report = patchsets.plan(game, patch_set, rt.os)
    for patch, r in zip(patch_set["patches"], report["results"]):
        if r["status"] not in ("ready", "already"):
            r["written"], r["wall"] = False, ""
            continue
        path = ws.member_path(game, str(patch.get("file", "")))
        data = path.read_bytes() if path is not None and path.is_file() else b""
        wall = write_located(session, data, r["offset"], bytes.fromhex(r["new"]), base)
        r["wall"], r["detail"] = wall.wall.value, wall.detail
        r["written"] = not wall.blocked
    ready = [r for r in report["results"] if r["status"] == "ready"]
    report["written"] = bool(ready) and all(r.get("written") for r in ready)
    return report


@dataclass
class IsolateRequest:
    exe: Path
    workspace: Path
    tier: str = ""
    image: Path | None = None
    pid: int = 0
    patchset: Path | None = None
    base: int = 0
    snapshot: bool = False


def _backend(rt, tier: str):
    """The isolation backend for `tier` (a backend id), or the first ready one when tier is ''."""
    found = sorted(
        (b for b in rt.backends.values() if "isolation" in getattr(b, "families", ())),
        key=lambda b: b.tier,
    )
    if tier:
        for backend in found:
            if backend.backend_id == tier:
                return backend
        raise ViwoError("invalid_request", f"no isolation tier {tier!r}", hint="vbox|qemu|libvmi")
    for backend in found:
        if not backend.ready(rt.os).blocked:
            return backend
    walls = "; ".join(f"{b.backend_id}: {b.ready(rt.os).detail}" for b in found)
    raise ViwoError("unavailable", "no isolation tier is ready here", hint=walls)


def drive(rt, req: IsolateRequest, say=None) -> dict:
    """Start the target under a tier, apply a patch set live (when given), then close."""
    backend = _backend(rt, req.tier)
    report = backend.ready(rt.os)
    if report.blocked:
        raise ViwoError("unavailable", f"{backend.backend_id} not ready: {report.detail}")
    target = PatchTarget(req.exe, req.workspace, req.pid, req.image)
    ctx = core_context(rt, "isolate", req.exe.parent, rt.temp_root, say)
    ctx.staging = req.workspace / RUNTIME_DIR / "isolation" / backend.backend_id
    session = backend.start(target, ctx, snapshot=req.snapshot)
    if isinstance(session, Outcome):
        code = session.kind.value if session.kind.value != "ok" else "failed"
        raise ViwoError(code, session.error or f"{backend.backend_id} could not start")
    try:
        head = {"tier": backend.backend_id, "exe": str(req.exe)}
        if req.patchset is None:
            return {**head, "started": True}
        patch_set = patchsets.load(req.patchset)
        return {**head, **apply_live(rt, session, req.exe.parent, patch_set, req.base)}
    finally:
        session.close()
