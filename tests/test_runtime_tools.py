"""L3: D3 headless: a real memory dump of a running child process through the OS layer, pid
lookup by name, and the dynamic-arm switch."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import runtime
from viwo.contracts import ViwoError
from viwo.core.capture import runtime as rtools


class RuntimeToolTests(unittest.TestCase):
    def test_dump_a_running_process_and_the_switch(self) -> None:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "off").mkdir()
                with self.assertRaises(ViwoError):  # capture is off by default
                    rtools.dump(runtime(root / "off"), root / "ws", child.pid)
                rt = runtime(root, "[startup]\nfeatures = extraction, capture\n")
                done = rtools.dump(rt, root / "ws", child.pid)
                self.assertGreater(done["size"], 1 << 20)  # a real dump of a Python process
                self.assertTrue(Path(done["dump"]).is_file())
                self.assertIn(child.pid, rt.os.pids_of(Path(sys.executable).name))
                with self.assertRaises(ViwoError):
                    rtools.resolve_pid(rt, 0, "no-such-image.exe")
        finally:
            child.kill()
            child.wait()

    def test_every_kind_and_entry_point_share_one_dispatch(self) -> None:
        """The CLI, the /api/runtime/<kind> routes and POST /api/jobs reach the same core run:
        with the dynamic arm off, every kind is refused the same way everywhere."""
        from viwo.api.app import App
        from viwo.api.handlers import POST
        from viwo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root)
            app = App(rt)
            app.set_workspace(root / "ws")
            params = {"pid": 1, "gamePath": str(root), "exePath": str(root / "g.exe")}
            for kind in ("dump", "trace", "agent", "record"):
                for answer in (
                    POST[f"/api/runtime/{kind}"](app, params),
                    POST["/api/jobs"](app, {"kind": kind, "params": params}),
                ):
                    self.assertEqual((answer["success"], answer["code"]), (False, "refused"))
            args = ["--quiet", "--ini", str(root / "test.ini"), "dump", "--pid", "1"]
            with mock.patch("sys.stdout"):
                code = main([*args, "--workspace", str(root / "ws")])
            self.assertEqual(code, 3)  # refused


if __name__ == "__main__":
    unittest.main()
