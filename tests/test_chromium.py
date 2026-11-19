"""Chromium .pak (doc 8, doc 18): random version-4 and version-5 packs written byte by byte.
Every resource comes out under its id; an unchanged pack rebuilds byte for byte; an edited id
carries the new bytes and every other id and every version-5 alias is kept; the writer verifies."""

import random
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from viwo.plugins.chromium import PakBuiltin, read_pak
from viwo.plugins.chromium.pack import PakWriter, build_pak

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


def make_pak(version: int, res: list[tuple[int, bytes]], aliases: list[tuple[int, int]]) -> bytes:
    if version == 4:
        head = struct.pack("<II", 4, len(res)) + bytes([1])
        alias_bytes = b""
    else:
        head = struct.pack("<IB", 5, 1) + b"\0\0\0" + struct.pack("<HH", len(res), len(aliases))
        alias_bytes = b"".join(struct.pack("<HH", a, b) for a, b in aliases)
    start = len(head) + (len(res) + 1) * 6 + len(alias_bytes)
    index, at = bytearray(), start
    for rid, data in res:
        index += struct.pack("<HI", rid, at)
        at += len(data)
    index += struct.pack("<HI", 0, at)
    return head + bytes(index) + alias_bytes + b"".join(d for _, d in res)


class ChromiumTests(unittest.TestCase):
    def test_versions_round_trip_with_identity_and_edits(self) -> None:
        rng = random.Random(5)
        for case in range(12):
            version = rng.choice((4, 5))
            ids = rng.sample(range(1, 4000), rng.randint(1, 8))
            res = [(i, rng.randbytes(rng.randint(0, 300))) for i in ids]
            aliases = [(rng.randint(5000, 6000), rng.randrange(len(res)))] if version == 5 else []
            raw = make_pak(version, res, aliases)
            parsed = {rid: raw[s:e] for rid, s, e in read_pak(raw)[2]}
            self.assertEqual(parsed, dict(res))
            self.assertEqual(build_pak(raw, {}), raw)  # identity
            victim = rng.choice(ids)
            edited = build_pak(raw, {victim: b"EDITED-" + bytes([case])})
            back = {rid: edited[s:e] for rid, s, e in read_pak(edited)[2]}
            self.assertEqual(back[victim], b"EDITED-" + bytes([case]))
            for rid, data in res:
                if rid != victim:
                    self.assertEqual(back[rid], data)
            self.assertEqual(read_pak(edited)[3], aliases)

    def test_extract_and_pack_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = make_pak(5, [(10, b"alpha"), (20, b"beta!!"), (30, b"")], [(99, 1)])
            pak = root / "resources.pak"
            pak.write_bytes(raw)
            dest = root / "out"
            dest.mkdir()
            out = PakBuiltin().extract(pak, dest, CTX)
            self.assertEqual(out.files, 3, out)
            self.assertEqual((dest / "20.dat").read_bytes(), b"beta!!")
            edit = root / "edit"
            edit.write_bytes(b"BETA!!")
            copy = root / "copy.pak"
            copy.write_bytes(raw)
            res = PakWriter().pack(copy, {"20.dat": edit}, CTX)
            self.assertTrue(res.ok, res)
            self.assertEqual(PakWriter().verify(copy, {"20.dat": edit}, CTX), [])


class ChromiumPackEdgeTests(unittest.TestCase):
    def test_pack_names_unknown_members_and_reports_a_bad_container(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy = root / "c.pak"
            copy.write_bytes(make_pak(4, [(10, b"a"), (20, b"bb")], []))
            e1 = root / "e1"
            e1.write_bytes(b"ZZ")
            # 99.dat is a valid id form but not in the pack; x.dat has no id at all
            out = PakWriter().pack(copy, {"99.dat": e1, "x.dat": e1}, CTX)
            self.assertTrue(out.ok and out.files == 0, out)
            self.assertIn("2 member(s)", " ".join(out.notes))
            bad = root / "bad.pak"
            bad.write_bytes(b"nope")
            self.assertFalse(PakWriter().pack(bad, {"10.dat": e1}, CTX).ok)

    def test_verify_flags_a_member_that_differs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pak = root / "p.pak"
            pak.write_bytes(make_pak(4, [(10, b"a"), (20, b"bb")], []))  # id 20 holds b"bb"
            other = root / "o"
            other.write_bytes(b"DIFFERS")
            self.assertEqual(PakWriter().verify(pak, {"20.dat": other}, CTX), ["20.dat"])


if __name__ == "__main__":
    unittest.main()
