"""L3: QuickBMS bridge: scripts folder from the ini, identification by suffix, fake tool."""

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract

FAKE = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
assert args[:2] == ["-o", "-Y"], args
script, archive, out = map(Path, args[2:5])
(out / "unpacked").mkdir(parents=True, exist_ok=True)
(out / "unpacked" / (archive.stem + ".ogg")).write_bytes(b"via " + script.name.encode())
"""


class QuickBmsTests(unittest.TestCase):
    def test_script_per_suffix_in_any_game(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "dat.mygame.bms").write_text("# script")
            tool = root / "fake_quickbms.py"
            tool.write_text(FAKE.format(python=sys.executable))
            tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
            if sys.platform == "win32":
                wrapper = root / "fake_quickbms.cmd"
                wrapper.write_text(f'@"{sys.executable}" "{tool}" %*\r\n')
                tool = wrapper
            game = root / "game"
            game.mkdir()
            (game / "sound.dat").write_bytes(b"custom archive")
            (game / "other.bin").write_bytes(b"x" * 2000)
            before = tree_hashes(game)
            rt = runtime(
                root, f"[tools]\nquickbms = {tool}\n[options.quickbms]\nscripts = {scripts}\n"
            )
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertEqual(
                (root / "ws" / "ogg" / "sound.ogg").read_bytes(), b"via dat.mygame.bms"
            )
            self.assertEqual(result.by_backend.get("quickbms-cli"), 1)
            self.assertEqual(tree_hashes(game), before)
            broken = runtime(root, "[options.quickbms]\nscripts = /nowhere\n")
            self.assertTrue(any("quickbms" in p for p in broken.problems), broken.problems)


if __name__ == "__main__":
    unittest.main()
