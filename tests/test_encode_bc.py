"""L3: ViWo's block encoder (doc 18.3, the way back of a block-compressed DDS), property tests.
For random images, BC1/BC3/BC4/BC5 blocks decoded again (by a reference decoder written here,
the expansion ffmpeg uses, and by Pillow) stay within the format's bound: a colour channel
within its block's range plus the RGB565 step, a single channel within (max - min) / 14 plus
rounding; a block of two colours within the RGB565 step; a flat block within 1 for any colour
and exact for a colour an endpoint holds; alpha exact at 0 and 255 (BC1: transparent or not).
The same pixels give the same bytes. Written back as a DDS, the original's header is kept (DX10
too) with the new size, the mip chain rebuilt; ATI2 keeps ffmpeg's channel order; BC2, BC6H,
BC7, signed BC4/BC5 and cube maps are refused by name."""

from __future__ import annotations

import io
import random
import struct
import unittest

from PIL import Image

from tests.test_encoders import png_of
from viwo.core import encode_bc
from viwo.core.encode_bc import E5, E6, compress, size
from viwo.core.encode_dds import layout, write_dds

FOURCC = {"BC1": b"DXT1", "BC3": b"DXT5", "BC4": b"BC4U", "BC5": b"BC5U"}
CHANNELS = {"BC1": (0, 1, 2), "BC3": (0, 1, 2, 3), "BC4": (0,), "BC5": (0, 1)}


