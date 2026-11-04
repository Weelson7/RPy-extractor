"""Game-folder guard: extraction must never change the game (doc 0: the game folder is
read-only). ViWo writes only to staging, scratch and the workspace; this module refuses
layouts that would put those inside the game, and verifies the game afterwards."""

from __future__ import annotations

import os
from pathlib import Path

from viwo.contracts.errors import ViwoError

Snapshot = dict[str, tuple[int, int]]


def refuse_writes_inside(game: Path, **targets: Path) -> None:
    root = game.resolve()
    for label, target in targets.items():
        resolved = target.resolve()
        if resolved == root or root in resolved.parents:
            raise ViwoError(
                "refused",
                f"the {label} ({target}) is inside the game folder",
                hint="choose a location outside the game; ViWo never writes there",
            )


def snapshot(game: Path) -> Snapshot:
    """Cheap fingerprint of every file: relative path -> (size, mtime in ns)."""
    found: Snapshot = {}
    for dirpath, _, filenames in os.walk(game):
        for name in filenames:
            path = Path(dirpath) / name
            try:
                st = path.stat()
            except OSError:
                continue
            found[path.relative_to(game).as_posix()] = (st.st_size, st.st_mtime_ns)
    return found


def changes(before: Snapshot, after: Snapshot) -> list[str]:
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k))


def change_warning(before: Snapshot, after: Snapshot, during: str) -> str:
    """ "GAME FOLDER CHANGED during <x>: ..." naming what vanished (an antivirus quarantine
    removes files; ViWo never writes there), or "" when nothing changed."""
    touched = changes(before, after)
    if not touched:
        return ""
    gone = [t for t in touched if t in before and t not in after]
    text = f"GAME FOLDER CHANGED during {during}: {', '.join(touched[:10])}"
    if gone:
        text += f" ({len(gone)} removed by someone else, e.g. an antivirus: {', '.join(gone[:5])})"
    return text
