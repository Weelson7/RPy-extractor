"""Provenance upkeep: when curation renames, trashes, restores or moves a workspace file,
its provenance entry follows, so the map never points at a missing file (round trip, doc 18).
"""

import json
import os
from pathlib import Path

from viwo.contracts import workspace as ws


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
        tmp = file.with_suffix(".tmp")
        tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
        os.replace(tmp, file)
    return changed


def moved(workspace: Path, src: Path, dest: Path) -> int:
    """One file moved or renamed inside the workspace."""
    return rewrite(workspace, {relative(workspace, src) or "": relative(workspace, dest)})
