"""L3: T2 mod packages: pack a patched copy's changes, check against the original install and
another version, apply into a new copy; the game is only read; unsafe paths are refused."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import ViwoError
from viwo.core import mods, patchsets
from viwo.core.roundtrip import MARKER


def game_and_copy(root: Path) -> tuple[Path, Path]:
    game = root / "game"
    (game / "data").mkdir(parents=True)
    (game / "Game.exe").write_bytes(b"MZ" + bytes(30))
    (game / "data" / "text.txt").write_text("hello")
    (game / "data" / "big.bin").write_bytes(bytes(5000))
    patch = {
        "schema": 1,
        "patches": [{"file": "Game.exe", "offset": "2", "original": "00", "patched": "90"}],
    }
    set_path = root / "p.patch.json"
    set_path.write_text(json.dumps(patch))
    copy = root / "copy"
    patchsets.apply(runtime(root), game, set_path, copy)
    (copy / "data" / "new.txt").write_text("added by the mod")
    return game, copy


class ModTests(unittest.TestCase):
    def test_pack_check_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, copy = game_and_copy(root)
            before = tree_hashes(game)
            done = mods.pack(game, copy, root / "out" / "my.zip", "my mod")
            self.assertEqual(done["files"], 2)  # Game.exe changed, new.txt added
            names = zipfile.ZipFile(root / "out" / "my.zip").namelist()
            self.assertEqual(
                sorted(names),
                [
                    "files/Game.exe",
                    "files/data/new.txt",
                    "patches/p.aob.patch.json",
                    "viwo-mod.json",
                ],
            )
            fit = mods.check(game, root / "out" / "my.zip")
            self.assertEqual({r["state"] for r in fit["files"]}, {"fits", "new"})
            self.assertTrue(fit["fits"])
            self.assertTrue(
                all(
                    r["state"] == "installed"
                    for r in mods.check(copy, root / "out" / "my.zip")["files"]
                )
            )
            target = root / "second"
            applied = mods.apply(runtime(root), game, [root / "out" / "my.zip"], target)
            self.assertEqual(applied["applied"], 2)
            self.assertEqual((target / "Game.exe").read_bytes()[2], 0x90)
            self.assertTrue((target / MARKER).is_dir())
            self.assertEqual(tree_hashes(game), before)
            (game / "Game.exe").write_bytes(b"MZ" + bytes([1]) * 30)  # another game version
            self.assertFalse(mods.check(game, root / "out" / "my.zip")["fits"])
            # no unique AOB fits a file of identical bytes, so the mod cannot adapt here
            with self.assertRaises(ViwoError):
                mods.apply(runtime(root), game, [root / "out" / "my.zip"], root / "third")

    def test_update_check_order_and_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            code = bytearray(b"MZ" + bytes(range(2, 120)))
            (game / "Game.exe").write_bytes(bytes(code))
            patch = {
                "schema": 1,
                "patches": [
                    {"file": "Game.exe", "offset": "0x40", "original": "40", "patched": "90"}
                ],
            }
            (root / "p.patch.json").write_text(json.dumps(patch))
            patchsets.apply(runtime(root), game, root / "p.patch.json", root / "copy")
            mods.pack(game, root / "copy", root / "a.zip", "a")
            newer = bytes(b"\xcc" * 16) + bytes(code)  # the next version: the code moved by 16
            (game / "Game.exe").write_bytes(newer)
            state = mods.check(game, root / "a.zip")["files"][0]["state"]
            self.assertEqual(state, "adapts")  # the AOB patch resolves in the new version
            mods.apply(runtime(root), game, [root / "a.zip"], root / "adapted")
            self.assertEqual((root / "adapted" / "Game.exe").read_bytes()[0x50], 0x90)
            (root / "copy" / "extra.txt").write_text("b")
            mods.pack(game, root / "copy", root / "b.zip", "b", {"requires": ["a"]})
            self.assertEqual(
                [p.name for p in mods.order([root / "b.zip", root / "a.zip"])], ["a.zip", "b.zip"]
            )
            with self.assertRaises(ViwoError):
                mods.order([root / "b.zip"])  # its requirement is missing
            (root / "twin").mkdir()
            mods.pack(game, root / "copy", root / "twin" / "a.zip", "a")
            with self.assertRaises(
                ViwoError
            ) as err:  # same name: one would silently replace the other
                mods.order([root / "a.zip", root / "twin" / "a.zip"])
            self.assertIn("share the name a", err.exception.message)
            (root / "copy" / "extra.txt").write_text("c")
            mods.pack(game, root / "copy", root / "c.zip", "c")
            clash = mods.conflicts([root / "b.zip", root / "c.zip"])
            self.assertEqual(clash, ["extra.txt: b and c"])  # Game.exe is the same in both

    def test_refusals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, copy = game_and_copy(root)
            with self.assertRaises(ViwoError):
                mods.pack(game, game, root / "x.zip")  # not a patched copy
            bad = root / "bad.zip"
            with zipfile.ZipFile(bad, "w") as z:
                manifest = {
                    "schema": 1,
                    "files": [{"path": "../evil.txt", "original": "", "sha256": "0"}],
                }
                z.writestr("viwo-mod.json", json.dumps(manifest))
                z.writestr("files/../evil.txt", "x")
            with self.assertRaises(ViwoError):
                mods.apply(runtime(root), game, [bad], copy)
            self.assertFalse((root / "evil.txt").exists())
            with self.assertRaises(ViwoError):
                mods.read_manifest(root / "p.patch.json")


if __name__ == "__main__":
    unittest.main()
