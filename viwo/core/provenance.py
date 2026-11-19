"""Provenance upkeep: when curation renames, trashes, restores or moves a workspace file,
its provenance entry follows, so the map never points at a missing file (round trip, doc 18).
"""

import json
from pathlib import Path

from viwo.contracts import workspace as ws

from .workspace import write_atomic


def relative(workspace: Path, path: Path) -> str | None:
    """Workspace-relative posix path, or None when the file left the workspace."""
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return None


def entries(workspace: Path) -> list[dict]:
    """Every provenance entry; a damaged line (a crash mid-write) is skipped, not fatal."""
    file = workspace / ws.PROVENANCE_FILE
    out = []
    for line in file.read_text(encoding="utf-8").splitlines() if file.is_file() else []:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def rewrite(workspace: Path, moves: dict[str, str | None]) -> int:
    """Point entries at their files' new paths (old rel -> new rel); returns entries changed."""
    moves = {old: new for old, new in moves.items() if new and old != new}
    file = workspace / ws.PROVENANCE_FILE
    if not moves or not file.is_file():
        return 0
    out, changed = [], 0
    for line in file.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            out.append(line)
            continue
        new = moves.get(entry.get("path")) if isinstance(entry, dict) else None
        if new is not None:
            entry["path"], changed = new, changed + 1
            line = json.dumps(entry, sort_keys=True)
        out.append(line)
    if changed:
        write_atomic(file, "\n".join(out) + "\n")
    return changed


def add(workspace: Path, new: list[dict]) -> None:
    """Entries for files ViWo made in the workspace after the extraction (sanitizer copies)."""
    if new:
        file = workspace / ws.PROVENANCE_FILE
        file.parent.mkdir(parents=True, exist_ok=True)
        with open(file, "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(entry, sort_keys=True) + "\n" for entry in new)


def forget(workspace: Path, gone: set[str]) -> int:
    """Drop the entries of files that are no longer there (an undone copy); returns how many."""
    file = workspace / ws.PROVENANCE_FILE
    if not gone or not file.is_file():
        return 0
    lines = file.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if _path_of(line) not in gone]
    if len(kept) != len(lines):
        write_atomic(file, "".join(line + "\n" for line in kept))
    return len(lines) - len(kept)


def _path_of(line: str) -> str | None:
    try:
        entry = json.loads(line)
    except ValueError:
        return None  # a damaged line stays as it is
    return entry.get("path") if isinstance(entry, dict) else None


def moved(workspace: Path, src: Path, dest: Path) -> int:
    """One file moved or renamed inside the workspace."""
    return rewrite(workspace, {relative(workspace, src) or "": relative(workspace, dest)})