def _bc4(block: bytes) -> list[int]:
    a0, a1 = block[0], block[1]
    if a0 > a1:
        levels = [a0, a1] + [((7 - s) * a0 + s * a1) // 7 for s in range(1, 7)]
    else:
        levels = [a0, a1] + [((5 - s) * a0 + s * a1) // 5 for s in range(1, 5)] + [0, 255]
    bits = int.from_bytes(block[2:8], "little")
    return [levels[(bits >> (3 * i)) & 7] for i in range(16)]


def _bc1(block: bytes, four: bool) -> list[tuple]:
    """A reference BC1 decoder with ffmpeg's endpoint expansion and truncating mixes."""
    c0, c1, bits = struct.unpack("<HHI", block)
    p = [(E5[c >> 11], E6[(c >> 5) & 63], E5[c & 31], 255) for c in (c0, c1)]
    if four or c0 > c1:
        p += [tuple((2 * x + y) // 3 for x, y in zip(p[0], p[1])), None]
        p[3] = tuple((x + 2 * y) // 3 for x, y in zip(p[0], p[1]))
    else:
        p += [tuple((x + y) // 2 for x, y in zip(p[0], p[1])), (0, 0, 0, 0)]
    return [p[(bits >> (2 * i)) & 3] for i in range(16)]


def reference(data: bytes, w: int, h: int, kind: str) -> bytes:
    """RGBA of `w` x `h` decoded from blocks (BC4: grey; BC5: blue 0)."""
    out, step, at = bytearray(w * h * 4), encode_bc.KINDS[kind], 0
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            block, at = data[at : at + step], at + step
            if kind == "BC1":
                px = _bc1(block, False)
            elif kind == "BC3":
                px = [(*c[:3], a) for c, a in zip(_bc1(block[8:], True), _bc4(block[:8]))]
            elif kind == "BC4":
                px = [(v, v, v, 255) for v in _bc4(block)]
            else:
                px = [(r, g, 0, 255) for r, g in zip(_bc4(block[:8]), _bc4(block[8:]))]
            for i, pixel in enumerate(px):
                x, y = bx + i % 4, by + i // 4
                if x < w and y < h:
                    out[4 * (y * w + x) : 4 * (y * w + x) + 4] = bytes(pixel)
    return bytes(out)


def dds(name: str, w: int, h: int, mips: int = 1, dxgi: int | None = None) -> bytes:
    """An original block-compressed DDS: `name` a kind (BC1...), a FourCC, or DX10 `dxgi`."""
    kind = {"ATI1": "BC4", "ATI2": "BC5"}.get(name, name)
    body = size(kind, w, h) if kind in encode_bc.KINDS else 64
    flags = 0x81007 | (0x20000 if mips > 1 else 0)
    head = struct.pack("<4sIIIIIII44x", b"DDS ", 124, flags, h, w, body, 0, mips)
    fourcc = b"DX10" if dxgi is not None else FOURCC.get(name, name.encode())
    head += struct.pack("<II4s20x", 32, 0x4, fourcc) + struct.pack("<I16x", 0x1000)
    head += struct.pack("<IIIII", dxgi, 3, 0, 1, 0) if dxgi is not None else b""
    return head + bytes(body)


def pillow(blob: bytes) -> bytes:
    return Image.open(io.BytesIO(blob)).convert("RGBA").tobytes()


def blocks(w: int, h: int):
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            yield [y * w + x for y in range(by, min(by + 4, h)) for x in range(bx, min(bx + 4, w))]


def within_range(kind: str, c: int, span: int) -> float:
    """The bound of a channel whose block spans `span`: colour range fit, or 8 levels."""
    colour = kind == "BC1" or (kind == "BC3" and c < 3)
    return span + 5 if colour else span / 14 + 1


def check(test, px: bytes, got: bytes, kind: str, shape: tuple[int, int], bound) -> None:
    """Every pixel of every block of `got` within `bound` of `px`; BC1's cut-out alpha kept."""
    test.assertEqual(len(got), len(px))
    for idx in blocks(*shape):
        for c in CHANNELS[kind]:
            values = [px[4 * i + c] for i in idx]
            for i in idx:
                if kind == "BC1" and px[4 * i + 3] < 128:
                    test.assertEqual(got[4 * i + 3], 0)  # transparent stays transparent
                    continue
                allowed = bound(kind, c, max(values) - min(values))
                test.assertLessEqual(abs(got[4 * i + c] - px[4 * i + c]), allowed, (kind, c))


class BlockTests(unittest.TestCase):
    def test_random_images_stay_within_the_formats_bound(self) -> None:
        rng = random.Random(71)
        for _ in range(60):
            w, h = rng.randint(1, 13), rng.randint(1, 13)
            px = bytearray(rng.randbytes(w * h * 4))
            if rng.random() < 0.5:  # cut-out alpha, else any
                px[3::4] = bytes(rng.choice((0, 255)) for _ in range(w * h))
            for kind in encode_bc.KINDS:
                data = compress(bytes(px), w, h, kind)
                self.assertEqual(len(data), size(kind, w, h))
                self.assertEqual(compress(bytes(px), w, h, kind), data)  # deterministic
                for got in (reference(data, w, h, kind), pillow(dds(kind, w, h)[:128] + data)):
                    check(self, bytes(px), got, kind, (w, h), within_range)

    def test_two_colour_blocks_keep_their_colours_within_the_rgb565_step(self) -> None:
        rng = random.Random(72)
        for _ in range(80):
            two = [bytes((*rng.randbytes(3), 255)) for _ in "ab"]
            px = b"".join(rng.choice(two) for _ in range(16))
            for kind in ("BC1", "BC3"):
                data = compress(px, 4, 4, kind)
                for got in (reference(data, 4, 4, kind), pillow(dds(kind, 4, 4)[:128] + data)):
                    check(self, px, got, kind, (4, 4), lambda *_: 5)

    def test_flat_blocks_are_exact_where_the_format_holds_the_colour(self) -> None:
        rng = random.Random(73)
        for n in range(300):
            held = n % 2 == 0  # a colour an RGB565 endpoint shows as ffmpeg expands it
            r, g, b = (rng.choice(E5), rng.choice(E6), rng.choice(E5)) if held else rng.randbytes(3)
            a = rng.randrange(256)
            px = bytes((r, g, b, a)) * 16
            for kind in encode_bc.KINDS:
                data = compress(px, 4, 4, kind)
                got = reference(data, 4, 4, kind)
                for c in CHANNELS[kind]:
                    if kind == "BC1" and a < 128:
                        self.assertEqual(got[3::4], bytes(16))
                        continue
                    exact = c == 3 or kind in ("BC4", "BC5") or held
                    self.assertLessEqual(abs(got[c] - px[c]), 0 if exact else 1, (kind, c))
                    self.assertTrue(all(got[c::4][0] == v for v in got[c::4]))  # still flat
                theirs = pillow(dds(kind, 4, 4)[:128] + data)
                for c in CHANNELS[kind] if kind != "BC1" or a >= 128 else ():
                    self.assertLessEqual(abs(theirs[c] - px[c]), 1, (kind, c))

    def test_alpha_is_exact_at_0_and_255(self) -> None:
        rng = random.Random(74)
        for _ in range(60):
            px = bytearray(rng.randbytes(64))
            px[3::4] = bytes(rng.choice((0, 255, rng.randrange(256))) for _ in range(16))
            for kind, c in (("BC1", 3), ("BC3", 3), ("BC4", 0), ("BC5", 1)):
                if kind in ("BC4", "BC5"):
                    px[c::4] = bytes(rng.choice((0, 255, rng.randrange(256))) for _ in range(16))
                got = reference(compress(bytes(px), 4, 4, kind), 4, 4, kind)
                for i in range(16):
                    want = px[4 * i + c]
                    if kind == "BC1":
                        self.assertEqual(got[4 * i + 3], 0 if want < 128 else 255)
                    elif want in (0, 255):
                        self.assertEqual(got[4 * i + c], want, kind)

    def test_an_unknown_kind_is_named(self) -> None:
        with self.assertRaisesRegex(ValueError, "BC7 is not a block format"):
            compress(bytes(64), 4, 4, "BC7")


class DdsBlockTests(unittest.TestCase):
    def test_written_back_in_the_originals_format_with_its_header_and_mips(self) -> None:
        rng = random.Random(75)
        cases = [(k, None) for k in ("BC1", "BC3", "BC4", "BC5", "ATI1", "ATI2")]
        cases += [("BC1", 71), ("BC1", 72), ("BC3", 77), ("BC4", 80), ("BC5", 83), ("BC5", 82)]
        for name, dxgi in cases * 3:
            kind = {"ATI1": "BC4", "ATI2": "BC5"}.get(name, name)
            mips = rng.choice([1, 3, 6])
            original = dds(name if dxgi is None else kind, 16, 8, mips, dxgi)
            w, h = rng.randint(1, 40), rng.randint(1, 40)
            edit = Image.frombytes("RGBA", (w, h), rng.randbytes(w * h * 4))
            blob = write_dds(png_of(edit), original)
            hsize = 148 if dxgi is not None else 128
            count = 1 if mips == 1 else min(mips, max(w, h).bit_length())
            sizes = [size(kind, max(1, w >> n), max(1, h >> n)) for n in range(count)]
            self.assertEqual(len(blob), hsize + sum(sizes))
            flags, hh, ww, pitch = struct.unpack_from("<IIII", blob, 8)
            self.assertEqual(
                (hh, ww, pitch, struct.unpack_from("<I", blob, 28)[0]), (h, w, sizes[0], count)
            )
            self.assertEqual(flags & 0x80008, 0x80000)  # linear size, not pitch
            unchanged = lambda b: b[:8] + b[24:28] + b[32:hsize]  # noqa: E731
            self.assertEqual(unchanged(blob), unchanged(original))  # the original's header
            pixels = edit.tobytes()
            if name == "ATI2":  # ffmpeg shows ATI2 with red and green swapped: kept that way
                turned = bytearray(pixels)
                turned[0::4], turned[1::4] = pixels[1::4], pixels[0::4]
                pixels = bytes(turned)
            got = reference(blob[hsize : hsize + sizes[0]], w, h, kind)
            check(self, pixels, got, kind, (w, h), within_range)
            self.assertEqual(layout(blob)[3], kind)  # it reads back as the same format

    def test_what_has_no_encoder_says_why(self) -> None:
        png = png_of(Image.new("RGBA", (4, 4)))
        for original, why in (
            (dds("DXT3", 4, 4), "DXT3 \\(BC2\\) is block-compressed in a form ViWo has no"),
            (dds("DXT4", 4, 4), "premultiplied"),
            (dds("BC5S", 4, 4), "signed BC5"),
            (dds("BC7", 4, 4, dxgi=98), "BC7"),
            (dds("BC6H", 4, 4, dxgi=95), "BC6H"),
            (dds("BC4", 4, 4, dxgi=81), "signed BC4"),
            (dds("RXGB", 4, 4), "not a pixel format ViWo writes back"),
            (dds("BC1", 4, 4)[:112] + struct.pack("<I", 0x200) + dds("BC1", 4, 4)[116:], "cube"),
        ):
            with self.assertRaisesRegex(ValueError, why):
                write_dds(png, original)


if __name__ == "__main__":
    unittest.main()
