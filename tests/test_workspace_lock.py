"""L3: cross-process workspace lock file (pid + time), stale takeover, cleanup."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from viwo.contracts import ViwoError
from viwo.core import workspace


class LockFileTests(unittest.TestCase):
    def test_lock_file_exists_while_held_and_is_removed_after(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with workspace.workspace_lock(folder):
                data = json.loads((folder / workspace.LOCK_FILE).read_text())
                self.assertEqual(data["pid"], os.getpid())
            self.assertFalse((folder / workspace.LOCK_FILE).exists())
            self.assertFalse((folder / ".extraction_metadata").exists())  # left clean

    def test_live_lock_from_another_process_is_busy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / workspace.LOCK_FILE
            path.parent.mkdir(parents=True)
            # a lock held by a live process: our own pid stands in for "another live process"
            with mock.patch.object(workspace, "_stale", return_value=""):
                path.write_text(json.dumps({"pid": os.getpid(), "time": time.time()}))
                with self.assertRaises(ViwoError) as err, workspace.workspace_lock(folder):
                    pass
            self.assertEqual(err.exception.code, "busy")
            self.assertTrue(path.exists())  # never removed from under its owner

    def test_stale_locks_are_taken_over(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / workspace.LOCK_FILE
            path.parent.mkdir(parents=True)
            for body in (
                json.dumps({"pid": os.getpid(), "time": time.time() - 7 * 3600}),  # too old
                json.dumps({"pid": 2**22 + 12345, "time": time.time()}),  # dead pid
                "not json",
            ):
                path.parent.mkdir(exist_ok=True)  # the last release removed the empty folder
                path.write_text(body)
                with self.assertLogs("viwo.workspace", level="WARNING"):
                    with workspace.workspace_lock(folder):
                        self.assertEqual(json.loads(path.read_text())["pid"], os.getpid())
            self.assertTrue(workspace.pid_alive(os.getpid()))
            self.assertFalse(workspace.pid_alive(2**22 + 12345))

    def test_missing_folder_uses_the_in_process_lock_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "later"
            with workspace.workspace_lock(folder):
                self.assertFalse(folder.exists())


if __name__ == "__main__":
    unittest.main()
