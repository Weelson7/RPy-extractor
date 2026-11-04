"""Game-folder journal restore (doc 11.5). Runtime agents work in a patched copy, so nothing
writes into a game folder any more; a journal left in `<temp>/capture/<name>/journal.json` (by
a crashed session that did) is still restored before the next capture starts: every recorded
file is put back from its backup (or removed when it was new) and its hash checked.

The journal is JSON lines: a header line `{"game": ...}`, then one line per entry
`{"rel", "backup", "original", "dirs"}`; a damaged line is skipped with a warning.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..pipeline.collect import sha256


class Journal:
    def __init__(self, folder: Path, game: Path, name: str = "journal") -> None:
        self.folder, self.game = folder / name, game
        self.entries: list[dict] = []

    def restore(self) -> list[str]:
        """Undo every change in reverse; returns the paths that do not match afterwards."""
        bad = []
        for entry in reversed(self.entries):
            target = self.game / entry["rel"]
            if entry["backup"]:
                shutil.copy2(self.folder / entry["backup"], target)
                if sha256(target) != entry["original"]:
                    bad.append(entry["rel"])
            elif target.exists():
                target.unlink()
            for created in entry.get("dirs", ()):  # folders the agent added, when empty
                folder = self.game / created
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
        if not bad:
            shutil.rmtree(self.folder, ignore_errors=True)
        return bad


def _parse(file: Path, warn) -> tuple[str, list[dict]] | None:
    """(game, entries) from a journal file. Damaged lines are skipped with a warning; a journal
    without a readable header is skipped."""
    game, entries, broken = "", [], 0
    for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            broken += 1
            continue
        if not isinstance(item, dict):
            broken += 1
        elif "game" in item and not game:
            game = str(item["game"])
        elif "rel" in item and "backup" in item:
            entries.append(item)
    if broken:
        warn(f"{file.parent.name}: {broken} damaged journal line(s) skipped")
    if not game:
        warn(f"{file.parent.name}: journal unreadable (no header); not restored, kept on disk")
        return None
    return game, entries


def pending(folder: Path, warn=None) -> list[Journal]:
    """Journals left by an interrupted session (to restore before anything else)."""
    out, warn = [], warn or (lambda message: None)
    for file in sorted(folder.glob("*/journal.json")) if folder.is_dir() else ():
        parsed = _parse(file, warn)
        if parsed is None:
            continue
        journal = Journal(folder, Path(parsed[0]), file.parent.name)
        journal.entries = parsed[1]
        out.append(journal)
    return out
