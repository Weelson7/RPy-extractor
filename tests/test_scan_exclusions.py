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

    refuse = False

    def include_in_scan(self, paths):
        if self.refuse:
            return False
        self.excluded -= set(paths)
        return True


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

    def test_jobs_share_an_exclusion_and_only_the_last_removes_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            host = Host()
            rt = runtime(root, host)
            with excluded(rt, (root / "ws", root / "a")):
                with excluded(rt, (root / "ws", root / "b")) as inner:
                    self.assertEqual(set(inner), {root / "ws", root / "b"})
                self.assertEqual(host.excluded, {root / "ws", root / "a"})  # still in use
            self.assertEqual((host.excluded, scan_exclusions.ACTIVE), (set(), {}))

    def test_a_refused_removal_is_said_journaled_and_finished_later(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            host, said = Host(), []
            rt = runtime(root, host)
            host.refuse = True
            with excluded(rt, (root / "ws",), said.append):
                pass
            self.assertTrue(any("could not be removed" in s for s in said), said)
            journal = json.loads(next((root / "scan-exclusions").glob("*.json")).read_text())
            self.assertEqual(journal["paths"], [str(root / "ws")])
            host.refuse = False
            with excluded(rt, (root / "other",)):
                pass
            journal["pid"] = 2**22 + 777  # as if this process had died: the next job finishes it
            (root / "scan-exclusions" / "gone.json").write_text(json.dumps(journal))
            undo_leftovers(rt)
            self.assertEqual(host.excluded, set())

    def test_refusal_is_said_every_job_and_the_real_host_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            rt, said = runtime(root, Host("needs administrator")), []
            for _ in range(2):
                with excluded(rt, (root / "ws",), said.append):
                    pass
            self.assertEqual(said, ["needs administrator"] * 2)
            added, note = select_os().exclude_from_scan([])  # never changes anything here
            self.assertEqual(added, [])
            self.assertIsInstance(note, str)


if __name__ == "__main__":
    unittest.main()
