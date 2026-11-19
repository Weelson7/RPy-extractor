"""L3: ViWo's block encoders (doc 18.3, the way back of a block-compressed DDS), property tests.
For random images, BC1/BC2/BC3/BC4/BC5/BC7 and BC6H (unsigned and signed) blocks decoded again,
by ViWo's own decoders (the expansion ffmpeg uses; BC7 per the specification), by a BC6H mode 11
decoder written here per the specification and by Pillow, stay within the format's bound: a
colour channel within its block's range plus the endpoint step (RGB565: 5; BC7's p-bit: 1;
BC6H's 10-bit endpoints in 8 bits: 2, signed 4), a single channel within (max - min) / 14 plus
rounding, BC2's alpha within 8; a block of two colours within the endpoint step; a flat block
within 1 for any colour and exact where an endpoint holds it; alpha exact at 0 and 255 (BC1:
transparent or not; BC7: a block all opaque or all clear stays so). The same pixels give the
same bytes. Written back as a DDS, the original's header is kept (DX10 too) with the new size,
the mip chain rebuilt; ATI2 keeps its decoder's channel order; premultiplied, signed BC4/BC5,
typeless BC6H and cube maps are refused by name. The DDS backends: BC6H and BC7 go to the
Pillow spare without starting ffmpeg, BC6H's clamp and loss are said."""

from __future__ import annotations

import io
import random
import struct
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tests.test_encoders import png_of
from viwo.backends.blocks import encode_bc
from viwo.backends.blocks.decode_bc import decompress
from viwo.backends.blocks.encode_bc import E5, E6, compress, size
from viwo.backends.blocks.encode_bptc import CLAMPED, HDR, WEIGHTS, finish, unquantize
from viwo.contracts.types import OutcomeKind
from viwo.core.decode import FfmpegImage
from viwo.core.decode_dds import PillowImage
from viwo.core.encode_dds import layout, write_dds

FOURCC = {"BC1": b"DXT1", "BC2": b"DXT3", "BC3": b"DXT5", "BC4": b"BC4U", "BC5": b"BC5U"}
DXGI = {"BC6H": 95, "BC6HS": 96, "BC7": 98}
ALIAS = {"ATI1": "BC4", "ATI2": "BC5", "DXT3": "BC2"}
RGBA = (0, 1, 2, 3)
CHANNELS = {"BC1": (0, 1, 2), "BC2": RGBA, "BC3": RGBA, "BC4": (0,), "BC5": (0, 1), "BC7": RGBA}
CHANNELS |= {"BC6H": (0, 1, 2), "BC6HS": (0, 1, 2)}
STEP = {"BC1": 5, "BC2": 5, "BC3": 5, "BC7": 1, "BC6H": 2, "BC6HS": 4}  # endpoint step, 8 bits


def _bc6h(block: bytes, signed: bool) -> list[tuple]:
    """A BC6H mode 11 block per the specification, shown in 8 bits as Pillow shows it."""
    bits = int.from_bytes(block, "little")
    assert bits & 31 == 3, "not mode 11"
    raw = [(bits >> (5 + 10 * k)) & 1023 for k in range(6)]
    ends = [unquantize(e - (1024 if signed and e > 511 else 0), signed) for e in raw]
    idx, at = [], 65
    for i in range(16):
        idx.append((bits >> at) & (7 if i == 0 else 15))
        at += 3 if i == 0 else 4
    out = []
    for k in idx:
        w = WEIGHTS[k]
        mix = [((64 - w) * ends[c] + w * ends[c + 3] + 32) >> 6 for c in range(3)]
        half = [struct.unpack("<e", struct.pack("<H", finish(x, signed)))[0] for x in mix]
        out.append(tuple(max(0, min(255, int(f * 255))) for f in half) + (255,))
    return out


