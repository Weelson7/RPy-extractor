"""L3: T1 patch sets: offset patches check their original bytes, AOB patterns must match once,
bytes already patched read `already`, the game is never written, an existing patched copy is
patched in place, a set that does not fit is refused; CLI and API. Properties: a pattern's
matches are every position it fits, overlapping ones included (int3/NOP padding); a set plans
`ok` exactly when no two of its located patches write the same bytes of one file, both of an
overlapping pair are refused naming each other, and a set that applies re-applies as
`already`."""

from __future__ import annotations

import json
import random
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


def _brute(data: bytes, pattern: bytes, mask: list[bool]) -> list[int]:
    """Every start where the pattern fits, by hand."""

    def fits(i: int) -> bool:
        return all(not m or data[i + k] == b for k, (b, m) in enumerate(zip(pattern, mask)))

    return [i for i in range(len(data) - len(pattern) + 1) if fits(i)]


SPELLINGS = {"bin/a.bin": "a", "./bin/a.bin": "a", "bin\\a.bin": "a", "b.bin": "b"}


def _random_patch(rng: random.Random, data: bytes) -> tuple[dict, int, int]:
    """(patch, start, width): an offset patch, or an AOB one whose 12-byte pattern is unique."""
    width = rng.randint(1, 4)
    start = rng.randrange(0, len(data) - width)
    patch = {"file": rng.choice(list(SPELLINGS)), "patched": rng.randbytes(width).hex(" ")}
    head = max(0, min(start - rng.randint(0, 12 - width), len(data) - 12))
    pattern = data[head : head + 12]
    if rng.random() < 0.4 and _brute(data, pattern, [True] * 12) == [head]:
        return {**patch, "pattern": pattern.hex(" "), "at": start - head}, start, width
    original = data[start : start + width].hex(" ")
    return {**patch, "offset": hex(start), "original": original}, start, width


class OverlapTests(unittest.TestCase):
    def test_every_match_counts_overlapping_ones_too(self) -> None:
        rng = random.Random(70)
        for _ in range(400):
            data = bytes(rng.choice(b"\xcc\x90") for _ in range(rng.randint(0, 40)))  # padding
            size = rng.randint(1, 5)
            pattern = bytes(rng.choice(b"\xcc\x90") for _ in range(size))
            mask = [rng.random() < 0.8 for _ in range(size)]
            self.assertEqual(patchsets._hits(data, pattern, mask), _brute(data, pattern, mask))
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pad.bin").write_bytes(b"\x00" + b"\xcc" * 4 + b"\x00")
            patch = {"file": "pad.bin", "pattern": "CC CC CC", "patched": "90"}
            found = patchsets.locate(Path(tmp), patch)  # two matches in four bytes: not unique
            self.assertEqual(found["status"], "mismatch")
            self.assertEqual(found["reason"], "pattern matches 2 times (needs exactly one)")

    def test_a_set_applies_exactly_when_no_two_patches_write_the_same_bytes(self) -> None:
        rng = random.Random(71)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root)
            for case in range(60):
                game, data = root / f"g{case}", rng.randbytes(rng.randint(40, 200))
                (game / "bin").mkdir(parents=True)
                (game / "bin" / "a.bin").write_bytes(data)
                (game / "b.bin").write_bytes(data)
                made = [_random_patch(rng, data) for _ in range(rng.randint(1, 5))]
                spans = [(SPELLINGS[p["file"]], s, s + w) for p, s, w in made]
                pairs = {
                    (i, j)
                    for i, (f, a, a_end) in enumerate(spans)
                    for j, (g, b, b_end) in enumerate(spans)
                    if i < j and f == g and a < b_end and b < a_end
                }
                clash = {k for pair in pairs for k in pair}
                set_path = root / f"s{case}.patch.json"
                patch_set = {"schema": 1, "patches": [p for p, _, _ in made]}
                set_path.write_text(json.dumps(patch_set), encoding="utf-8")
                report = patchsets.plan(game, patch_set)
                self.assertEqual(report["ok"], not clash, report)
                for i, r in enumerate(report["results"]):
                    self.assertEqual(r["status"] == "overlap", i in clash, (i, r))
                for i, j in pairs:  # both of a pair are refused, each naming both
                    for k in (i, j):
                        self.assertIn(f"patches {i + 1} (", report["results"][k]["reason"])
                        self.assertIn(f") and {j + 1} (", report["results"][k]["reason"])
                copy = root / f"c{case}"
                if clash:
                    with self.assertRaises(ViwoError) as err:
                        patchsets.apply(rt, game, set_path, copy)
                    self.assertIn("overlap", err.exception.message)
                    self.assertFalse(copy.exists())
                    continue
                self.assertTrue(patchsets.apply(rt, game, set_path, copy)["verified"])
                if all(
                    "offset" in p for p, _, _ in made
                ):  # (a neighbour may edit an AOB's context)
                    again = patchsets.apply(rt, game, set_path, copy)  # re-applies as it is
                    self.assertEqual({r["status"] for r in again["results"]}, {"already"})


if __name__ == "__main__":
    unittest.main()
