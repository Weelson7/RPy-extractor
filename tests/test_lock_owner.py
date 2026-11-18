"""L3: the workspace lock belongs to its live owner (doc 4.3).

Properties, over random lock files (owner, its age, its recorded start time, its host):

1. A lock is taken over exactly when its owner is gone: a dead pid, a pid that now belongs
   to a later process (the start time the lock records differs from the pid's), or an owner
   on another machine (which cannot be checked) whose lock was not refreshed for STALE_AFTER.
   A live owner on this machine keeps its lock whatever its age, with or without a recorded
   start time; a lock that is kept is never touched, a lock that is taken over is said.
2. While a lock is held its time (the file's modification time) is refreshed every REFRESH
   seconds; on release the refreshing stops before the file goes, and the file never comes
   back.
3. `pid_started` gives one stable number per live process, None for a pid that is gone.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from viwo.contracts import ViwoError
from viwo.core import workspace
from viwo.os import pid_started

HOUR = 3600


def _child() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def _dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


class OwnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.child = _child()
        self.addCleanup(self.child.wait)
        self.addCleanup(self.child.kill)
        self.dead = _dead_pid()

    def _write(self, path: Path, rng: random.Random) -> bool:
        """A random lock file; whether it may be taken over."""
        owner = rng.choice(["self", "child", "dead", "reused", "remote"])
        age = rng.uniform(0, 48 * HOUR)
        pid = {"self": os.getpid(), "dead": self.dead}.get(owner, self.child.pid)
        body = {"pid": pid, "time": time.time() - age}
        if owner != "remote" and (owner == "reused" or rng.random() < 0.6):
            started = pid_started(pid)
            body["started"] = started - 3600 if owner == "reused" else started
        if owner == "remote" or rng.random() < 0.5:
            body["host"] = "another-machine" if owner == "remote" else workspace.HOST
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
        os.utime(path, (time.time() - age, time.time() - age))  # its last refresh
        if owner == "remote":
            return age > workspace.STALE_AFTER
        return owner in ("dead", "reused")

    def test_taken_over_exactly_when_the_owner_is_gone(self) -> None:
        rng = random.Random(61)
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(40):
                folder = Path(tmp) / f"w{i}"
                path = folder / workspace.LOCK_FILE
                gone = self._write(path, rng)
                written = path.read_bytes()
                with self.subTest(lock=written):
                    self.assertEqual(bool(workspace._stale(path)), gone)
                    if not gone:  # kept: busy, the owner's file untouched
                        with self.assertRaises(ViwoError) as err:
                            with workspace.workspace_lock(folder):
                                pass
                        self.assertEqual(err.exception.code, "busy")
                        self.assertIn(str(path), err.exception.hint)
                        self.assertEqual(path.read_bytes(), written)
                        continue
                    with self.assertLogs("viwo.workspace", level="WARNING"):
                        with workspace.workspace_lock(folder):
                            mine = json.loads(path.read_text())
                    self.assertEqual(mine["pid"], os.getpid())
                    self.assertEqual(mine["started"], pid_started(os.getpid()))
                    self.assertEqual(mine["host"], workspace.HOST)

    def test_a_live_run_of_many_hours_keeps_its_lock(self) -> None:
        """The review's case: a WolvenKit run past six hours, a second run asks to replace."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / workspace.LOCK_FILE
            path.parent.mkdir(parents=True)
            started = pid_started(self.child.pid)
            then = time.time() - 9 * HOUR
            path.write_text(json.dumps({"pid": self.child.pid, "time": then, "started": started}))
            os.utime(path, (then, then))
            self.assertEqual(workspace._stale(path), "")
            with self.assertRaises(ViwoError):
                with workspace.workspace_lock(Path(tmp)):
                    pass


class RefreshTests(unittest.TestCase):
    def test_a_held_lock_is_refreshed_and_the_refresh_ends_with_it(self) -> None:
        rng = random.Random(67)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(workspace, "REFRESH", 0.05):
            for i in range(3):
                folder = Path(tmp) / f"w{i}"
                path = folder / workspace.LOCK_FILE
                with workspace.workspace_lock(folder):
                    old = time.time() - 5 * HOUR
                    os.utime(path, (old, old))  # as if the run had started hours ago
                    deadline = time.monotonic() + 5
                    while path.stat().st_mtime < time.time() - 60:
                        self.assertLess(time.monotonic(), deadline, "never refreshed")
                        time.sleep(0.02)
                    time.sleep(rng.uniform(0, 0.12))
                self.assertFalse(path.exists())
                time.sleep(0.15)  # three refresh periods: nothing brings the file back
                self.assertFalse(path.exists())
                beaters = [t for t in threading.enumerate() if t.name == "viwo-lock-refresh"]
                self.assertEqual(beaters, [])


class StartedTests(unittest.TestCase):
    def test_one_stable_number_per_live_process_none_once_gone(self) -> None:
        own = pid_started(os.getpid())
        self.assertIsNotNone(own)
        self.assertEqual(pid_started(os.getpid()), own)
        child = _child()
        try:
            theirs = pid_started(child.pid)
            self.assertIsNotNone(theirs)
            self.assertGreaterEqual(theirs, own)  # started after this test process
        finally:
            child.kill()
            child.wait()
        self.assertIsNone(pid_started(_dead_pid()))
        self.assertIsNone(pid_started(2**22 + 12345))


if __name__ == "__main__":
    unittest.main()
