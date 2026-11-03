"""L6: 10 CAPTURE API: warnings (never a block), confirmation, the capture job, file picker."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import make_png, write_ini
from tests.test_capture import FAKE_RDCMD, FAKE_RDPY, script
from viwo.api import app as app_module
from viwo.api.handlers_capture import CAPTURE_GET, CAPTURE_POST
from viwo.core.wiring.boot import boot


class CaptureApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.game = root / "MyGame"
        self.game.mkdir()
        (self.game / "Game.exe").write_bytes(b"MZ")
        (self.game / "EasyAntiCheat").mkdir()
        self.known = make_png(self.game / "title.png")
        self.fresh = make_png(root / "fresh.png", 8, 8, (1, 2, 3))
        rdcmd = script(root, "fake_rdcmd", FAKE_RDCMD.format(python=sys.executable))
        rdpy = script(
            root,
            "fake_rdpy",
            FAKE_RDPY.format(
                python=sys.executable,
                known=str(self.known),
                fresh=str(self.fresh),
                marker=str(root / "trigger.ran"),
            ),
        )
        ini = write_ini(
            root,
            "[startup]\nfeatures = extraction, capture\n"
            f"[tools]\nrenderdoccmd = {rdcmd}\nrdpython = {rdpy}\n"
            "[server]\nworkspace = ws\nlogs = logs\ntemp = tmp\n",
        )
        rt = boot(ini)
        rt.temp_root = rt.config.server.temp
        self.app = app_module.App(rt, ini)
        app_module.reset_app(self.app)

    def tearDown(self) -> None:
        app_module.reset_app()
        self._tmp.cleanup()

    def test_warnings_confirmation_and_capture(self) -> None:
        info = CAPTURE_POST["/api/capture/warnings"](self.app, {"gamePath": str(self.game)})
        self.assertTrue(info["success"], info)
        self.assertTrue(info["enabled"])
        self.assertEqual(info["backend"], "renderdoc")
        self.assertTrue(any("anti-cheat" in w for w in info["warnings"]))
        self.assertIn("responsible", info["confirmation"])
        missing = CAPTURE_POST["/api/capture/warnings"](self.app, {"gamePath": "/nope"})
        self.assertEqual(missing["code"], "not_found")
        ask = CAPTURE_POST["/api/capture"](
            self.app, {"gamePath": str(self.game), "exePath": str(self.game / "Game.exe")}
        )
        self.assertEqual(ask["code"], "needs_decision")
        self.assertIn("anti-cheat", ask["hint"])
        done = CAPTURE_POST["/api/capture"](
            self.app,
            {"gamePath": str(self.game), "exePath": str(self.game / "Game.exe"), "confirmed": True},
        )
        self.assertTrue(done["success"], done)
        self.assertEqual((done["gathered"], done["backend"]), (2, "renderdoc"))
        self.assertTrue(done["new"] and done["jobId"])
        self.assertEqual((self.game / "Game.exe").read_bytes(), b"MZ")
        outside = CAPTURE_POST["/api/capture"](
            self.app, {"gamePath": str(self.game), "exePath": str(self.fresh), "confirmed": True}
        )
        self.assertEqual(outside["code"], "refused")  # executable outside the game folder

    def test_browse_file(self) -> None:
        shell = type(self.app.rt.os.shell)
        with mock.patch.object(shell, "pick_file", return_value=None):
            res = CAPTURE_GET["/api/browse-file"](self.app, {"initialPath": str(self.game)})
            self.assertEqual((res["success"], res["code"]), (False, "cancelled"))
        with mock.patch.object(shell, "pick_file", return_value=self.game / "Game.exe"):
            res = CAPTURE_GET["/api/browse-file"](self.app, {})
            self.assertTrue(res["path"].endswith("Game.exe"))


if __name__ == "__main__":
    unittest.main()
