"""L3: pack.tpac (doc 18.4), the way back into a TaleWorlds TPAC, property tests on packages
written here as Bannerlord lays them out (segments raw or LZ4 HC level 12, each entry holding
the xxHash64 of its data, a texture with its full chain and the chain from mip 1 as a second
segment). Every member given back unchanged gives the same bytes; random edits read back through
the plugin's own reader as edited, the other members unchanged, every entry's hash matching its
data, and no byte changed outside the touched entries and data; a texture's tail segment follows
its edit, a segment that is not its tail is left and said; a DDS of another size is refused by
name, so are two edits of one segment; a member the package does not hold is said; without lz4
the segment is stored raw, said; a segment another entry shares is never written over. End to
end: an edited PNG of a BC7 texture goes back through decode.image and pack.tpac and verifies.
The real check (one Bannerlord package, unchanged and edited) is in CHANGELOG.md, with pack.tpac."""

from __future__ import annotations

import io
import random
import struct
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import lz4.block
from PIL import Image

from tests.helpers import runtime
from tests.test_encoders import png_of
from tests.test_tpac_textures import meta as texture_meta
from viwo.backends.blocks.encode_bc import compress
from viwo.contracts.pipeline import ExtractionRequest
from viwo.contracts.types import CancelToken, OutcomeKind
from viwo.core.pipeline.runner import extract
from viwo.core.roundtrip import repack
from viwo.plugins.taleworlds import TpacBuiltin, entries
from viwo.plugins.taleworlds.pack import TpacWriter, write_tpac
from viwo.plugins.taleworlds.textures import TEXTURE, chain
from viwo.plugins.taleworlds.xxh64 import xxh64

OTHER = bytes(range(16))  # a type GUID that is not a texture
CTX = SimpleNamespace(cancel=CancelToken())


def lz4hc(data: bytes) -> bytes:
    return lz4.block.compress(data, mode="high_compression", compression=12, store_size=False)


def package(items: list, share: bool = False) -> bytes:
    """A version-2 TPAC: items (name, type GUID, metadata, [(data, format)]); `share`: the last
    item's first segment entry points at the first item's first segment."""
    index, blobs, entries_at = b"", [], []
    for name, kind, meta, segments in items:
        index += kind + uuid.UUID(int=len(index)).bytes + struct.pack("<I", 0)
        index += struct.pack("<i", len(name.encode())) + name.encode()
        index += struct.pack("<Q", len(meta)) + meta + struct.pack("<q", 7)
        index += struct.pack("<i", len(segments))
        for data, fmt in segments:
            entries_at.append(len(index))
            stored = lz4hc(data) if fmt else data
            blobs.append(stored)
            index += struct.pack("<QQQ", 0, len(data), len(stored)) + bytes(32)
            index += struct.pack("<QI", xxh64(data), 4) + bytes((fmt,))
        index += struct.pack("<i", 0)
    out = bytearray(b"TPAC" + struct.pack("<I", 2) + bytes(16))
    out += struct.pack("<III", len(items), len(index), 0) + index
    for n, (at, blob) in enumerate(zip(entries_at, blobs)):
        offset = len(out) if not (share and n == len(blobs) - 1) else 36 + len(index)
        struct.pack_into("<Q", out, 36 + at, offset)
        out += blob if offset == len(out) else b""
    return bytes(out)


def extracted(root: Path, blob: bytes, name: str = "out") -> dict[str, bytes]:
    (root / f"{name}.tpac").write_bytes(blob)
    result = TpacBuiltin().extract(root / f"{name}.tpac", root / name, CTX)
    assert result.ok, result.error
    return {p.name: p.read_bytes() for p in (root / name).iterdir()}


def segments_of(blob: bytes) -> list[tuple]:
    """Every segment entry of a package, through the plugin's reader."""
    return [s for _, segments, _, _ in entries(io.BytesIO(blob)) for s in segments]


def texture(rng, fmt: str = "DXT5") -> tuple:
    """A texture item: its full chain (LZ4) and the chain from mip 1 (raw), as Bannerlord."""
    side = 1 << rng.randint(3, 6)
    mips = side.bit_length()
    full = rng.randbytes(chain(side, side, fmt, mips))
    tail = full[chain(side, side, fmt, 1) :]
    meta = texture_meta(fmt, False, (side, side, mips))
    return ("tex", TEXTURE, meta, [(tail, 0), (full, 1)]), side


def random_items(rng) -> list:
    items = []
    for n in range(rng.randint(1, 4)):
        segments = [(rng.randbytes(rng.randint(1, 300)), rng.choice((0, 1))) for _ in "ab"]
        items.append((f"item{n}", OTHER, rng.randbytes(rng.randint(0, 40)), segments))
    return items


