"""L3: T1 patch sets: offset patches check their original bytes, AOB patterns must match once,
bytes already patched read `already`, the game is never written, an existing patched copy is
patched in place, a set that does not fit is refused; CLI and API."""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from tests.test_capture import script
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


FAKE_KSTOOL = """#!{python}
import sys
mode, text, address = sys.argv[1:4]
assert (mode, address) == ("x64", "140001010"), sys.argv
print(text + " = [ eb 0e 90 ]")
"""


def make_pe(path: Path) -> None:
    """A minimal PE32+: one .text section, VA 0x1000 at file offset 0x200, image base
    0x140000000; the code starts with `74 05` at RVA 0x1010."""
    head = bytearray(0x200)
    head[:2], head[0x3C:0x40] = b"MZ", (0x40).to_bytes(4, "little")
    head[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HH", head, 0x44, 0x8664, 1)
    struct.pack_into("<H", head, 0x54, 0xF0)  # optional header size
    struct.pack_into("<HxxxxxxxxxxxxxxxxxxxxxxQ", head, 0x58, 0x20B, 0x140000000)
    struct.pack_into("<8sIIII", head, 0x58 + 0xF0, b".text", 0x100, 0x1000, 0x200, 0x200)
    code = bytearray(b"\x90" * 0x200)
    code[0x10:0x13] = b"\x74\x05\x90"
    code[0x40:0x50] = bytes(range(0x40, 0x50))  # unique bytes for the signature
    path.write_bytes(bytes(head) + bytes(code))


class PeAsmTests(unittest.TestCase):
    def test_rva_asm_untouched_bytes_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            make_pe(game / "Game.exe")
            (root / "ks").mkdir()
            kstool = script(root / "ks", "kstool", FAKE_KSTOOL.format(python=sys.executable))
            rt = runtime(root, f"[tools]\nkeystone = {kstool}\n")
            patch = {
                "schema": 1,
                "title": "asm",
                "patches": [
                    {
                        "file": "Game.exe",
                        "rva": "0x1010",
                        "original": "74 05 90",
                        "asm": "jmp 0x140001020; nop",
                    }
                ],
            }
            set_path = root / "asm.patch.json"
            set_path.write_text(json.dumps(patch))
            planned = patchsets.plan(game, patchsets.load(set_path), rt.os)["results"][0]
            self.assertEqual(
                (planned["offset"], planned["new"], planned["status"]), (0x210, "eb 0e 90", "ready")
            )
            done = patchsets.apply(rt, game, set_path, root / "copy")
            self.assertTrue(done["verified"])  # the range has the new bytes, nothing else moved
            marker = root / "copy" / MARKER
            self.assertIn("0x210: 74 05 90 -> eb 0e 90", (marker / "asm.diff.txt").read_text())
            aob = json.loads((marker / "asm.aob.patch.json").read_text())
            self.assertEqual(len(aob["patches"]), 1)
            (root / "aob.patch.json").write_text(json.dumps(aob))
            again = patchsets.plan(game, patchsets.load(root / "aob.patch.json"))["results"][0]
            self.assertEqual((again["offset"], again["status"]), (0x210, "ready"))  # resolves again


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

    def test_a_patch_lands_only_inside_the_file(self) -> None:
        import random

        rng = random.Random(9)
        with tempfile.TemporaryDirectory() as tmp:
            game, _ = fixture(Path(tmp))
            size = len(BINARY)
            for _ in range(200):
                offset, width = rng.randint(-8, size + 8), rng.randint(1, 4)
                patch = {
                    "file": "bin/Game.exe",
                    "offset": str(offset),
                    "patched": " ".join(["90"] * width),
                }
                result = patchsets.locate(game, patch)
                fits = 0 <= offset and offset + width <= size
                self.assertEqual(result["status"] != "mismatch", fits, (offset, width, result))
                if not fits:
                    self.assertIn("out of range", result["reason"])
            for broken in (
                {"file": "bin/Game.exe", "patched": "90"},
                {"file": "bin/Game.exe", "offset": "zz", "patched": "90"},
            ):
                result = patchsets.locate(
                    game, broken
                )  # a malformed address is a reason, not a crash
                self.assertEqual(result["status"], "mismatch")
                self.assertIn("offset", result["reason"])

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
