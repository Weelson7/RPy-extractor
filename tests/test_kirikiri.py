"""L3: KiriKiri XP3 over random archives in every layout the format has (version 1 and 2
headers, stored or compressed index, stored or compressed segments, files split over several
segments, foreign chunks in the index): every unencrypted file comes out byte for byte, an
encrypted one is counted and named, never guessed, and an archive of only encrypted files
needs a key."""

from __future__ import annotations

import random
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace

from viwo.contracts.types import OutcomeKind
from viwo.plugins.kirikiri import ENCRYPTED, MAGIC, KiriKiriPlugin, Xp3Builtin


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + struct.pack("<Q", len(body)) + body


def build(files, rng: random.Random, v2: bool, packed_index: bool) -> bytes:
    """files: [(name, data, encrypted)]; each file split into 1-3 random segments."""
    start = 11 + 8 + (4 + 1 + 8 + 8 if v2 else 0)  # v2: a version, then the header at 0x17
    body, index = b"", b""
    for name, data, encrypted in files:
        cuts = sorted(rng.sample(range(1, len(data)), min(rng.randint(0, 2), len(data) - 1)))
        segm = b""
        for part in (data[a:b] for a, b in zip([0, *cuts], [*cuts, len(data)])):
            squeeze = rng.random() < 0.5
            stored = zlib.compress(part) if squeeze else part
            segm += struct.pack("<IQQQ", int(squeeze), start + len(body), len(part), len(stored))
            body += stored
        flags = ENCRYPTED if encrypted else 0
        info = struct.pack("<IQQH", flags, len(data), len(data), len(name)) + name.encode(
            "utf-16-le"
        )
        index += _chunk(
            b"File", _chunk(b"info", info) + _chunk(b"segm", segm) + _chunk(b"adlr", b"\0" * 4)
        )
        if rng.random() < 0.3:
            index += _chunk(b"hnfn", b"\0" * 8)  # a chunk ViWo does not use: skipped
    at = start + len(body)
    tail = (
        b"\x01" + struct.pack("<QQ", len(zlib.compress(index)), len(index)) + zlib.compress(index)
        if packed_index
        else b"\x00" + struct.pack("<Q", len(index)) + index
    )
    v2_head = struct.pack("<QI", 0x17, 1) + b"\x80" + struct.pack("<QQ", 0, at)  # at 0x17
    head = MAGIC + (v2_head if v2 else struct.pack("<Q", at))
    return head + body + tail


class Xp3Tests(unittest.TestCase):
    def test_every_layout_gives_back_every_plain_file(self) -> None:
        rng = random.Random(23)
        ctx = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(30):
                files = [
                    (
                        f"data/{rng.choice('abc')}/f{i}.bin",
                        rng.randbytes(rng.randint(1, 300)),
                        rng.random() < 0.25,
                    )
                    for i in range(rng.randint(1, 6))
                ]
                archive = root / f"a{case}.xp3"
                archive.write_bytes(build(files, rng, rng.random() < 0.5, rng.random() < 0.5))
                dest = root / f"out{case}"
                out = Xp3Builtin().extract(archive, dest, ctx)
                plain = [(n, d) for n, d, enc in files if not enc]
                locked = len(files) - len(plain)
                if not plain:
                    self.assertEqual(out.kind, OutcomeKind.NEEDS_KEY)
                    self.assertIn(f"{locked} entries", out.error)
                    continue
                self.assertEqual((out.kind, out.files), (OutcomeKind.OK, len(plain)), out.error)
                for name, data in plain:
                    self.assertEqual((dest / name).read_bytes(), data)
                self.assertEqual(bool(out.notes), bool(locked))  # skipped entries are said

    def test_bounds_names_and_detection(self) -> None:
        from viwo.plugins.kirikiri import _segment

        rng = random.Random(2)
        ctx = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "a.xp3"
            archive.write_bytes(
                build(
                    [("../escape.bin", b"x" * 20, False), ("ok.bin", b"y" * 9, False)],
                    rng,
                    False,
                    False,
                )
            )
            out = Xp3Builtin().extract(archive, root / "o", ctx)
            self.assertEqual(out.files, 1)  # the traversal name is never written
            self.assertFalse((root / "escape.bin").exists())
            short = root / "z.bin"
            short.write_bytes(zlib.compress(b"a" * 10))
            with open(short, "rb") as z:
                with self.assertRaises(ValueError):
                    _segment(z, False, 0, -1, 4)  # a negative size is damage
                with self.assertRaises(ValueError):  # inflates short of its declared size
                    _segment(z, True, 0, 50, short.stat().st_size)
            huge = bytearray(build([("a.bin", b"a" * 10, False)], rng, False, False))
            at = struct.unpack_from("<Q", huge, 11)[0]
            huge[at + 1 : at + 9] = struct.pack("<Q", 1 << 40)  # a stored index of 1 TiB
            archive.write_bytes(bytes(huge))
            self.assertIn("bad XP3", Xp3Builtin().extract(archive, root / "h", ctx).error)
            cancelled = SimpleNamespace(cancel=SimpleNamespace(cancelled=True))
            archive.write_bytes(build([("a.bin", b"a" * 10, False)], rng, False, False))
            self.assertEqual(Xp3Builtin().extract(archive, root / "c", cancelled).files, 0)
        probe = SimpleNamespace(
            with_suffix=lambda s: [], head=lambda p, n: b"", has_name=lambda *n: True
        )
        found = KiriKiriPlugin().detect(probe)
        self.assertEqual((found.confidence, found.evidence), (0.6, ("KiriKiri runtime",)))


if __name__ == "__main__":
    unittest.main()
