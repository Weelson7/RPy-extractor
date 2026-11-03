"""L3: T1 patch sets: offset patches check their original bytes, AOB patterns must match once,
bytes already patched read `already`, the game is never written, an existing patched copy is
patched in place, a set that does not fit is refused; CLI and API."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import ViwoError
from viwo.core import patchsets
from viwo.core.roundtrip import MARKER

BINARY = bytes.fromhex("4d5a9000") + b"\0" * 12 + bytes.fromhex("7405 8b45fc 90 c3") + b"\0" * 8


def fixture(root: Path) -> tuple[Path, Path]:
    game = root / "game"
    (game / "bin").mkdir(parents=True)
    (game / "bin" / "Game.exe").write_bytes(BINARY)
    patch = {
        "schema": 1,
        "title": "skip the check",
        "patches": [
            {"file": "bin/Game.exe", "offset": "0x10", "original": "74 05", "patched": "EB 05"},
            {"file": "bin/Game.exe", "pattern": "8B 45 ?? 90", "at": 3, "patched": "CC"},
        ],
    }
    set_path = root / "skip.patch.json"
    set_path.write_text(json.dumps(patch), encoding="utf-8")
    return game, set_path


class PatchSetTests(unittest.TestCase):
    def test_plan_apply_reapply_and_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, set_path = fixture(root)
            before = tree_hashes(game)
            report = patchsets.plan(game, patchsets.load(set_path))
            self.assertEqual([r["status"] for r in report["results"]], ["ready", "ready"])
            self.assertEqual(report["results"][1]["offset"], 0x15)
            rt, out = runtime(root), root / "patched"
            done = patchsets.apply(rt, game, set_path, out)
            self.assertTrue(done["verified"])
            data = (out / "bin" / "Game.exe").read_bytes()
            self.assertEqual((data[0x10], data[0x15]), (0xEB, 0xCC))
            self.assertEqual(tree_hashes(game), before)  # the game is only read
            self.assertTrue((out / MARKER / "skip.patch.json").is_file())
            again = patchsets.apply(rt, game, set_path, out)  # in place, bytes already there
            self.assertEqual([r["status"] for r in again["results"]], ["already", "already"])
            wrong = json.loads(set_path.read_text())
            wrong["patches"][0]["original"] = "75 05"
            set_path.write_text(json.dumps(wrong))
            with self.assertRaises(ViwoError) as err:
                patchsets.apply(rt, game, set_path, root / "other")
            self.assertIn("mismatch", err.exception.message)
            self.assertFalse((root / "other").exists())

    def test_bad_input_is_refused_and_cli_api(self) -> None:
        from viwo.api.handlers_tools import apply_patch_set
        from viwo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, set_path = fixture(root)
            for bad in ("7G", "", "?? 90"):
                with self.assertRaises(ViwoError):
                    patchsets._bytes(bad)
            self.assertEqual(
                patchsets.locate(game, {"file": "../x", "patched": "90"})["status"], "missing"
            )
            self.assertEqual(main(["--json", "patch", str(game), str(set_path), "--plan"]), 0)

            class App:
                rt = runtime(root)

            res = apply_patch_set(
                App(), {"gamePath": str(game), "patchSet": str(set_path), "plan": True}
            )
            self.assertTrue(res["success"] and res["ok"])


if __name__ == "__main__":
    unittest.main()
