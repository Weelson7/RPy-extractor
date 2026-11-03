"""L6: tools/integration_games.py on a synthetic Test-games/ (in-process CLI, no subprocess)."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_game, make_png

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "integration_games", ROOT / "tools" / "integration_games.py"
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def synthetic_games(root: Path) -> Path:
    games = root / "Test-games"
    make_game(games / "zip-game")  # make_game writes <folder>/game/...; the slug is the parent
    loose = games / "loose-game"
    make_png(loose / "title.png")
    (loose / "readme.txt").write_text("hello")
    (games / "empty-game").mkdir()  # no files: ignored
    return games


class IntegrationGamesTests(unittest.TestCase):
    def test_run_over_synthetic_games(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            games = synthetic_games(root)
            folders = tool.game_folders(games)
            self.assertEqual([f.name for f in folders], ["loose-game", "zip-game"])
            flags = {
                "zip-game": [{"name": "a text file out of the zip", "glob": "**/*.txt", "min": 1}],
                "loose-game": [
                    {"name": "nope", "glob": "png/*.png", "min": 99},
                    {"name": "an analysis flag", "analyze": "nope", "glob": ".analysis/**/*"},
                ],
            }
            records = [
                tool.run_game(g, root / "out", tool.viwo_inprocess, flags=flags[g.name])
                for g in folders
            ]
            for r in records:
                self.assertEqual(
                    set(r)
                    >= {"game", "path", "steps", "warnings", "detection", "gameUnchanged", "ok"},
                    True,
                )
                self.assertEqual(
                    list(r["steps"])[:5],
                    ["detect", "survey", "extract", "repack_plan", "sanitize_plan"],
                )
                self.assertTrue(r["gameUnchanged"], r.get("changedFiles"))
                self.assertTrue((root / "out" / r["game"] / "survey.json").is_file())
            zip_game = next(r for r in records if r["game"] == "zip-game")
            self.assertGreaterEqual(zip_game["extract"]["archivesFound"], 1)
            self.assertIn("generic", zip_game["extract"]["plugins"])
            self.assertTrue(zip_game["ok"] and zip_game["flags"][0]["ok"], zip_game["flags"])
            loose = next(r for r in records if r["game"] == "loose-game")
            self.assertFalse(loose["ok"])  # the flags did not pass
            analysis = loose["steps"]["analyze:nope"]  # the analysis ran (and found no target)
            self.assertFalse(analysis["ok"])
            self.assertIn("nope", analysis["error"])
            self.assertTrue((root / "out" / "loose-game" / "analysis.ini").is_file())
            self.assertEqual(tool.exit_code(records), 1)
            report = tool.write_report(records, root / "out").read_text(encoding="utf-8")
            self.assertIn("| zip-game |", report)
            self.assertIn("FLAG FAILED: nope (found 1)", report)
            self.assertIn("1/2 games passed", report)
            shipped = tool.load_flags()
            self.assertGreaterEqual(len(shipped["DDLC-1.1.1-pc"]), 3)
            for slug, items in shipped.items():
                for flag in items:
                    self.assertTrue(flag["name"] and ("glob" in flag or "warning" in flag), slug)

    def test_integrity_and_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "g"
            game.mkdir()
            (game / "a.txt").write_text("a")
            before = tool.tree_hashes(game)
            record = {"steps": {}, "warnings": []}
            self.assertTrue(tool.integrity(record, game, before))
            (game / "a.txt").write_text("changed")
            self.assertFalse(tool.integrity(record, game, before))
            self.assertEqual(record["changedFiles"], ["a.txt"])
            self.assertEqual(tool.exit_code([]), 1)
            self.assertEqual(tool.exit_code([{"ok": True}, {"ok": False}]), 1)
            self.assertEqual(tool.exit_code([{"ok": True}]), 0)

    def test_failed_step_is_recorded_not_raised(self) -> None:
        record = {"steps": {}}
        data = tool.step(record, "detect", ["detect", "C:/nowhere/at/all"], tool.viwo_inprocess)
        self.assertIsNone(data)
        self.assertFalse(record["steps"]["detect"]["ok"])
        self.assertTrue(record["steps"]["detect"]["error"])


if __name__ == "__main__":
    unittest.main()
