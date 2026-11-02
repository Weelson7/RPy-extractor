"""Journaled overlay (doc 11.4): every file a runtime agent adds to or replaces in the game
folder is recorded with backups and hashes; restore undoes it and checks the result. A
journal left behind by a crash is restored before the next capture starts.

The journal is JSON lines (a header line, then one line per entry), written atomically
(temp file + replace), so a truncated file still restores every complete entry.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.workspace import safe_member

from ..pipeline.collect import sha256


class Journal:
    def __init__(self, folder: Path, game: Path, name: str = "journal") -> None:
        self.folder, self.game = folder / name, game
        self.file = self.folder / "journal.json"
        self.entries: list[dict] = []

    def _new_dirs(self, target: Path) -> list[str]:
        """Folders write() will create, game-relative, deepest first (removed on restore)."""
        created, parent = [], target.parent
        while parent != self.game and not parent.exists():
            created.append(parent.relative_to(self.game).as_posix())
            parent = parent.parent
        return created

    def write(self, rel: str, data: bytes) -> None:
        member = safe_member(rel)
        if member is None:
            raise ViwoError("refused", f"journal path leaves the game folder: {rel}")
        target = self.game.joinpath(*member.parts)
        backup = ""
        if target.exists():
            backup = f"backup/{len(self.entries)}"
            (self.folder / backup).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, self.folder / backup)
        self.entries.append(
            {
                "rel": member.as_posix(),
                "backup": backup,
                "original": sha256(target) if backup else "",
                "dirs": self._new_dirs(target),
            }
        )
        self._save()  # recorded before the write, so a crash mid-write is still undone
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def _save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps({"game": str(self.game)})]
        lines += [json.dumps(entry) for entry in self.entries]
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, self.file)  # atomic: the journal is complete or unchanged

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
    """(game, entries) from a journal file: JSON lines, or the older single-object form.
    Damaged lines are skipped with a warning; a journal without a readable header is skipped."""
    text = file.read_text(encoding="utf-8", errors="replace")
    try:
        whole = json.loads(text)
        if isinstance(whole, dict) and "entries" in whole:
            return str(whole["game"]), list(whole["entries"])
    except ValueError:
        pass
    game, entries, broken = "", [], 0
    for line in text.splitlines():
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
