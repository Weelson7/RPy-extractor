"""L3: temporary antivirus exclusions: added for the block, removed after it, a crash journal
undone at the next job, the user's own exclusions untouched, the switch, and the real host."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from viwo.core import scan_exclusions
from viwo.core.scan_exclusions import excluded, undo_leftovers
from viwo.os import select_os


class Host:
    def __init__(self, note: str = "") -> None:
        self.excluded: set[Path] = set()
        self.note = note

    def exclude_from_scan(self, paths):
        if self.note:
            return [], self.note
        new = [p for p in paths if p not in self.excluded]
        self.excluded |= set(new)
        return new, ""

    def include_in_scan(self, paths):
        self.excluded -= set(paths)


def runtime(root: Path, host, on: bool = True):
    (root / "tmp").mkdir(exist_ok=True)
    return SimpleNamespace(
        os=host, temp_root=root / "tmp", config=SimpleNamespace(av_exclusions=on)
    )


class ScanExclusionTests(unittest.TestCase):
    def test_added_for_the_block_then_removed_user_exclusions_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            host = Host()
            mine = root / "mine"
            host.excluded.add(mine)  # the user's own exclusion
            rt = runtime(root, host)
            with excluded(rt, (root / "ws", mine, root / "src")) as added:
                self.assertEqual(set(added), {root / "ws", root / "src"})
                self.assertEqual(len(list((root / "scan-exclusions").glob("*.json"))), 1)
            self.assertEqual(host.excluded, {mine})
            self.assertEqual(list((root / "scan-exclusions").glob("*.json")), [])

    def test_crash_journal_undone_next_time_and_switch_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            host = Host()
            host.excluded.add(root / "left")
            journals = root / "scan-exclusions"
            journals.mkdir()
            dead = {"pid": 2**22 + 12345, "paths": [str(root / "left")]}  # no such process
            (journals / "dead.json").write_text(json.dumps(dead), encoding="utf-8")
            undo_leftovers(runtime(root, host))
            self.assertEqual(host.excluded, set())
            self.assertFalse((journals / "dead.json").exists())
            with excluded(runtime(root, host, on=False), (root / "ws",)) as added:
                self.assertEqual((added, host.excluded), ([], set()))

    def test_refusal_is_said_once_and_the_real_host_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            rt, said = runtime(root, Host("needs administrator")), []
            scan_exclusions.NOTED.discard("needs administrator")
            for _ in range(2):
                with excluded(rt, (root / "ws",), said.append):
                    pass
            self.assertEqual(said, ["needs administrator"])
            added, note = select_os().exclude_from_scan([])  # never changes anything here
            self.assertEqual(added, [])
            self.assertIsInstance(note, str)


if __name__ == "__main__":
    unittest.main()
