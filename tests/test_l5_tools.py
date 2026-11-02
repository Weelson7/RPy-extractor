"""L5: core backends against real third-party tools (skipped unless VIWO_L5=1)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract


@unittest.skipUnless(os.environ.get("VIWO_L5"), "L5 real-tool test (set VIWO_L5=1)")
class SevenZipTest(unittest.TestCase):
    def test_7z_through_its_slot(self) -> None:
        try:
            import py7zr
        except ImportError:
            self.skipTest("py7zr not installed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            (root / "src.txt").write_text("seven")
            with py7zr.SevenZipFile(game / "data.7z", "w") as archive:
                archive.write(root / "src.txt", "docs/readme.txt")
            rt = runtime(root)
            binding = rt.bindings["unarchive.7z"]
            self.assertTrue(binding.bound, binding.reasons)
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertIn("txt/readme.txt", tree_hashes(root / "ws", skip_reserved=True))
            self.assertEqual(result.archives_extracted, 1)


if __name__ == "__main__":
    unittest.main()
