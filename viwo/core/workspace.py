"""Workspace ownership, re-extraction policy and locking (doc 4.3, 12.3).

Locking is two-level: an in-process lock per folder, plus a lock file
`<workspace>/.extraction_metadata/lock` (created exclusively, holding pid and time) so two
ViWo processes cannot work on one workspace at once. A stale file (dead pid, or older than
STALE_AFTER) is taken over with a warning in the log.
"""

import json
import logging
import os
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from viwo import CONTRACT_VERSION, __version__
from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.contracts.pipeline import OnExisting
from viwo.os import pid_alive

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
LOCK_FILE = f"{ws.METADATA_DIR}/lock"
STALE_AFTER = 6 * 3600
log = logging.getLogger("viwo.workspace")


def write_atomic(path: Path, text: str) -> None:
    """Write text so a crash never leaves a half-written state file (temp + os.replace)."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def marker_data(folder: Path) -> dict:
    """The ownership marker's JSON (doc 4.3); older or empty markers read as {}."""
    try:
        data = json.loads((folder / ws.MARKER).read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def claim(folder: Path) -> Path:
    """Write the ownership marker: workspace id (kept across re-claims), who created it, and
    the contract version."""
    folder.mkdir(parents=True, exist_ok=True)
    old = marker_data(folder)
    data = {
        "app": "viwo",
        "id": old.get("id") or uuid.uuid4().hex,
        "created_by": old.get("created_by") or f"viwo {__version__}",
        "created": old.get("created") or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "contract": CONTRACT_VERSION,
    }
    (folder / ws.MARKER).write_text(json.dumps(data) + "\n", encoding="utf-8")
    return folder


def _has_content(folder: Path) -> bool:
    """Asset groups or run records; the other arms' dot-folders (.runtime, .analysis) are no
    extraction, and an extraction never touches them."""
    for entry in folder.iterdir():
        if entry.name == ws.MARKER or (
            ws.is_reserved(entry.name) and entry.name != ws.METADATA_DIR
        ):
            continue
        if entry.name == ws.METADATA_DIR and all(c.name == "lock" for c in entry.iterdir()):
            continue  # only our own lock file: not an extraction
        return True
    return False


def _new_sibling(folder: Path) -> Path:
    index = 2
    while (candidate := folder.with_name(f"{folder.name}-{index}")).exists():
        index += 1
    return claim(candidate)


def _replace_groups(folder: Path) -> Path:
    """Remove asset groups, keep reserved dot-folders (runs, trash, journals)."""
    for entry in folder.iterdir():
        if ws.is_reserved(entry.name):
            continue
        shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    return claim(folder)


def precheck(folder: Path, policy: OnExisting, default: Path | None = None) -> None:
    """Raise the errors resolve_target would raise, without creating or deleting anything."""
    if folder.exists() and not folder.is_dir():
        raise ViwoError("invalid_request", f"not a folder: {folder}")
    if not folder.exists() or not _has_content(folder):
        return
    is_default = default is not None and folder.resolve() == default.resolve()
    if not ws.has_marker(folder) and not is_default:
        raise ViwoError(
            "refused",
            f"{folder} has files and was not created by ViWo",
            hint="choose an empty folder or a ViWo workspace",
        )
    if not ws.has_marker(folder) and policy is OnExisting.REPLACE:  # the default, unclaimed
        raise ViwoError(
            "refused",
            f"{folder} holds files ViWo did not write: replace would delete them",
            hint="new: a fresh folder next to it; or empty the folder yourself",
        )
    if policy is OnExisting.ASK:
        raise ViwoError(
            "needs_decision",
            f"{folder} already holds an extraction",
            hint="new: a fresh folder next to it; replace: clear this workspace; or cancel",
        )
    if policy is OnExisting.CANCEL:
        raise ViwoError("cancelled", "extraction cancelled by the re-extraction choice")


def resolve_target(folder: Path, policy: OnExisting, default: Path | None = None) -> Path:
    """Apply the ownership rule and the re-extraction policy; never deletes user data."""
    precheck(folder, policy, default)
    if not folder.exists() or not _has_content(folder):
        return claim(folder)
    return _new_sibling(folder) if policy is OnExisting.NEW else _replace_groups(folder)


def _stale(path: Path) -> str:
    """Why an existing lock file may be taken over ("" when its owner is alive)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pid, when = int(data["pid"]), float(data["time"])
    except (OSError, ValueError, KeyError, TypeError):
        return "unreadable lock file"
    if time.time() - when > STALE_AFTER:
        return f"lock older than {STALE_AFTER // 3600} h (pid {pid})"
    if pid == os.getpid():
        return ""
    return "" if pid_alive(pid) else f"owner pid {pid} is not running"


def _lock_file(folder: Path) -> tuple[Path | None, bool]:
    """Create the lock file exclusively; (its path, whether the folder was created for it: a
    missing folder is, and is removed again on release when nothing else landed in it)."""
    if folder.exists() and not folder.is_dir():
        return None, False  # precheck reports it
    created = not folder.exists()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"pid": os.getpid(), "time": time.time()})
    for attempt in (1, 2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            reason = _stale(path) if attempt == 1 else ""
            if not reason:
                raise ViwoError("busy", f"workspace {folder} is locked by another ViWo process")
            log.warning("taking over the lock on %s: %s", folder, reason)
            path.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path, created
    return None, created


def _unlock_file(path: Path | None, created: bool) -> None:
    if path is None:
        return
    path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()  # only when nothing else lives in .extraction_metadata
        if created:  # a folder made for the lock, still empty: as it was before
            path.parent.parent.rmdir()
    except OSError:
        pass


@contextmanager
def workspace_lock(folder: Path, timeout: float = 0.0):
    key = str(folder.resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, threading.Lock())
    acquired = lock.acquire(timeout=timeout) if timeout > 0 else lock.acquire(blocking=False)
    if not acquired:
        raise ViwoError("busy", f"workspace {folder} is busy with another job")
    try:
        held, created = _lock_file(folder)
        try:
            yield
        finally:
            _unlock_file(held, created)
    finally:
        lock.release()
