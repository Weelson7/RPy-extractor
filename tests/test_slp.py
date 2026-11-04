"""L3: Genie SLP sprites to PNG. A small encoder writes random sprites with every command the
decoder reads (colour lists short and long, skips, fills, player colours, shadows, outlines,
empty rows); decoding gives back exactly the pixels encoded. Verified on the real thing too:
AoE II HD's graphics.drs decodes (CHANGELOG.md 1.6.0)."""

from __future__ import annotations

import random
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from viwo.plugins.genie.slp import PLAYER, SHADOW, SlpDecoder, frames, palette

COLORS = [(i, 255 - i, (i * 7) % 256, 255) for i in range(256)]
PAL = "JASC-PAL\n0100\n256\n" + "\n".join(f"{r} {g} {b}" for r, g, b, _ in COLORS) + "\n"


def encode_row(rng, width: int) -> tuple[bytes, list]:
    """A random command stream for one row, and the pixels it must decode to."""
    out, pixels = bytearray(), []
    while len(pixels) < width:
        n, kind = rng.randint(1, min(20, width - len(pixels))), rng.choice("lsLfpPhoS")
        idx = [rng.randrange(0, 200) for _ in range(n)]
        if kind == "l" and n < 64:
            out += bytes([n << 2]) + bytes(idx)
            pixels += [COLORS[i] for i in idx]
        elif kind == "L":
            out += bytes([((n >> 8) << 4) | 0x02, n & 0xFF]) + bytes(idx)
            pixels += [COLORS[i] for i in idx]
        elif kind == "s" and n < 64:
            out += bytes([(n << 2) | 0x01])
            pixels += [None] * n
        elif kind in "fp" and n < 16:
            out += bytes([(n << 4) | (0x07 if kind == "f" else 0x0A), idx[0]])
            pixels += [COLORS[idx[0] + (PLAYER if kind == "p" else 0)]] * n
        elif kind == "P":
            out += bytes([0x06, n]) + bytes(idx)
            pixels += [COLORS[i + PLAYER] for i in idx]
        elif kind == "h" and n < 16:
            out += bytes([(n << 4) | 0x0B])
            pixels += [SHADOW] * n
        elif kind == "o":
            out += bytes([0x4E])
            pixels += [None]
        else:
            out += bytes([0x03 | ((n >> 8) << 4), n & 0xFF])
            pixels += [None] * n
    return bytes(out) + b"\x0f", pixels


def encode(rng, sizes: list[tuple[int, int]]) -> tuple[bytes, list]:
    head = b"2.0N" + struct.pack("<i", len(sizes)) + b"ViWo test".ljust(24, b"\0")
    records, body, expected = b"", b"", []
    base = 32 + 32 * len(sizes)
    for width, height in sizes:
        outline_at = base + len(body)
        rows = [
            encode_row(rng, width) if rng.random() > 0.15 else (b"", None) for _ in range(height)
        ]
        outline = b"".join(struct.pack("<HH", 0 if p is not None else 0x8000, 0) for _, p in rows)
        cmds_at = outline_at + len(outline)
        offsets, stream = [], b""
        for cmd, _ in rows:
            offsets.append(cmds_at + 4 * height + len(stream))
            stream += cmd
        body += outline + struct.pack(f"<{height}I", *offsets) + stream
        records += struct.pack("<IIIIiiii", cmds_at, outline_at, 0, 0, width, height, 0, 0)
        expected.append([p if p is not None else [] for _, p in rows])
    return head + records + body, expected


class SlpTests(unittest.TestCase):
    def test_random_sprites_decode_to_exactly_their_pixels(self) -> None:
        rng = random.Random(8)
        for _ in range(60):
            sizes = [(rng.randint(1, 40), rng.randint(1, 12)) for _ in range(rng.randint(1, 5))]
            data, expected = encode(rng, sizes)
            got = frames(data, COLORS)
            self.assertEqual([rows for _, _, rows in got], expected)

    def test_the_decoder_writes_a_sheet_and_says_when_the_palette_is_missing(self) -> None:
        data, _ = encode(random.Random(2), [(10, 6), (7, 9)])
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "slp").mkdir()
            (ws / "slp" / "1.slp").write_bytes(data)
            missing = SlpDecoder().decode(ws / "slp" / "1.slp", ws, SimpleNamespace())
            self.assertIn("palette", missing.error)
            (ws / "bina").mkdir()
            (ws / "bina" / "50500.bina").write_text(PAL, encoding="ascii")
            done = SlpDecoder().decode(ws / "slp" / "1.slp", ws, SimpleNamespace())
            self.assertTrue(done.ok, done.error)
            from PIL import Image

            with Image.open(ws / "1.png") as sheet:
                self.assertEqual(sheet.size, (20, 9))  # two cells of the largest frame
        self.assertEqual(palette(PAL)[3], COLORS[3])


if __name__ == "__main__":
    unittest.main()
