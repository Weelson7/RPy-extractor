"""L1/L3: per-game indexes: validator, shipped entries, detection, script install (no network)."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import runtime
from viwo.contracts import ViwoError
from viwo.core import indexes, thirdparty

ROOT = Path(__file__).resolve().parent.parent / "indexes"


def entry(**over) -> dict:
    base = {
        "schema": 1,
        "slug": "demo",
        "game_version": "any",
        "title": "Demo",
        "engine": "quickbms",
        "detect": ["data/*.dat"],
        "plugins": ["quickbms"],
        "options": {},
        "tools": [],
        "scripts": [],
    }
    return {**base, **over}


def write_entry(root: Path, data: dict) -> None:
    folder = root / "games" / data["slug"] / data["game_version"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.json").write_text(json.dumps(data), encoding="utf-8")


class ValidatorTests(unittest.TestCase):
    def test_shipped_entries_are_valid_and_listed(self) -> None:
        games = indexes.list_games(ROOT)
        for slug in ("freedoom", "renpy-generic", "godot-generic", "unreal-generic", "skyrim-se"):
            self.assertIn(slug, games)
            self.assertEqual(indexes.validate(indexes.load_index(ROOT, slug)), [])
        self.assertIn("overwatch", games)

    def test_rejections(self) -> None:
        self.assertIn("slug: lowercase", indexes.validate(entry(slug="../evil"))[0])
        self.assertTrue(
            any(
                "https" in p
                for p in indexes.validate(
                    entry(
                        scripts=[
                            {
                                "name": "dat.bms",
                                "url": "http://x/dat.bms",
                                "sha256": "0" * 64,
                                "size": 10,
                            }
                        ]
                    )
                )
            )
        )
        self.assertTrue(
            any(
                "secrets" in p
                for p in indexes.validate(entry(options={"unreal": {"aes_key": "0x00"}}))
            )
        )
        self.assertTrue(
            any("unknown dependency" in p for p in indexes.validate(entry(tools=["nope-tool"])))
        )
        self.assertTrue(any("relative" in p for p in indexes.validate(entry(detect=["../x"]))))
        self.assertTrue(
            any(
                "scripts: bad name" in p
                for p in indexes.validate(
                    entry(
                        scripts=[
                            {
                                "name": "sub/dat.bms",
                                "url": "https://x/d",
                                "sha256": "0" * 64,
                                "size": 1,
                            }
                        ]
                    )
                )
            )
        )

    def test_load_checks_folder_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_entry(root, entry(slug="demo"))
            self.assertEqual(indexes.load_index(root, "demo")["title"], "Demo")
            (root / "games" / "other" / "any").mkdir(parents=True)
            (root / "games" / "other" / "any" / "index.json").write_text(json.dumps(entry()))
            with self.assertRaises(ViwoError):
                indexes.load_index(root, "other")
            with self.assertRaises(ViwoError):
                indexes.load_index(root, "../demo")


class MatchAndInstallTests(unittest.TestCase):
    def test_install_game_scripts_and_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "dat.bms"
            script.write_text("get SIZE asize\n")
            digest = hashlib.sha256(script.read_bytes()).hexdigest()
            item = {
                "name": "dat.bms",
                "url": script.as_uri(),
                "sha256": digest,
                "size": script.stat().st_size,
            }
            write_entry(root, entry(scripts=[item]))
            (root / "home").mkdir()
            rt = runtime(root / "home")
            home = thirdparty.home_of(rt.config)
            with mock.patch.object(indexes, "validate", lambda e: []):  # file:// only in fixtures
                report = indexes.install_game(rt, root, "demo")
                self.assertEqual(report["scripts"], {"dat.bms": "installed"})
                installed = home / "third_party" / "quickbms" / "scripts" / "dat.bms"
                self.assertEqual(installed.read_bytes(), script.read_bytes())
                self.assertEqual(
                    indexes.install_game(rt, root, "demo")["scripts"], {"dat.bms": "present"}
                )
                installed.write_text("changed by hand\n")
                report = indexes.install_game(rt, root, "demo")
                self.assertIn("another checksum", report["failed"]["dat.bms"])
                self.assertEqual(installed.read_text(), "changed by hand\n")
            self.assertEqual(report["plugins"], ["quickbms"])


if __name__ == "__main__":
    unittest.main()
