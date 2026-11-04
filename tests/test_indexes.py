"""L1/L3: per-game indexes: validator, shipped entries, detection, script install (no network)."""

from __future__ import annotations

import hashlib
import json
import random
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.helpers import runtime, tree_hashes
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
                write_entry(root, entry(scripts=[{**item, "name": "b.bms", "sha256": "1" * 64}]))
                report = indexes.install_game(rt, root, "demo")  # the download is not the pin
                self.assertIn("checksum mismatch", report["failed"]["b.bms"])
                self.assertFalse((installed.parent / "b.bms").exists())
            self.assertEqual(report["plugins"], ["quickbms"])

    def test_tools_failing_to_install_are_named_and_the_rest_installed(self) -> None:
        from viwo.core import preflight

        rng = random.Random(4)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root)
            known = sorted(indexes._known_tools())
            present = {i["id"] for i in rt.dependency_report() if i["available"]}
            for _ in range(8):
                wanted = rng.sample(known, 4)
                broken = set(rng.sample(wanted, rng.randint(0, 4)))
                write_entry(root, entry(tools=wanted))

                def install(_rt, dep, _sink, _cancel, broken=broken):
                    if dep in broken:
                        raise ViwoError("failed", f"{dep} broke")
                    return {"installed": dep}

                said = []
                with mock.patch.object(preflight, "install", install):
                    report = indexes.install_game(rt, root, "demo", sink=said.append)
                missing = [d for d in wanted if d not in present]
                self.assertEqual(set(report["failed"]), broken - present)
                self.assertEqual(report["tools"], [d for d in missing if d not in broken])
                self.assertTrue(said)  # the summary is said, never silent


def _corrupt(entry_: dict, rng: random.Random) -> tuple[dict, set[str]]:
    """A valid entry with a random set of known faults, and the message each must produce."""
    faults = {
        "schema": ("schema", 2, "schema must be"),
        "version": ("game_version", "../1", "game_version:"),
        "title": ("title", "  ", "title is required"),
        "plugins": ("plugins", "quickbms", "plugins must be a list"),
        "detect": ("detect", [], "detect needs at least one"),
        "options": ("options", ["x"], "options must be an object"),
        "secret": ("options", {"unreal": {"Password": "x"}}, "secrets never live"),
        "script": ("scripts", ["dat.bms"], "every item must be an object"),
        "sha": ("scripts", [{**_SCRIPT, "sha256": "zz"}], "sha256 missing or malformed"),
        "size": ("scripts", [{**_SCRIPT, "size": 0}], "size must be a positive integer"),
    }
    chosen = rng.sample(sorted(faults), rng.randint(0, 3))
    keys = [faults[c][0] for c in chosen]
    chosen = [c for c in chosen if keys.count(faults[c][0]) == 1]  # one fault per field
    bad = dict(entry_)
    for c in chosen:
        bad[faults[c][0]] = faults[c][1]
    return bad, {faults[c][2] for c in chosen}


_SCRIPT = {"name": "d.bms", "url": "https://x/d.bms", "sha256": "0" * 64, "size": 3}


class ValidatorPropertyTests(unittest.TestCase):
    def test_every_fault_is_named_and_a_clean_entry_has_none(self) -> None:
        rng = random.Random(21)
        self.assertEqual(indexes.validate([]), ["entry must be an object"])
        loose = {k: v for k, v in entry().items() if k != "scripts"}
        self.assertEqual(indexes.validate({**loose, "options": {"godot": "plain"}}), [])
        for _ in range(200):
            bad, expected = _corrupt(entry(), rng)
            problems = indexes.validate(bad)
            for text in expected:
                self.assertTrue(any(text in p for p in problems), (text, problems))
            self.assertEqual(bool(problems), bool(expected), problems)

    def test_missing_or_broken_index_files_are_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ViwoError) as err:
                indexes.load_index(root, "demo", "1.0")
            self.assertEqual(err.exception.code, "not_found")
            write_entry(root, entry())
            (root / "games" / "demo" / "any" / "index.json").write_text("{not json")
            with self.assertRaises(ViwoError) as err:
                indexes.load_index(root, "demo")
            self.assertIn("not JSON", err.exception.message)


def _release(root: Path, tag: str, games: dict[str, bytes], nest: bool, good: bool) -> dict:
    """A release as the GitHub API lists it, its assets as file:// URLs."""
    zip_path = root / f"indexes-{tag}.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for name, data in games.items():
            z.writestr(("top/" if nest else "") + f"games/{name}", data)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest() if good else "0" * 64
    sums = root / f"sums-{tag}.txt"
    sums.write_text(f"{digest} *indexes-{tag}.zip\n")
    assets = [
        {"name": f"indexes-{tag}.zip", "browser_download_url": zip_path.as_uri()},
        {"name": "SHA256SUMS.txt", "browser_download_url": sums.as_uri()},
    ]
    return {"tag_name": tag, "assets": assets}


class UpdateTests(unittest.TestCase):
    def test_update_takes_the_newest_release_of_its_line_or_keeps_the_old(self) -> None:
        rng = random.Random(8)
        with tempfile.TemporaryDirectory() as tmp:
            root, home = Path(tmp), Path(tmp) / "home"
            for i in range(10):
                major = rng.choice([1, 2])
                tags = [f"v{rng.choice([1, 2, 3])}.{rng.randrange(9)}.{i}" for _ in range(3)]
                games = {f"g{i}/any/index.json": rng.randbytes(20)}
                good = rng.random() < 0.7
                releases = [_release(root, t, games, rng.random() < 0.5, good) for t in tags]
                before = tree_hashes(home / "indexes") if (home / "indexes").exists() else None
                if rng.random() < 0.3:
                    (home / ".indexes.old" / "stale").mkdir(parents=True, exist_ok=True)
                if rng.random() < 0.2:  # a release without its checksum list
                    releases[rng.randrange(3)]["assets"].pop()
                line = [r for r in releases if r["tag_name"].startswith(f"v{major}.")]
                newest = line[0] if line else None
                fails = None if newest and len(newest["assets"]) == 2 else "not_found"
                fails = fails or (None if good else "refused")
                said = []
                get = lambda _url, r=releases: r  # noqa: E731
                try:
                    done = indexes.update_indexes(home, major, said.append, fetch=get)
                except ViwoError as err:
                    self.assertEqual(err.code, fails, err.message)
                    after = tree_hashes(home / "indexes") if before is not None else None
                    self.assertEqual(after, before)  # a failed update keeps what was there
                    continue
                self.assertIsNone(fails)
                tag = line[0]["tag_name"]
                self.assertEqual(done["tag"], tag)
                target = home / "indexes"
                self.assertEqual((target / "VERSION").read_text().strip(), tag)
                name = next(iter(games))
                self.assertEqual((target / "games" / name).read_bytes(), games[name])
                self.assertFalse((home / ".indexes.old").exists())
                self.assertTrue(any(tag in str(e) for e in said))  # never silent
            (home / "indexes" / ".git").mkdir(parents=True, exist_ok=True)
            release = _release(root, "v1.0.0", {"x/any/index.json": b"{}"}, False, True)
            with self.assertRaises(ViwoError) as err:
                indexes.update_indexes(home, 1, fetch=lambda _url: [release])
            self.assertIn("git checkout", err.exception.message)


if __name__ == "__main__":
    unittest.main()
