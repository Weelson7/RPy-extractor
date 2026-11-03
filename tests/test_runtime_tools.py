"""L3: D3 headless: a real memory dump of a running child process through the OS layer, pid
lookup by name, and the dynamic-arm switch."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
