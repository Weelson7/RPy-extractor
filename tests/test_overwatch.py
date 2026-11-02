"""L3: Overwatch plugin (tos-sensitive): never auto-picked, explicit run via a fake DataTool,
reminder in every result, repack and capture refused. Real-game tests: independent operator."""

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionMode, ExtractionRequest, ViwoError
from viwo.core.capture import CaptureRequest, capture
from viwo.core.pipeline.runner import extract

FAKE = """#!{python}
import sys
from pathlib import Path
game, mode, out = sys.argv[1:4]
Path(out).mkdir(parents=True, exist_ok=True)
(Path(out) / (mode + ".png")).write_bytes(b"png from " + mode.encode())
"""


class OverwatchTests(unittest.TestCase):
    def test_explicit_only_with_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "Overwatch"
            (game / "data" / "casc").mkdir(parents=True)
            (game / "Overwatch.exe").write_bytes(b"MZ")
            (game / ".build.info").write_text("x")
            tool = root / "fake_datatool.py"
            tool.write_text(FAKE.format(python=sys.executable))
            tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
            if sys.platform == "win32":
                (root / "fake_datatool.cmd").write_text(f'@"{sys.executable}" "{tool}" %*\r\n')
                tool = root / "fake_datatool.cmd"
            ini = "[startup]\nfeatures = extraction, capture\n"
            rt = runtime(
                root,
                ini + f"[tools]\ndatatool = {tool}\n[options.overwatch]\nmodes = extract-maps\n",
            )
            before = tree_hashes(game)
            auto = extract(
                rt,
                ExtractionRequest(str(game), str(root / "a")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertNotIn("overwatch", [r.plugin_id for r in auto.runs])
            single = ExtractionRequest(
                str(game), str(root / "b"), mode=ExtractionMode.SINGLE, plugins=("overwatch",)
            )
            result = extract(rt, single, "j", lambda e: None, CancelToken())
            self.assertEqual(
                (root / "b" / "png" / "extract-maps.png").read_bytes(), b"png from extract-maps"
            )
            self.assertTrue(any("respect Blizzard" in w for w in result.warnings))
            self.assertEqual(tree_hashes(game), before)
            with self.assertRaises(ViwoError) as err:
                capture(
                    rt, CaptureRequest(game, game / "Overwatch.exe", root / "c", confirmed=True)
                )
            self.assertEqual(err.exception.code, "refused")


if __name__ == "__main__":
    unittest.main()
