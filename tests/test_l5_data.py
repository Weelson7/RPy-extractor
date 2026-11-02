"""L5: plugins against real, redistributable game data (skipped unless the data is present)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract

FREEDOOM = os.environ.get("VIWO_FREEDOOM", "")


@unittest.skipUnless(FREEDOOM, "set VIWO_FREEDOOM to the unpacked Freedoom release folder")
class FreedoomTests(unittest.TestCase):
    def test_both_iwads_extract_to_viewable_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, game = Path(tmp), Path(tmp) / "game"
            game.mkdir()
            for name in ("freedoom1.wad", "freedoom2.wad"):
                shutil.copy2(Path(FREEDOOM) / name, game / name)
            before = tree_hashes(game)
            request = ExtractionRequest(str(game), str(root / "ws"))
            result = extract(runtime(root), request, "j", lambda e: None, CancelToken())
            self.assertEqual(result.runs[0].plugin_id, "doom")
            self.assertEqual(result.archives_extracted, 2, result.warnings)
            counts = result.copied_by_ext
            self.assertGreater(counts.get("png", 0), 2500)  # sprites, patches, flats, graphics
            self.assertGreater(counts.get("wav", 0), 80)
            self.assertGreater(counts.get("mid", 0) + counts.get("mus", 0), 30)
            self.assertEqual(tree_hashes(game), before)


if __name__ == "__main__":
    unittest.main()
