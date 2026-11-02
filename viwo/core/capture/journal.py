"""Journaled overlay (doc 11.4): every file a runtime agent adds to or replaces in the game
folder is recorded with backups and hashes; restore undoes it and checks the result. A
journal left behind by a crash is restored before the next capture starts."""

from __future__ import annotations

import json
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
            }
        )
        self._save()  # recorded before the write, so a crash mid-write is still undone
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def _save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.file.write_text(
            json.dumps({"game": str(self.game), "entries": self.entries}), encoding="utf-8"
        )

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
        if not bad:
            shutil.rmtree(self.folder, ignore_errors=True)
        return bad


def pending(folder: Path) -> list[Journal]:
    """Journals left by an interrupted session (to restore before anything else)."""
    out = []
    for file in sorted(folder.glob("*/journal.json")) if folder.is_dir() else ():
        data = json.loads(file.read_text(encoding="utf-8"))
        journal = Journal(folder, Path(data["game"]), file.parent.name)
        journal.entries = data["entries"]
        out.append(journal)
    return out
