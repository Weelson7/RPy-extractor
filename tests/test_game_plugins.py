"""L3: game plugins (doc 2.10). Every built-in game plugin is found under its engine and names
that engine; a game plugin never runs alone (chosen, it brings its engine first) and a chosen
engine brings the game plugins that detect their game; an engine detects by its own file
signature, so a game of that engine without the title's executable still extracts; the
engine's archive reader takes the path lists of the run's game plugins."""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime, tree_hashes
from tests.test_redengine import cr2w, rdar
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts.pipeline import ExtractionMode
from viwo.contracts.types import DetectionResult
from viwo.core.pipeline.runner import extract
from viwo.core.pipeline.select import with_games
from viwo.core.wiring.registry import BUILTIN_PLUGINS, DISCOVERY_PROBLEMS, load_plugin


def _game(root: Path, title_exe: bool) -> Path:
    game = root / ("cp" if title_exe else "other")
    (game / "archive" / "pc" / "content").mkdir(parents=True)
    if title_exe:
        (game / "bin" / "x64").mkdir(parents=True)
        (game / "bin" / "x64" / "Cyberpunk2077.exe").write_bytes(b"MZ")
    archive = rdar({0x1234: [cr2w("CMesh"), b"buffer"]})
    (game / "archive" / "pc" / "content" / "basegame_1.archive").write_bytes(archive)
    return game


class DiscoveryTests(unittest.TestCase):
    def test_every_game_plugin_sits_under_the_engine_it_names(self) -> None:
        self.assertEqual(DISCOVERY_PROBLEMS, [])
        games = {}
        for pid, entry in BUILTIN_PLUGINS.items():
            engine = load_plugin(entry).manifest.engine
            if engine:
                games[pid] = engine
                self.assertIn(f"viwo.plugins.{engine}.games.{pid}:", entry)
                self.assertIn(engine, BUILTIN_PLUGINS)
                self.assertFalse(load_plugin(BUILTIN_PLUGINS[engine]).manifest.engine)
        self.assertEqual(games, {"cyberpunk2077": "redengine", "bannerlord": "taleworlds"})

    def test_a_game_plugin_whose_engine_is_off_is_not_loaded_and_said(self) -> None:
        from viwo.core.wiring.registry import load_enabled

        for engine, game in (("redengine", "cyberpunk2077"), ("taleworlds", "bannerlord")):
            plugins, problems = load_enabled({engine: False, game: True})
            self.assertNotIn(game, plugins)
            self.assertIn(f"plugin {game} disabled: its engine plugin {engine} is off", problems)
            plugins, problems = load_enabled({engine: True, game: True})
            self.assertIn(game, plugins)


class SelectionTests(unittest.TestCase):
    def test_a_game_plugin_never_runs_without_its_engine(self) -> None:
        rng = random.Random(4)
        plugins = {pid: load_plugin(entry) for pid, entry in BUILTIN_PLUGINS.items()}
        for _ in range(300):
            chosen = rng.sample(sorted(plugins), rng.randint(1, 4))
            found = {
                pid: DetectionResult("x", rng.choice([0.0, 0.3, 0.6, 0.9]), (), pid)
                for pid in plugins
            }
            order = with_games(plugins, chosen, found)
            self.assertEqual(len(order), len(set(order)))
            self.assertLessEqual(set(chosen), set(order))
            for at, pid in enumerate(order):
                engine = plugins[pid].manifest.engine
                if engine:  # its engine runs, and runs first
                    self.assertLess(order.index(engine), at)
                    self.assertTrue(pid in chosen or found[pid].confidence >= 0.5)


class RunTests(unittest.TestCase):
    def test_the_engine_detects_by_signature_and_the_title_adds_its_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root)
            for title, want in ((True, ["redengine", "cyberpunk2077"]), (False, ["redengine"])):
                game = _game(root, title)
                before = tree_hashes(game)
                result = extract(
                    rt, ExtractionRequest(str(game), str(root / f"ws{title}")), "j",
                    lambda e: None, CancelToken(),
                )  # fmt: skip
                self.assertEqual([r.plugin_id for r in result.runs], want)
                self.assertTrue((root / f"ws{title}" / "mesh").is_dir())  # the engine extracts
                said = " ".join(result.warnings)
                if not title:  # never silent: why the members keep their hashes
                    self.assertIn("no game plugin supplies", " ".join(result.logs) + said)
                self.assertEqual(tree_hashes(game), before)
            single = ExtractionRequest(
                str(_game(root / "s", True)), str(root / "wss"),
                mode=ExtractionMode.SINGLE, plugins=("cyberpunk2077",),
            )  # fmt: skip
            runs = extract(rt, single, "j", lambda e: None, CancelToken()).runs
            self.assertEqual([r.plugin_id for r in runs], ["redengine", "cyberpunk2077"])

    def test_the_reader_takes_the_path_lists_of_the_runs_games(self) -> None:
        from viwo.plugins.redengine import _names

        seen = []
        spec = SimpleNamespace(dep_id="list", hint="install the list")
        game = SimpleNamespace(name_lists=(spec,))
        ctx = SimpleNamespace(
            games=(game,), os=SimpleNamespace(tools=SimpleNamespace(locate=seen.append))
        )
        names, notes = _names(ctx, None)
        self.assertEqual((names, seen), (None, [spec]))
        self.assertIn("install the list", notes[0])


if __name__ == "__main__":
    unittest.main()
