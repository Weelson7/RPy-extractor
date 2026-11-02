"""Workspace ownership, re-extraction policy and locking (doc 4.3, 12.3)."""

from __future__ import annotations

import json
import shutil
import threading
from contextlib import contextmanager
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.contracts.pipeline import OnExisting

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def claim(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ws.MARKER).write_text(json.dumps({"app": "viwo"}) + "\n", encoding="utf-8")
    return folder


def _has_content(folder: Path) -> bool:
    return any(p.name not in (ws.MARKER, *ws.LEGACY_MARKERS) for p in folder.iterdir())


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


def resolve_target(folder: Path, policy: OnExisting, default: Path | None = None) -> Path:
    """Apply the ownership rule and the re-extraction policy; never deletes user data."""
    if folder.exists() and not folder.is_dir():
        raise ViwoError("invalid_request", f"not a folder: {folder}")
    if not folder.exists() or not _has_content(folder):
        return claim(folder)
    is_default = default is not None and folder.resolve() == default.resolve()
    if not ws.has_marker(folder) and not is_default:
        raise ViwoError(
            "refused",
            f"{folder} has files and was not created by ViWo",
            hint="choose an empty folder or a ViWo workspace",
        )
    if policy is OnExisting.ASK:
        raise ViwoError(
            "needs_decision", f"{folder} already holds an extraction", hint="new | replace | cancel"
        )
    if policy is OnExisting.CANCEL:
        raise ViwoError("cancelled", "extraction cancelled by the re-extraction choice")
    return _new_sibling(folder) if policy is OnExisting.NEW else _replace_groups(folder)


@contextmanager
def workspace_lock(folder: Path, timeout: float = 0.0):
    key = str(folder.resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, threading.Lock())
    acquired = lock.acquire(timeout=timeout) if timeout > 0 else lock.acquire(blocking=False)
    if not acquired:
        raise ViwoError("busy", f"workspace {folder} is busy with another job")
    try:
        yield
    finally:
        lock.release()
