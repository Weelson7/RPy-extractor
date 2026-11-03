"""Temporary antivirus exclusions (owner, 2026-11-03): while a job runs, its workspace, source
and temp folders are excluded from the host's real-time scan (game files the scanner holds,
such as online-fix DLLs, otherwise break copies). The OS layer decides whether and how; ViWo
journals what it added and removes exactly that when the job ends, or at the next job when a
crash left a journal behind. `[startup] av_exclusions = off` switches it off."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

from viwo.os import pid_alive

NOTED: set[str] = set()  # each "could not" note is said once per process


def _journals(rt) -> Path:
    return rt.temp_root.parent / "scan-exclusions"


def undo_leftovers(rt) -> None:
    """Journals of processes that are gone: their exclusions are removed now."""
    for journal in sorted(_journals(rt).glob("*.json")):
        try:
            data = json.loads(journal.read_text(encoding="utf-8"))
            if pid_alive(int(data["pid"])):
                continue
            rt.os.include_in_scan([Path(p) for p in data["paths"]])
            journal.unlink()
        except (OSError, ValueError, KeyError, TypeError):
            continue


@contextmanager
def excluded(rt, paths, say=None):
    """Exclude `paths` for the duration of the block (a no-op when switched off)."""
    if not getattr(rt.config, "av_exclusions", True):
        yield []
        return
    undo_leftovers(rt)
    folders = sorted({Path(p).resolve() for p in paths if p})
    added, note = rt.os.exclude_from_scan(folders)
    if note and note not in NOTED and say is not None:
        NOTED.add(note)
        say(note)
    journal = _journals(rt) / f"{os.getpid()}-{id(folders)}.json"
    if added:
        journal.parent.mkdir(parents=True, exist_ok=True)
        payload = {"pid": os.getpid(), "paths": [str(p) for p in added]}
        journal.write_text(json.dumps(payload), encoding="utf-8")
    try:
        yield added
    finally:
        if added:
            rt.os.include_in_scan(added)
            journal.unlink(missing_ok=True)
