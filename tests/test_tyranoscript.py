"""L3: TyranoScript games are loose HTML5/JS on disk. The plugin recognises the engine by its
`tyrano/` folder plus scenario scripts / config (not the shell alone, so RPG Maker MV and the
KiriKiri `.ks`/`.tjs` names do not trip it), claims the scenario and config extensions so they
are surfaced as text, names the scenario scripts as its completeness claim, and the round trip
replaces an edited loose file in the patched copy while the game folder is left as it was."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.core.roundtrip import repack
from viwo.plugins.tyranoscript import TyranoScriptPlugin


def a_game(root: Path) -> Path:
    game = root / "MyNovel"
    (game / "tyrano").mkdir(parents=True)
    (game / "tyrano" / "libs.js").write_text("// tyrano engine\n")
    (game / "data" / "scenario").mkdir(parents=True)
    (game / "data" / "scenario" / "first.ks").write_text("[cm]\n*start\nHello.[l]\n")
    (game / "data" / "scenario" / "second.ks").write_text("*next\nMore.[l]\n")
    (game / "data" / "system").mkdir(parents=True)
    (game / "data" / "system" / "Config.tjs").write_text(";projectID=myNovel\n")
    (game / "data" / "bgimage").mkdir(parents=True)
    (game / "data" / "bgimage" / "title.png").write_bytes(b"\x89PNG\r\n\x1a\n\0\0\0")
    (game / "index.html").write_text("<html><body>tyrano</body></html>")
    return game


class TyranoScriptTests(unittest.TestCase):
    def test_detection_prefers_the_engine_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = a_game(Path(tmp))
            self.assertEqual(TyranoScriptPlugin().detect(FolderProbe(game)).confidence, 0.9)
            # a KiriKiri-looking folder (.ks but no tyrano/ engine) is not claimed
            bare = Path(tmp) / "kirikiri"
            (bare / "scn").mkdir(parents=True)
            (bare / "scn" / "a.ks").write_text("x")
            self.assertEqual(TyranoScriptPlugin().detect(FolderProbe(bare)).confidence, 0.0)

    def test_inventory_names_the_scenario_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = a_game(Path(tmp))
            ctx = SimpleNamespace(probe=FolderProbe(game), game_root=game)
            inv = TyranoScriptPlugin().inventory(ctx)
            self.assertEqual(set(inv), {"data/scenario/first.ks", "data/scenario/second.ks"})

    def test_a_loose_edit_goes_back_and_the_game_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = a_game(root)
            before = tree_hashes(game)
            rt = runtime(root)
            request = ExtractionRequest(str(game), str(root / "ws"))
            result = extract(rt, request, "t", lambda e: None, CancelToken())
            self.assertEqual(result.runs[0].plugin_id, "tyranoscript", result.warnings)
            edited = next((root / "ws").rglob("first.ks"))
            edited.write_text("[cm]\n*start\nHello, edited.[l]\n")
            report = repack(rt, root / "ws", root / "copy")
            self.assertTrue(report["verified"], report)
            back = next((root / "copy").rglob("first.ks"))
            self.assertIn("edited", back.read_text())
            self.assertEqual(tree_hashes(game), before)


if __name__ == "__main__":
    unittest.main()