def reference(data: bytes, w: int, h: int, kind: str) -> bytes:
    """RGBA of `w` x `h` decoded from blocks (BC4: grey; BC5: blue 0; BC6H: opaque)."""
    if not kind.startswith("BC6"):
        return decompress(data, w, h, kind)
    out, at = bytearray(w * h * 4), 0
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            px, at = _bc6h(data[at : at + 16], kind == "BC6HS"), at + 16
            for i, pixel in enumerate(px):
                x, y = bx + i % 4, by + i // 4
                if x < w and y < h:
                    out[4 * (y * w + x) : 4 * (y * w + x) + 4] = bytes(pixel)
    return bytes(out)


def dds(name: str, w: int, h: int, mips: int = 1, dxgi: int | None = None) -> bytes:
    """An original block-compressed DDS: `name` a kind (BC1...), a FourCC, or DX10 `dxgi`."""
    kind = ALIAS.get(name, name)
    body = size(kind, w, h) if kind in encode_bc.KINDS else 64
    flags = 0x81007 | (0x20000 if mips > 1 else 0)
    head = struct.pack("<4sIIIIIII44x", b"DDS ", 124, flags, h, w, body, 0, mips)
    fourcc = b"DX10" if dxgi is not None else FOURCC.get(name, name.encode())
    head += struct.pack("<II4s20x", 32, 0x4, fourcc) + struct.pack("<I16x", 0x1000)
    head += struct.pack("<IIIII", dxgi, 3, 0, 1, 0) if dxgi is not None else b""
    return head + bytes(body)


def pillow(kind: str, data: bytes, w: int, h: int) -> bytes:
    """What Pillow shows of `kind` blocks (a FourCC DDS, DX10 for BC6H and BC7)."""
    head = dds(kind, w, h, dxgi=DXGI.get(kind))[: 148 if kind in DXGI else 128]
    return Image.open(io.BytesIO(head + data)).convert("RGBA").tobytes()


def blocks(w: int, h: int):
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            yield [y * w + x for y in range(by, min(by + 4, h)) for x in range(bx, min(bx + 4, w))]


def within_range(kind: str, c: int, span: int) -> float:
    """The bound of a channel whose block spans `span`: a line through the box, or levels."""
    if kind == "BC2" and c == 3:
        return 8
    if kind in STEP and (c < 3 or kind == "BC7"):
        return span + STEP[kind]
    return span / 14 + 1


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


def decoded(kind: str, px: bytes, w: int, h: int) -> tuple[bytes, bytes]:
    data = compress(px, w, h, kind)
    return reference(data, w, h, kind), pillow(kind, data, w, h)


