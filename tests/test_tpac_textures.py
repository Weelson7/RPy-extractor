"""L3: Bannerlord TPAC textures to DDS. Synthetic packages hold one texture item per format and
random shape (cubemaps too); the DDS that comes out names the shape the data was built with,
carries the data unchanged, and opens in Pillow for the formats Pillow implements; a texture of
an unknown shape stays a raw .bin and is counted in a note. Verified on the real thing too:
Native/pack_18.tpac, 188 of 190 textures (see docs/HANDOFF.md 1.5.2)."""

from __future__ import annotations

import random
import struct
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from viwo.contracts.types import CancelToken
from viwo.plugins.taleworlds import TpacBuiltin
from viwo.plugins.taleworlds.textures import FORMATS, TEXTURE, chain

PILLOW_READS = {"DXT1", "DXT3", "DXT5", "BC4", "BC5", "BC7", "R8_UNORM", "R8G8B8A8_UNORM"}


def package(items: list[tuple[str, bytes, bytes]]) -> bytes:
    """A version-2 TPAC of texture items: (name, metadata, the one raw segment)."""
    size = sum(16 + 16 + 4 + 4 + len(n.encode()) + 8 + len(m) + 8 + 4 + 69 + 4 for n, m, _ in items)
    body, data, data_at = b"", b"", 36 + size
    for name, meta, segment in items:
        body += TEXTURE + uuid.uuid4().bytes + struct.pack("<I", 0)
        body += struct.pack("<i", len(name.encode())) + name.encode()
        body += struct.pack("<Q", len(meta)) + meta + struct.pack("<q", 0) + struct.pack("<i", 1)
        body += struct.pack("<QQQ", data_at + len(data), len(segment), len(segment))
        body += bytes(44) + bytes([0]) + struct.pack("<i", 0)
        data += segment
    head = (
        b"TPAC"
        + struct.pack("<I", 2)
        + uuid.uuid4().bytes
        + struct.pack("<III", len(items), len(body), 0)
    )
    return head + body + data


def meta(fmt: str, cube: bool, full: tuple[int, int, int]) -> bytes:
    """Tags, then the full size and the format as the real metadata lays them out."""
    tags = b"\x0a\x00\x00\x00is_cubemap" if cube else b""
    width, height, mips = full
    size = struct.pack("<IIIBH", width, height, 1, mips, 1)
    return (
        bytes(17) + tags + bytes(5) + size + struct.pack("<I", len(fmt)) + fmt.encode() + bytes(8)
    )


def header(dds: bytes) -> tuple[int, int, int, int]:
    """(width, height, mip count, payload offset) of a DDS file."""
    height, width = struct.unpack_from("<II", dds, 12)
    mips = struct.unpack_from("<I", dds, 28)[0]
    dx10 = dds[84:88] == b"DX10"
    return width, height, mips, 128 + (20 if dx10 else 0)


class TpacTextureTests(unittest.TestCase):
    def extract(self, items) -> tuple[Path, object]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "p.tpac").write_bytes(package(items))
        out = TpacBuiltin().extract(
            root / "p.tpac", root / "out", SimpleNamespace(cancel=CancelToken())
        )
        return root / "out", out

    def test_every_format_and_shape_becomes_a_faithful_dds(self) -> None:
        rng = random.Random(6)
        cases, items = [], []
        for fmt in FORMATS:
            for i in range(5):
                cube = i == 4
                width = 1 << rng.randint(2, 9)  # full size; the package may hold a lower chain
                height = (
                    width
                    if cube
                    else max(1, width >> rng.randint(0, 3) if i % 2 else width << rng.randint(0, 2))
                )
                mips = max(width, height).bit_length() if i != 3 else 1
                level = rng.randint(0, mips - 1)
                w, h = max(1, width >> level), max(1, height >> level)
                body = rng.randbytes(chain(w, h, fmt, mips - level) * (6 if cube else 1))
                cases.append((f"{fmt}_{i}", fmt, cube, (w, h, mips - level), body))
                items.append((f"{fmt}_{i}", meta(fmt, cube, (width, height, mips)), body))
        out, result = self.extract(items)
        self.assertTrue(result.ok, result.error)
        from PIL import Image

        for name, fmt, cube, stored, body in cases:
            dds = (out / f"{name}.dds").read_bytes()
            w, h, mips, at = header(dds)
            self.assertEqual(((w, h, mips), dds[at:]), (stored, body), name)
            if fmt in PILLOW_READS and not cube and min(w, h) >= 4:
                with Image.open(out / f"{name}.dds") as image:
                    self.assertEqual(image.size, (w, h), name)

    def test_an_unknown_shape_stays_raw_and_is_said(self) -> None:
        out, result = self.extract([("odd", meta("BC4", False, (256, 256, 9)), b"\0" * 49152)])
        self.assertTrue((out / "odd.0.bin").is_file())
        self.assertIn("1 texture(s) of an unknown shape kept as raw .bin", result.notes)


if __name__ == "__main__":
    unittest.main()