class XxhTests(unittest.TestCase):
    def test_reference_vectors(self) -> None:
        self.assertEqual(xxh64(b""), 0xEF46DB3751D8E999)
        self.assertEqual(xxh64(b"a"), 0xD24EC4F1A98C6E5B)
        self.assertEqual(xxh64(b"abc"), 0x44BC2CF5AD770999)
        self.assertEqual(xxh64(b"Nobody inspects the spammish repetition"), 0xFBCEA83C8A378BF1)


class PackTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_members_given_back_unchanged_give_the_same_bytes(self) -> None:
        rng = random.Random(101)
        for n in range(20):
            tex, _ = texture(rng)
            blob = package([*random_items(rng), tex])
            members = extracted(self.root, blob, f"o{n}")
            for name, data in members.items():
                (self.root / name).write_bytes(data)
            write_tpac(
                self.root / f"o{n}.tpac", {m: self.root / m for m in members}, self.root / "s"
            )
            self.assertEqual((self.root / "s").read_bytes(), blob)

    def test_edits_read_back_and_nothing_else_changes(self) -> None:
        rng = random.Random(102)
        for n in range(30):
            items = random_items(rng)
            blob = package(items)
            before = extracted(self.root, blob, f"b{n}")
            edits = {m: rng.randbytes(rng.randint(0, 400)) for m in before if rng.random() < 0.5}
            for name, data in edits.items():
                (self.root / name).write_bytes(data)
            out = self.root / f"e{n}.tpac"
            write_tpac(self.root / f"b{n}.tpac", {m: self.root / m for m in edits}, out)
            after = extracted(self.root, out.read_bytes(), f"a{n}")
            self.assertEqual(after, before | edits)
            self.check_entries(blob, out.read_bytes())

    def check_entries(self, old: bytes, new: bytes) -> None:
        """Every entry's hash is its data's; within the old length, the bytes changed are the
        rewritten entries' offset, sizes, hash and format and their old data, nothing else."""
        olds, news = segments_of(old), segments_of(new)
        allowed = set()
        for (o_off, _, o_stored, _, at), now in zip(olds, news):
            data = new[now[0] : now[0] + now[2]]
            data = lz4.block.decompress(data, uncompressed_size=now[1]) if now[3] else data
            self.assertEqual(struct.unpack_from("<Q", new, at + 56)[0], xxh64(data))
            if new[at : at + 69] != old[at : at + 69]:
                allowed |= {*range(at, at + 24), *range(at + 56, at + 64), at + 68}
                allowed |= set(range(o_off, o_off + o_stored))
        changed = {i for i in range(len(old)) if old[i] != new[i]}
        self.assertLessEqual(changed, allowed)
        self.assertGreaterEqual(len(new), len(old))

    def test_a_texture_edit_carries_its_tail_and_keeps_its_shape(self) -> None:
        rng = random.Random(103)
        for n in range(10):
            (name, kind, meta, segments), side = texture(rng, rng.choice(("DXT5", "BC7")))
            segments.append((rng.randbytes(50), 0))  # not a part of the chain
            blob = package([(name, kind, meta, segments)])
            dds = extracted(self.root, blob, f"t{n}")["tex.dds"]
            head = len(dds) - len(segments[1][0])
            edit = dds[:head] + rng.randbytes(len(dds) - head)
            (self.root / "tex.dds").write_bytes(edit)
            out = self.root / f"u{n}.tpac"
            notes = write_tpac(self.root / f"t{n}.tpac", {"tex.dds": self.root / "tex.dds"}, out)
            self.assertEqual(
                notes, ["tex.dds: segment 2 is not a part of its chain: left as it was"]
            )
            self.assertEqual(extracted(self.root, out.read_bytes(), f"v{n}"), {"tex.dds": edit})
            first = segments_of(out.read_bytes())[0]  # the chain from mip 1, stored raw
            tail = out.read_bytes()[first[0] : first[0] + first[2]]
            self.assertEqual(tail, edit[len(edit) - len(segments[0][0]) :])
            self.check_entries(blob, out.read_bytes())
            for bad in (dds[:12] + struct.pack("<II", side * 2, side) + dds[20:], dds[:-1]):
                (self.root / "tex.dds").write_bytes(bad)
                with self.assertRaisesRegex(ValueError, f"keep the texture's {side}x{side}"):
                    write_tpac(self.root / f"t{n}.tpac", {"tex.dds": self.root / "tex.dds"}, out)

    def test_what_cannot_be_written_is_said(self) -> None:
        rng = random.Random(104)
        tex, _ = texture(rng)
        blob = package([("item0", OTHER, b"", [(b"a" * 50, 0), (b"b" * 50, 1)]), tex])
        original = self.root / "p.tpac"
        original.write_bytes(blob)
        members = extracted(self.root, blob, "p")
        (self.root / "e.bin").write_bytes(b"new")
        notes = write_tpac(original, {"nope.0.bin": self.root / "e.bin"}, self.root / "q")
        self.assertEqual(notes, ["nope.0.bin: not a member of this package: not written"])
        (self.root / "tex.dds").write_bytes(members["tex.dds"])
        both = {"tex.dds": self.root / "tex.dds", "tex.1.bin": self.root / "e.bin"}
        with self.assertRaisesRegex(ValueError, "two edited members write the same segment"):
            write_tpac(original, both, self.root / "q")
        with mock.patch.dict(sys.modules, {"lz4": None, "lz4.block": None}):
            notes = write_tpac(original, {"item0.1.bin": self.root / "e.bin"}, self.root / "q")
            self.assertEqual(
                notes, ["the lz4 package is missing: a segment was stored uncompressed"]
            )
            self.assertEqual(segments_of((self.root / "q").read_bytes())[1][2:4], (3, 0))
            out = TpacWriter().pack(original, {"tex.dds": self.root / "tex.dds"}, CTX)
            self.assertEqual(out.kind, OutcomeKind.FAILED)
            self.assertIn("pip install lz4", out.error)
        self.assertEqual(original.read_bytes(), blob)  # a failed pack leaves the package
        self.assertFalse((self.root / "p.tpac.viwo-tmp").exists())
        ok = TpacWriter().pack(original, {"item0.0.bin": self.root / "e.bin"}, CTX)
        self.assertEqual(
            (ok.kind, extracted(self.root, original.read_bytes(), "r")["item0.0.bin"]),
            (OutcomeKind.OK, b"new"),
        )

    def test_a_shared_segment_is_never_written_over(self) -> None:
        rng = random.Random(105)
        items = [("a", OTHER, b"", [(b"shared" * 9, 0)]), ("b", OTHER, b"", [(b"shared" * 9, 0)])]
        blob = package(items, share=True)
        before = extracted(self.root, blob, "s")
        self.assertEqual(before["b.0.bin"], before["a.0.bin"])
        (self.root / "e.bin").write_bytes(rng.randbytes(10))
        write_tpac(self.root / "s.tpac", {"b.0.bin": self.root / "e.bin"}, self.root / "o.tpac")
        after = extracted(self.root, (self.root / "o.tpac").read_bytes(), "o")
        self.assertEqual(after, before | {"b.0.bin": (self.root / "e.bin").read_bytes()})


