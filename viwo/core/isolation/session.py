"""The isolation session's lifecycle (doc 11.8): `start` boots a target behind a tier and leaves
it running; every later action (status, pause, resume, snapshot, rollback, dump, patch, undo,
stop) rejoins it from the record the session left in the workspace
(`.runtime/isolation/session.json`: the tier and what its backend needs to reach the guest
again). So a session outlives the call that started it and is driven the same way from the CLI
and the API. One session per workspace. The guest process belongs to whoever started it: the
`viwo isolate start` that holds it, or the server. `locate` finds a program inside the guest
(core.isolation.guest): later patches and undo go through that process's address space."""

import json
import time
from dataclasses import dataclass
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.patcher import PatchTarget
from viwo.contracts.types import Outcome

from .. import patchsets
from ..context import core_context
from . import coldguest, guest, live, patching
from .qemu_session import NAME

ACTIONS = (
    "status", "pause", "resume", "snapshot", "rollback", "locate", "dump", "patch", "undo",
    "deploy", "restore", "stop",
)  # fmt: skip


def folder(workspace: Path) -> Path:
    return workspace / ".runtime" / "isolation"


def _record(workspace: Path) -> Path:
    return folder(workspace) / "session.json"


@dataclass
class IsolateRequest:
    workspace: Path
    image: Path | None = None
    exe: Path | None = None
    tier: str = ""
    pid: int = 0
    snapshot: bool = False
    guest: dict | None = None  # memory_mb, cpus, network, headless, accel, fresh, args


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


def _context(rt, workspace: Path, backend_id: str, say):
    ctx = core_context(rt, "isolate", workspace, rt.temp_root, say)
    ctx.staging = folder(workspace) / backend_id
    return ctx


def _raise(outcome: Outcome, what: str):
    code = outcome.kind.value if outcome.kind.value in ("unavailable", "failed") else "failed"
    raise ViwoError(code, outcome.error or what)


def start(rt, req: IsolateRequest, say=None):
    """Boot the target under a tier and leave it running. Returns (what to tell the user, the
    session): the caller that owns the guest process keeps the session to watch or stop it."""
    if (running := _rejoin(rt, req.workspace, say, missing_ok=True)) is not None:
        running[0].release()
        raise ViwoError("busy", "a session already runs in this workspace", hint="isolate stop")
    backend = _backend(rt, req.tier)
    report = backend.ready(rt.os)
    if report.blocked:
        raise ViwoError("unavailable", f"{backend.backend_id} not ready: {report.detail}")
    exe = req.exe or req.image or req.workspace
    target = PatchTarget(exe, req.workspace, req.pid, req.image, **(req.guest or {}))
    ctx = _context(rt, req.workspace, backend.backend_id, say)
    session = backend.start(target, ctx, snapshot=req.snapshot)
    if isinstance(session, Outcome):
        _raise(session, f"{backend.backend_id} could not start")
    record = {"tier": backend.backend_id, **session.record()}
    guest.drop(folder(req.workspace))  # a process located in an earlier guest is not this one
    (folder(req.workspace) / "journal.jsonl").unlink(missing_ok=True)  # nor its edits
    _record(req.workspace).parent.mkdir(parents=True, exist_ok=True)
    _record(req.workspace).write_text(json.dumps(record, indent=1), encoding="utf-8")
    session.release()
    ctx.log("Isolation session is up; `viwo isolate stop` (or closing the guest) ends it", "info")
    return {"started": True, **record}, session


def drive(rt, req: IsolateRequest, patchset: Path | None = None, base: int = 0, say=None) -> dict:
    """The one-shot form: start the target under a tier, apply a patch set live (when given),
    then close. With no set it starts and closes (a readiness probe of the whole tier)."""
    _, session = start(rt, req, say)
    try:
        head = {"tier": session_tier(req.workspace), "exe": str(req.exe or "")}
        if patchset is None:
            return {**head, "started": True}
        game = (req.exe or req.workspace).parent
        return {**head, **live.apply_live(rt, session, game, patchsets.load(patchset), base)}
    finally:
        session.close()
        forget(req.workspace)


def session_tier(workspace: Path) -> str:
    """The tier of the workspace's recorded session ('' when none is recorded)."""
    try:
        return str(json.loads(_record(workspace).read_text(encoding="utf-8"))["tier"])
    except (OSError, ValueError, KeyError):
        return ""


