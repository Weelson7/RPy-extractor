"""L5: plugins against real, redistributable game data (doc 17.2). Runs when the data is
present: `VIWO_FREEDOOM` points at an unpacked Freedoom release, or the owner's
`Test-games/` folder holds one (`sqc/games.md`); otherwise skipped with the reason."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract

REPO = Path(__file__).resolve().parent.parent
WADS = ("freedoom1.wad", "freedoom2.wad")


def freedoom_folder() -> Path | None:
    """The folder holding both Freedoom IWADs: env override, else Test-games/."""
    override = os.environ.get("VIWO_FREEDOOM", "")
    candidates = [Path(override)] if override else []
    games = REPO / "Test-games"
    if games.is_dir():
        candidates += [p.parent for p in games.rglob(WADS[0])]
    return next((c for c in candidates if all((c / w).is_file() for w in WADS)), None)


FREEDOOM = freedoom_folder()


@unittest.skipUnless(FREEDOOM, "Freedoom not found: set VIWO_FREEDOOM or unpack it in Test-games/")
class FreedoomTests(unittest.TestCase):
    def test_both_iwads_extract_to_viewable_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, game = Path(tmp), Path(tmp) / "game"
            game.mkdir()
            for name in WADS:
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
