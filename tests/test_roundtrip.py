"""L4: round trip (doc 18): extract -> edit -> repack into a patched copy -> verify."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.helpers import make_zip, runtime, tree_hashes
from tests.test_renpy import make_rpa
from viwo.contracts import CancelToken, ExtractionRequest, ViwoError
from viwo.core.pipeline.runner import extract
from viwo.core.roundtrip import MARKER, repack
from viwo.plugins.renpy.rpa import read_index


class RoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.rt = runtime(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def extract(self, game: Path) -> Path:
        ws = self.root / f"ws-{game.name}"
        extract(self.rt, ExtractionRequest(str(game), str(ws)), "j", lambda e: None, CancelToken())
        return ws

    def test_renpy_archive_member_and_loose_file(self) -> None:
        game = self.root / "vn"
        (game / "game").mkdir(parents=True)
        (game / "renpy").mkdir()
        make_rpa(
            game / "game" / "archive.rpa",
            {"images/bg.png": b"old-bg", "audio/a.ogg": b"keep"},
            prefix_len=2,
        )
        (game / "game" / "script.rpy").write_text("label start:\n")
        before = tree_hashes(game)
        ws = self.extract(game)
        (ws / "png" / "bg.png").write_bytes(b"NEW-BG")
        (ws / "rpy" / "script.rpy").write_text("label start:\n    'edited'\n")
        plan = repack(self.rt, ws, None, apply=False)
        self.assertEqual(
            [(p["container"], p["slot"]) for p in plan["plan"]],
            [("", "override"), ("game/archive.rpa", "pack.rpa")],
        )
        out = self.root / "patched"
        report = repack(self.rt, ws, out)
        self.assertTrue(report["verified"], report)
        with open(out / "game" / "archive.rpa", "rb") as fh:
            index = read_index(fh)
            fh.seek(index["audio/a.ogg"][0][0])
            self.assertEqual(fh.read(4), b"keep")  # untouched member intact
        self.assertIn("'edited'", (out / "game" / "script.rpy").read_text())
        self.assertEqual(tree_hashes(game), before)  # the original is never written
        self.assertTrue((out / MARKER / "report.json").is_file())
        self.assertTrue(repack(self.rt, ws, out)["verified"])  # a patched copy can be rebuilt

    def test_zip_container_and_target_rules(self) -> None:
        game = self.root / "love"
        game.mkdir()
        make_zip(game / "data.zip", {"sprites/hero.png": b"hero", "main.lua": b"print()"})
        ws = self.extract(game)
        (ws / "lua" / "main.lua").write_bytes(b"print('mod')")
        report = repack(self.rt, ws, self.root / "out")
        self.assertTrue(report["verified"], report)
        with zipfile.ZipFile(self.root / "out" / "data.zip") as z:
            self.assertEqual(
                (z.read("main.lua"), z.read("sprites/hero.png")), (b"print('mod')", b"hero")
            )
        busy = self.root / "busy"
        busy.mkdir()
        (busy / "mine.txt").write_text("user data")
        for target in (busy, game / "inside"):
            with self.assertRaises(ViwoError):
                repack(self.rt, ws, target)
        self.assertTrue((busy / "mine.txt").is_file())

    def test_http_plan_and_build(self) -> None:
        from viwo.api import app as app_module
        from viwo.api.handlers import POST

        game = self.root / "web"
        game.mkdir()
        make_zip(game / "data.zip", {"a.txt": b"a"})
        ws = self.extract(game)
        (ws / "txt" / "a.txt").write_bytes(b"b")
        app = app_module.App(self.rt)
        app.set_workspace(ws)
        plan = POST["/api/repack"](app, {"plan": True})
        self.assertEqual([p["slot"] for p in plan["plan"]], ["pack.zip"])
        self.assertEqual(POST["/api/repack"](app, {})["code"], "invalid_request")
        built = POST["/api/repack"](app, {"out": str(self.root / "web-patched")})
        self.assertTrue(built["verified"] and built["jobId"], built)

    def test_nothing_edited_writes_nothing(self) -> None:
        game = self.root / "plain"
        game.mkdir()
        (game / "a.txt").write_text("a")
        ws = self.extract(game)
        report = repack(self.rt, ws, self.root / "never")
        self.assertEqual((report["edits"], report["plan"]), (0, []))
        self.assertFalse((self.root / "never").exists())


if __name__ == "__main__":
    unittest.main()