def _rejoin(rt, workspace: Path, say, missing_ok: bool = False):
    """(session, record) of the workspace's running session; a record whose guest has gone is
    removed and said."""
    path = _record(workspace)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        backend = _backend(rt, str(record["tier"]))
    except (OSError, ValueError, KeyError, ViwoError):
        record = backend = None
    session = None
    if backend is not None:
        session = backend.reattach(record, _context(rt, workspace, record["tier"], say))
    if session is None or isinstance(session, Outcome):
        path.unlink(missing_ok=True)
        if missing_ok:
            return None
        why = session.error if isinstance(session, Outcome) else "none was started here"
        raise ViwoError("not_found", f"no isolation session runs in this workspace ({why})")
    return session, record


def forget(workspace: Path) -> None:
    """The guest has ended: drop the record so the next start is not refused."""
    _record(workspace).unlink(missing_ok=True)
    guest.drop(folder(workspace))
    (folder(workspace) / "journal.jsonl").unlink(missing_ok=True)


def _named(session, opt: dict, verb: str) -> dict:
    name = str(opt.get("name") or "base")
    outcome = getattr(session, verb)(name)
    if not outcome.ok:
        _raise(outcome, f"{verb} {name} failed")
    return {verb: name}


def _dump(rt, session, workspace: Path, opt: dict) -> dict:
    """The whole guest's RAM as an ELF core, or (`program`) the located program's files."""
    name = str(opt.get("name") or time.strftime("guest-%Y%m%d-%H%M%S"))
    if not NAME.fullmatch(name):
        raise ViwoError("invalid_request", "a dump name is letters, digits, _ . -")
    if opt.get("program"):
        where = folder(workspace)
        return guest.program(rt, session, where, where / "dumps" / name, _say(rt, workspace, opt))
    out = folder(workspace) / "dumps" / f"{name}.elf"
    out.parent.mkdir(parents=True, exist_ok=True)
    outcome = session.dump(out)
    if not outcome.ok:
        _raise(outcome, "the dump failed")
    return {"dump": str(out), "size": out.stat().st_size if out.is_file() else 0}


def _patch(rt, session, workspace: Path, opt: dict) -> dict:
    return patching.patch(rt, session, folder(workspace), opt, _say(rt, workspace, opt))


def _cold(rt, session, workspace: Path, action: str, opt: dict) -> dict:
    """The set written into the guest's own files (`deploy`), or the originals put back."""
    guest_dir, creds = str(opt.get("guest_dir") or ""), dict(opt.get("creds") or {})
    if not guest_dir:
        raise ViwoError("invalid_request", f"{action} needs the program's folder in the guest")
    say, where = _say(rt, workspace, opt), folder(workspace)
    if action == "restore":
        return coldguest.restore(session, where, {"dir": guest_dir, "creds": creds}, say)
    if not opt.get("patchset"):
        raise ViwoError("invalid_request", "deploy needs a --patchset")
    patch_set = patchsets.load(Path(opt["patchset"]))
    guest = {"dir": guest_dir, "creds": creds}
    return coldguest.deploy(rt, session, where, patch_set, guest, say)


def _say(rt, workspace: Path, opt: dict):
    tier = session_tier(workspace) or "isolation"
    return _context(rt, workspace, tier, opt.get("say")).log


def act(rt, workspace: Path, action: str, say=None, **opt) -> dict:
    """One action on the workspace's running session."""
    if action not in ACTIONS:
        raise ViwoError("invalid_request", f"no action {action!r}", hint=" | ".join(ACTIONS))
    session, record = _rejoin(rt, workspace, say)
    head = {"tier": record["tier"], "action": action}
    try:
        if action == "stop":
            session.close()
            forget(workspace)
            left = session.wall()  # what the tier could not tidy up, said
            return {**head, "stopped": True, **({"warning": left.detail} if left.blocked else {})}
        return {**head, **_run(rt, session, workspace, action, {**opt, "say": say})}
    finally:
        session.release()


def _run(rt, session, workspace: Path, action: str, opt: dict) -> dict:
    if action in ("pause", "resume"):
        session.suspend() if action == "pause" else session.resume()
    if action in ("snapshot", "rollback"):
        return _named(session, opt, action)
    if action == "locate":
        want = str(opt.get("target") or "")
        return guest.locate(rt, session, folder(workspace), want, _say(rt, workspace, opt))
    if action == "dump":
        return _dump(rt, session, workspace, opt)
    if action == "patch":
        return _patch(rt, session, workspace, opt)
    if action in ("deploy", "restore"):
        return _cold(rt, session, workspace, action, opt)
    if action == "undo":
        return live.undo(session, folder(workspace) / "journal.jsonl")
    running = getattr(session, "running", None)
    public = {k: v for k, v in session.record().items() if k not in ("qmp", "gdb", "qga")}
    view = guest.load(folder(workspace))
    if view:
        here = guest.present(session, view)  # gone: exited (or refused the VM) or restarted
        public["located"] = {"pid": view["pid"], "program": guest.main(view), "present": here}
    return {"running": running() if running else None, **public}
