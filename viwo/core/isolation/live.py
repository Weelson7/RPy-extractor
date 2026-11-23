"""The cold+live bridge (doc 11.8): one located patch recipe applied either way. A patch set
locates an edit in a PE as a file offset (core.patchsets / core.patch_tools); cold it is written
into the patched copy (core.patchsets.write), live it is written at the virtual address the same
offset loads to (patch_tools.address_of), under the atomic suspend -> write -> verify -> resume
(core.isolation.atomic_write). So the same recipe, or its AOB signature, drives both arms.

A live set is all or nothing: when one edit hits a wall, the edits of the set already written are
put back. Every edit that stays is journalled with the bytes it replaced (`journal.jsonl` beside
the session), so `undo` restores the target byte for byte."""

import json
import time
from pathlib import Path

from viwo.contracts import workspace as ws

from .. import patchsets
from ..patch_tools import address_of, pe
from . import atomic_write

SETTLE = 0.5  # seconds the target runs before a journalled edit is read once more


def located_va(data: bytes, offset: int, base: int = 0) -> int:
    """The virtual address a file offset loads at. `base` rebases onto the module's live load
    address when ASLR moved it; 0 keeps the PE's own preferred image base."""
    va = address_of(data, offset)
    info = pe(data)
    if base and info:
        return base + (va - info["base"])
    return va


def write_located(session, data: bytes, offset: int, new: bytes, base: int = 0, log=None):
    """Apply one located edit to the live target atomically, at its virtual address. With a
    `log` list, the bytes it replaced are read first and recorded, and the edit is read once
    more after the target has run again (a self-check that reverts it is said)."""
    va = located_va(data, offset, base)
    if log is None:
        return atomic_write(session, va, new)
    old = session.read_mem(va, len(new))
    wall = atomic_write(session, va, new, SETTLE)
    if not wall.blocked:
        log.append({"addr": va, "old": old.hex(), "new": new.hex(), "time": time.time()})
    return wall


def _restore(session, entries: list[dict]) -> int:
    """Write the recorded old bytes back, newest first; how many went back."""
    done = 0
    for entry in reversed(entries):
        old = bytes.fromhex(entry["old"])
        if len(old) and not atomic_write(session, int(entry["addr"]), old).blocked:
            done += 1
    return done


def apply_live(rt, session, game: Path, patch_set: dict, base: int = 0, journal=None) -> dict:
    """Plan the set against the game's files, then write every ready patch into the live target
    (the same located offset the cold writer uses, turned into a virtual address). With a
    `journal` path the set is all or nothing and what stays is appended to the journal."""
    report = patchsets.plan(game, patch_set, rt.os)
    log: list[dict] | None = [] if journal is not None else None
    for patch, r in zip(patch_set["patches"], report["results"]):
        if r["status"] not in ("ready", "already"):
            r["written"], r["wall"] = False, ""
            continue
        path = ws.member_path(game, str(patch.get("file", "")))
        data = path.read_bytes() if path is not None and path.is_file() else b""
        wall = write_located(session, data, r["offset"], bytes.fromhex(r["new"]), base, log)
        r["wall"], r["detail"] = wall.wall.value, wall.detail
        r["written"] = not wall.blocked
    ready = [r for r in report["results"] if r["status"] == "ready"]
    report["written"] = bool(ready) and all(r.get("written") for r in ready)
    if log is not None:
        _settle(session, report, log, journal)
    return report


def _settle(session, report: dict, log: list[dict], journal: Path) -> None:
    """Keep the set (journal it) when every ready edit landed, else put the landed ones back."""
    if report["written"]:
        journal.parent.mkdir(parents=True, exist_ok=True)
        with open(journal, "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(entry) + "\n" for entry in log)
        report["journalled"] = len(log)
        return
    report["rolled_back"] = _restore(session, log)
    for r in report["results"]:
        if r.get("written"):
            r["written"], r["detail"] = False, "put back: another edit of the set hit a wall"


def undo(session, journal: Path) -> dict:
    """Put back every journalled edit, newest first, and empty the journal."""
    if not journal.is_file():
        return {"restored": 0, "edits": 0}
    lines = journal.read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines if line.strip()]
    restored = _restore(session, entries)
    if restored == len(entries):
        journal.unlink()
    return {"restored": restored, "edits": len(entries)}