class RepackTests(unittest.TestCase):
    def test_an_edited_png_goes_back_into_its_package_and_verifies(self) -> None:
        rng = random.Random(106)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt, game = runtime(root), root / "bannerlord"
            (game / "Modules" / "M" / "AssetPackages").mkdir(parents=True)
            picture = Image.frombytes("RGBA", (16, 16), rng.randbytes(1024))
            levels = [picture.resize((16 >> n, 16 >> n)) for n in range(5)]
            full = b"".join(compress(p.tobytes(), p.width, p.height, "BC7") for p in levels)
            meta = texture_meta("BC7", False, (16, 16, 5))
            items = [("icon", TEXTURE, meta, [(full[256:], 0), (full, 1)])]
            items.append(("other", OTHER, b"", [(b"keep me", 1)]))
            pack_path = game / "Modules" / "M" / "AssetPackages" / "p.tpac"
            pack_path.write_bytes(package(items))
            work = root / "ws"
            extract(rt, ExtractionRequest(str(game), str(work)), "j", lambda e: None, CancelToken())
            pngs = sorted(work.rglob("icon.dds.png"))
            self.assertEqual(len(pngs), 1, sorted(p.name for p in work.rglob("*")))
            edit = Image.frombytes("RGBA", (16, 16), rng.randbytes(1024))
            pngs[0].write_bytes(png_of(edit))
            report = repack(rt, work, root / "copy")
            self.assertTrue(report["verified"], report)
            item = report["plan"][0]
            self.assertEqual(
                (item["slot"], item["ways"][0]["encoder"]), ("pack.tpac", "decode.image")
            )
            copy = root / "copy" / pack_path.relative_to(game)
            back = extracted(root, copy.read_bytes(), "back")
            self.assertEqual(back["other.0.bin"], b"keep me")
            self.assertEqual(pack_path.read_bytes(), package(items))  # the game: only read


if __name__ == "__main__":
    unittest.main()
