"""L1/L6: GUI settings: ini read as a form, written back key by key, applied by reload."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from viwo.api import app as app_module
from viwo.api.handlers_settings import SETTINGS_GET, SETTINGS_POST
from viwo.contracts import ViwoError
from viwo.core.wiring.boot import boot
from viwo.core.wiring.settings import read_settings, write_settings

INI = """; my startup file
[startup]
os = auto   ; keep
features = extraction, sorting, merger
auto_install = on

[plugins]
generic = on
renpy = on   ; visual novels
; unity stays default

[server]
workspace = data/ws
logs = data/logs
temp = data/tmp
"""


class SettingsFileTests(unittest.TestCase):
    def test_read_write_keeps_comments_and_unknown_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "startup.ini"
            ini.write_text(INI, encoding="utf-8")
            form = read_settings(ini, ["generic", "renpy", "unity"], ["sevenzip", "ffmpeg"])
            self.assertEqual(form["startup"]["features"], ["extraction", "sorting", "merger"])
            self.assertEqual(form["plugins"], {"generic": True, "renpy": True, "unity": True})
            self.assertEqual(form["tools"], {"sevenzip": "", "ffmpeg": ""})
            problems = write_settings(
                ini,
                {
                    "startup": {"features": ["extraction", "capture"], "auto_install": False},
                    "plugins": {"renpy": False, "unity": True},
                    "tools": {"sevenzip": "C:/7z/7z.exe"},
                    "options": {"quickbms": {"scripts": "scripts"}},
                },
            )
            self.assertEqual(problems, [])
            text = ini.read_text(encoding="utf-8")
            self.assertIn("; my startup file", text)
            self.assertIn("os = auto   ; keep", text)
            self.assertIn("features = extraction, capture", text)
            self.assertIn("auto_install = off", text)
            self.assertIn("renpy = off   ; visual novels", text)
            self.assertIn("; unity stays default", text)
            self.assertIn("unity = on", text)
            self.assertIn("[tools]\nsevenzip = C:/7z/7z.exe", text)
            self.assertIn("[options.quickbms]\nscripts = scripts", text)
            form = read_settings(ini, ["renpy", "unity"], ["sevenzip"])
            self.assertEqual(form["plugins"], {"renpy": False, "unity": True})
            self.assertTrue(form["tools"]["sevenzip"].endswith("7z.exe"))
            write_settings(ini, {"tools": {"sevenzip": ""}})  # empty = back to auto: line removed
            self.assertNotIn("sevenzip", ini.read_text(encoding="utf-8"))

    def test_refusals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "startup.ini"
            ini.write_text(INI, encoding="utf-8")
            for bad in (
                {"options": {"unreal": {"aes_key": "0x00"}}},
                {"tools": {"seven zip": "x"}},
                {"plugins": {"ren[py]": True}},
            ):
                with self.assertRaises(ViwoError) as err:
                    write_settings(ini, bad)
                self.assertEqual(err.exception.code, "invalid_request")
            self.assertEqual(ini.read_text(encoding="utf-8"), INI)  # untouched


class SettingsApiTests(unittest.TestCase):
    def test_get_post_and_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "startup.ini"
            ini.write_text(INI, encoding="utf-8")
            rt = boot(ini)
            rt.temp_root = rt.config.server.temp
            app = app_module.App(rt, ini)
            app_module.reset_app(app)
            try:
                got = SETTINGS_GET["/api/settings"](app, {})
                self.assertTrue(got["success"], got)
                self.assertTrue(got["plugins"]["renpy"])
                self.assertIn("renpy", got["pluginInfo"])
                self.assertIn("renpy", got["effective"]["plugins"])
                saved = SETTINGS_POST["/api/settings"](
                    app, {"plugins": {"renpy": False}, "startup": {"features": ["extraction"]}}
                )
                self.assertTrue(saved["success"], saved)
                self.assertNotIn("renpy", saved["effective"]["plugins"])
                self.assertEqual(saved["effective"]["features"], ["extraction"])
                self.assertNotIn("renpy", app.rt.plugins)  # reloaded, no restart
                refused = SETTINGS_POST["/api/settings"](
                    app, {"options": {"godot": {"key": "secret"}}}
                )
                self.assertEqual(refused["code"], "invalid_request")
            finally:
                app_module.reset_app()


if __name__ == "__main__":
    unittest.main()
