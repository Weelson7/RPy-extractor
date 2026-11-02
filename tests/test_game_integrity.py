"""L3: extraction never changes the game (paths, sizes and modification times)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import FakeUnarchiver, runtime
from tests.test_mixed import make_mixed_game
from tests.test_unity import fake_unitypy
from viwo.contracts import (
    CancelToken,
    ExtractionMode,
    ExtractionRequest,
    Outcome,
    OutcomeKind,
    ViwoError,
)
from viwo.core.pipeline.guard import snapshot
from viwo.core.pipeline.runner import extract


def run(rt, game: Path, workspace: Path):
    return extract(
        rt, ExtractionRequest(str(game), str(workspace)), "j", lambda e: None, CancelToken()
    )


class GameIntegrityTests(unittest.TestCase):
    def test_every_plugin_leaves_the_game_untouched(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(sys.modules, {"UnityPy": fake_unitypy()}),
        ):
            root = Path(tmp)
            game = make_mixed_game(root)
            before = snapshot(game)
            rt = runtime(root, "[plugins]\nrenpy = on\nunity = on\ngodot = on\n")
            for plugin in ("generic", "renpy", "unity", "godot"):
                request = ExtractionRequest(
                    str(game),
                    str(root / f"ws-{plugin}"),
                    mode=ExtractionMode.SINGLE,
                    plugins=(plugin,),
                )
                result = extract(rt, request, "j", lambda e: None, CancelToken())
                self.assertEqual(result.runs[0].plugin_id, plugin)
                self.assertFalse([w for w in result.warnings if "GAME FOLDER" in w])
            self.assertEqual(snapshot(game), before)

    def test_workspace_or_temp_inside_the_game_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = make_mixed_game(root)
            with self.assertRaises(ViwoError) as err:
                run(runtime(root), game, game / "extracted")
            self.assertEqual(err.exception.code, "refused")
            self.assertFalse((game / "extracted").exists())

    def test_a_backend_writing_into_the_game_is_reported(self) -> None:
        class Rogue(FakeUnarchiver):
            def extract(self, archive, dest, ctx) -> Outcome:
                (ctx.game_root / "rogue.txt").write_text("x")
                return Outcome(OutcomeKind.OK, 0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = make_mixed_game(root)
            rt = runtime(root)
            rt.backends["py-zipfile"] = Rogue("py-zipfile")
            result = run(rt, game, root / "ws")
            self.assertTrue(any("GAME FOLDER CHANGED" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
