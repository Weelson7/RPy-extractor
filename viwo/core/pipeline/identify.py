"""Identify containers for unarchive slots: custom identifiers, suffixes, magic (doc 8.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from viwo.contracts.slots import SNIFF_BYTES, Match, SlotDefinition

from .probe import _read


def identify(path: Path, slots: Iterable[SlotDefinition]) -> Match | None:
    candidates = [s for s in slots if s.family == "unarchive"]
    head = _read(path, SNIFF_BYTES, False)
    for slot in candidates:
        if slot.identify is not None:
            try:  # an identifier may reopen the file: a lock or an antivirus hold surfaces here
                found = slot.identify(path, head, _read(path, SNIFF_BYTES, True))
            except OSError:  # unidentified; the collect step names the file as unreadable
                continue
            if found is not None:
                return found
    name = path.name.lower()
    best, best_len = None, 0
    for slot in candidates:
        for suffix in slot.suffixes:
            if name.endswith(suffix) and len(suffix) > best_len:
                best, best_len = slot, len(suffix)
    if best is not None:
        return Match(best.slot_id, path)
    for slot in candidates:  # doc 2.5: no suffix claimed it, so the head bytes decide
        if any(head.startswith(magic) for magic in slot.magic):
            return Match(slot.slot_id, path)
    return None


def carve(match: Match, scratch: Path) -> Path:
    """Copy an embedded chunk (offset/size) into its own file for unpacking."""
    if not match.embedded:
        return match.path
    scratch.mkdir(parents=True, exist_ok=True)
    out = scratch / f"carved_{match.path.name}_{match.offset}.bin"
    with open(match.path, "rb") as src, open(out, "wb") as dst:
        src.seek(match.offset)
        remaining = match.size if match.size is not None else -1
        while remaining != 0:
            chunk = src.read(1 << 20 if remaining < 0 else min(1 << 20, remaining))
            if not chunk:
                break
            dst.write(chunk)
            remaining = -1 if remaining < 0 else remaining - len(chunk)
    return out
