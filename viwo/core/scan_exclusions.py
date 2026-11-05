"""Temporary antivirus exclusions (owner, 2026-11-03): while a job runs, its workspace, source
and temp folders are excluded from the host's real-time scan (game files the scanner holds,
such as online-fix DLLs, otherwise break copies). The OS layer decides whether and how; ViWo
journals what it added and removes exactly that when the last job using a folder ends, or at
the next job when a crash (or a refused removal) left a journal behind. Jobs running together
share an exclusion. `[startup] av_exclusions = off` switches it off."""

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

from viwo.os import pid_alive

ACTIVE: dict[Path, int] = {}  # folders this process excluded -> jobs still using them
LOCK = threading.Lock()


def _journals(rt) -> Path:
    return rt.temp_root.parent / "scan-exclusions"


def _journal(rt) -> Path:
    return _journals(rt) / f"{os.getpid()}.json"


def _save(rt, also: list[Path] = ()) -> None:
    """This process's journal: every folder it excluded and has not removed yet."""
    paths = sorted({*ACTIVE, *also})
    if paths:
        _journals(rt).mkdir(parents=True, exist_ok=True)
        payload = {"pid": os.getpid(), "paths": [str(p) for p in paths]}
        _journal(rt).write_text(json.dumps(payload), encoding="utf-8")
    else:
        _journal(rt).unlink(missing_ok=True)


def undo_leftovers(rt, say=None) -> None:
    """Journals of processes that are gone: their exclusions are removed now."""
    for journal in sorted(_journals(rt).glob("*.json")):
        try:
            data = json.loads(journal.read_text(encoding="utf-8"))
            if pid_alive(int(data["pid"])):
                continue
            if rt.os.include_in_scan([Path(p) for p in data["paths"]]):
                journal.unlink()
            elif say is not None:
                say(f"antivirus exclusions of an earlier run not removed yet: {data['paths']}")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if say is not None:
                say(f"antivirus exclusion journal {journal.name} unreadable: {exc}")


@contextmanager
def excluded(rt, paths, say=None):
    """Exclude `paths` for the duration of the block (a no-op when switched off)."""
    if not getattr(rt.config, "av_exclusions", True):
        yield []
        return
    undo_leftovers(rt, say)
    folders = sorted({Path(p).resolve() for p in paths if p})
    with LOCK:
        shared = [f for f in folders if f in ACTIVE]
        added, note = rt.os.exclude_from_scan([f for f in folders if f not in ACTIVE])
        for folder in [*shared, *added]:
            ACTIVE[folder] = ACTIVE.get(folder, 0) + 1
        _save(rt)
    if note and say is not None:  # said for every job: each run shows what happened to it
        say(note)
    mine = [*shared, *added]
    try:
        yield mine
    finally:
        _release(rt, mine, say)


def _release(rt, mine: list[Path], say) -> None:
    with LOCK:
        for folder in mine:
            ACTIVE[folder] -= 1
        last = [f for f in mine if ACTIVE[f] == 0]
        for folder in last:
            del ACTIVE[folder]
        removed = not last or rt.os.include_in_scan(last)
        _save(rt, [] if removed else last)  # a refused removal stays journaled for later
    if not removed and say is not None:
        say(f"antivirus exclusions could not be removed (retried at the next job): {last}")
