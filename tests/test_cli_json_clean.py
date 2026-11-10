"""L3: `viwo --json` answers one JSON document on stdout, whatever prints under it. A native
library and a child process both write straight to the process's stdout while the command runs
(as UnityPy's layout generator did on a real Unity game: the games pass could not read the
answer); the answer still parses, and what they wrote is on stderr, not lost."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = """
import os, subprocess, sys
from viwo import cli
from viwo.contracts.errors import Envelope

def noisy(args, rt=None):
    os.write(1, b"NATIVE NOISE\\n")  # under Python's sys.stdout, as a C library does
    subprocess.run([sys.executable, "-c", "print('CHILD NOISE')"])  # inherits stdout
    print("PYTHON NOISE")
    return Envelope.success({"answer": 42}, [])

cli._run = noisy
sys.exit(cli.main(sys.argv[1:]))
"""


class JsonStaysCleanTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", SCRIPT, *args], cwd=ROOT, capture_output=True, text=True
        )

    def test_json_mode_keeps_stdout_for_the_answer_alone(self) -> None:
        done = self.run_cli("--json", "info")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["data"], {"answer": 42})  # nothing else there
        for noise in ("NATIVE NOISE", "CHILD NOISE", "PYTHON NOISE"):
            self.assertIn(noise, done.stderr)  # said, on the other stream

    def test_text_mode_is_left_alone(self) -> None:
        done = self.run_cli("info")
        self.assertIn("NATIVE NOISE", done.stdout)


if __name__ == "__main__":
    unittest.main()