class BlockTests(unittest.TestCase):
    def test_random_images_stay_within_the_formats_bound(self) -> None:
        rng = random.Random(71)
        for _ in range(40):
            w, h = rng.randint(1, 13), rng.randint(1, 13)
            px = bytearray(rng.randbytes(w * h * 4))
            if rng.random() < 0.5:  # cut-out alpha, else any
                px[3::4] = bytes(rng.choice((0, 255)) for _ in range(w * h))
            for kind in encode_bc.KINDS:
                data = compress(bytes(px), w, h, kind)
                self.assertEqual(len(data), size(kind, w, h))
                self.assertEqual(compress(bytes(px), w, h, kind), data)  # deterministic
                for got in (reference(data, w, h, kind), pillow(kind, data, w, h)):
                    check(self, bytes(px), got, kind, (w, h), within_range)

    def test_two_colour_blocks_keep_their_colours_within_the_endpoint_step(self) -> None:
        rng = random.Random(72)
        for _ in range(80):
            two = [bytes((*rng.randbytes(3), 255)) for _ in "ab"]
            px = b"".join(rng.choice(two) for _ in range(16))
            for kind, step in STEP.items():
                for got in decoded(kind, px, 4, 4):
                    check(self, px, got, kind, (4, 4), lambda *_: step)  # noqa: B023

    def test_flat_blocks_are_exact_where_the_format_holds_the_colour(self) -> None:
        rng = random.Random(73)
        for n in range(300):
            held = n % 2 == 0  # a colour an RGB565 endpoint shows as ffmpeg expands it
            r, g, b = (rng.choice(E5), rng.choice(E6), rng.choice(E5)) if held else rng.randbytes(3)
            a = rng.randrange(256)
            px = bytes((r, g, b, a)) * 16
            for kind in ("BC1", "BC2", "BC3", "BC4", "BC5"):
                got = reference(compress(px, 4, 4, kind), 4, 4, kind)
                for c in CHANNELS[kind]:
                    if kind == "BC1" and a < 128:
                        self.assertEqual(got[3::4], bytes(16))
                        continue
                    exact = c == 3 or kind in ("BC4", "BC5") or held
                    allowed = 8 if (kind, c) == ("BC2", 3) else 0 if exact else 1
                    self.assertLessEqual(abs(got[c] - px[c]), allowed, (kind, c))
                    self.assertTrue(all(got[c::4][0] == v for v in got[c::4]))  # still flat
                theirs = pillow(kind, compress(px, 4, 4, kind), 4, 4)
                for c in CHANNELS[kind] if kind != "BC1" or a >= 128 else ():
                    allowed = 8 if (kind, c) == ("BC2", 3) else 1
                    self.assertLessEqual(abs(theirs[c] - px[c]), allowed, (kind, c))

    def test_flat_blocks_in_bc7_and_bc6h_stay_flat_within_the_endpoint_step(self) -> None:
        rng = random.Random(76)
        for _ in range(200):
            px = rng.randbytes(4) * 16
            even = len({v % 2 for v in px[:4]}) == 1  # one p-bit holds every channel
            for kind in ("BC7", "BC6H", "BC6HS"):
                for got in decoded(kind, px, 4, 4):
                    for c in CHANNELS[kind]:
                        allowed = 0 if kind == "BC7" and even else STEP[kind]
                        self.assertLessEqual(abs(got[c] - px[c]), allowed, (kind, c))
                        self.assertEqual(len(set(got[c::4])), 1)

    def test_alpha_is_exact_at_0_and_255(self) -> None:
        rng = random.Random(74)
        for _ in range(60):
            px = bytearray(rng.randbytes(64))
            px[3::4] = bytes(rng.choice((0, 255, rng.randrange(256))) for _ in range(16))
            for kind, c in (("BC1", 3), ("BC2", 3), ("BC3", 3), ("BC4", 0), ("BC5", 1)):
                if kind in ("BC4", "BC5"):
                    px[c::4] = bytes(rng.choice((0, 255, rng.randrange(256))) for _ in range(16))
                got = reference(compress(bytes(px), 4, 4, kind), 4, 4, kind)
                for i in range(16):
                    want = px[4 * i + c]
                    if kind == "BC1":
                        self.assertEqual(got[4 * i + 3], 0 if want < 128 else 255)
                    elif want in (0, 255):
                        self.assertEqual(got[4 * i + c], want, kind)
            for alpha in (0, 255):  # BC7: a block all opaque or all clear stays so
                px[3::4] = bytes((alpha,)) * 16
                for got in decoded("BC7", bytes(px), 4, 4):
                    self.assertEqual(got[3::4], bytes((alpha,)) * 16)

    def test_an_unknown_kind_is_named(self) -> None:
        with self.assertRaisesRegex(ValueError, "BC9 is not a block format"):
            compress(bytes(64), 4, 4, "BC9")


class DdsBlockTests(unittest.TestCase):
    def test_written_back_in_the_originals_format_with_its_header_and_mips(self) -> None:
        rng = random.Random(75)
        cases = [(k, None) for k in ("BC1", "BC2", "BC3", "BC4", "BC5", "ATI1", "ATI2", "DXT3")]
        cases += [("BC1", 71), ("BC1", 72), ("BC2", 74), ("BC2", 75), ("BC3", 77), ("BC4", 80)]
        cases += [("BC5", 83), ("BC5", 82), ("BC6H", 95), ("BC6HS", 96)]
        cases += [("BC7", 97), ("BC7", 98), ("BC7", 99)]
        for name, dxgi in cases * 2:
            kind = ALIAS.get(name, name)
            mips = rng.choice([1, 3, 6])
            original = dds(name if dxgi is None else kind, 16, 8, mips, dxgi)
            w, h = rng.randint(1, 30), rng.randint(1, 30)
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
                plain = write_dds(png_of(edit), original, ati2_green=False)  # Pillow's view
                got = reference(plain[hsize : hsize + sizes[0]], w, h, kind)
                check(self, edit.tobytes(), got, kind, (w, h), within_range)
            got = reference(blob[hsize : hsize + sizes[0]], w, h, kind)
            check(self, pixels, got, kind, (w, h), within_range)
            self.assertEqual(layout(blob)[3], kind)  # it reads back as the same format

    def test_what_has_no_encoder_says_why(self) -> None:
        png = png_of(Image.new("RGBA", (4, 4)))
        for original, why in (
            (dds("DXT2", 4, 4), "DXT2 \\(premultiplied BC2\\) is block-compressed in a form"),
            (dds("DXT4", 4, 4), "premultiplied"),
            (dds("BC5S", 4, 4), "signed BC5"),
            (dds("BC6H", 4, 4, dxgi=94), "typeless BC6H"),
            (dds("BC4", 4, 4, dxgi=81), "signed BC4"),
            (dds("BC4", 4, 4, dxgi=2), "DXGI format 2 is not a pixel format"),
            (dds("RXGB", 4, 4), "not a pixel format ViWo writes back"),
            (dds("BC1", 4, 4)[:112] + struct.pack("<I", 0x200) + dds("BC1", 4, 4)[116:], "cube"),
        ):
            with self.assertRaisesRegex(ValueError, why):
                write_dds(png, original)


class DdsBackendTests(unittest.TestCase):
    def test_bptc_goes_to_the_pillow_spare_and_its_losses_are_said(self) -> None:
        rng = random.Random(77)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            edit = Image.frombytes("RGBA", (8, 4), rng.randbytes(128))
            (root / "e.png").write_bytes(png_of(edit))
            for kind in ("BC7", "BC6H", "BC6HS"):
                (root / "t.dds").write_bytes(
                    write_dds(png_of(edit), dds(kind, 8, 4, 1, DXGI[kind]))
                )
                main = FfmpegImage().decode(root / "t.dds", root, None)  # no process started
                self.assertEqual(main.kind, OutcomeKind.FAILED)
                self.assertIn(f"does not read {kind[:4]}", main.error)
                out = root / kind
                out.mkdir()
                spare = PillowImage().decode(root / "t.dds", out, None)
                self.assertTrue(spare.ok, spare.error)
                shown = Image.open(out / "t.dds.png").convert("RGBA").tobytes()
                self.assertEqual(shown, pillow(kind, (root / "t.dds").read_bytes()[148:], 8, 4))
                self.assertEqual(spare.notes, (CLAMPED,) if kind != "BC7" else ())
                back = PillowImage().encode(root / "e.png", root / "t.dds", root / "o.dds", None)
                self.assertEqual(back.notes, (HDR,) if kind != "BC7" else ())
                self.assertEqual(layout((root / "o.dds").read_bytes())[3], kind)
            (root / "bad.dds").write_bytes(b"DDS " + bytes(10))
            self.assertIn("bad.dds", PillowImage().decode(root / "bad.dds", root, None).error)
            (root / "t.dds").write_bytes(dds("BC6H", 4, 4, dxgi=94))
            self.assertIn("typeless BC6H", PillowImage().refuses(root / "t.dds"))
            self.assertEqual(PillowImage().refuses(root / "o.dds"), "")
            failed = PillowImage().encode(root / "t.dds", root / "t.dds", root / "x.dds", None)
            self.assertIn("t.dds", failed.error)


if __name__ == "__main__":
    unittest.main()
