"""L3: XNA/FNA/MonoGame content (decode.xnb), property tests on XNB files written here byte by
byte (format version 5, uncompressed or LZ4 as MonoGame writes it, readers named in full, the
primary object behind its 7-bit index, shared resources after it). Texture2D in Color, Bgr565,
Bgra5551, Bgra4444 and Alpha8 decodes to the stored pixels and an edited PNG comes back exactly
(16-bit channels through their expansion and its inverse), every level rebuilt when it had mips;
DXT1/3/5 decode as ViWo's block decoders show them and come back in their block format; a
SoundEffect becomes a WAV with its format chunk and comes back with its loop kept when it fits;
an unchanged texture or sound is written back byte for byte. LZX, XNA 3.x files, other content
and other surface formats are refused by name; end to end, an edited PNG of a loose XNB becomes
the XNB in the patched copy."""

from __future__ import annotations

import io
import random
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lz4.block
from PIL import Image

from tests.helpers import runtime
from tests.test_roundtrip_encode import decoded, workspace
from viwo.backends.blocks.decode_bc import decompress
from viwo.backends.blocks.encode_bc import compress
from viwo.contracts.types import OutcomeKind
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.roundtrip import repack
from viwo.plugins.xna import XnaPlugin, XnbDecoder
from viwo.plugins.xna.content import texture

TEX = (
    "Microsoft.Xna.Framework.Content.Texture2DReader, Microsoft.Xna.Framework.Graphics, "
    "Version=4.0.0.0, Culture=neutral, PublicKeyToken=842cf8be1de50553"
)
SFX = "Microsoft.Xna.Framework.Content.SoundEffectReader"
FONT = "Microsoft.Xna.Framework.Content.SpriteFontReader"
BYTES = {0: 4, 1: 2, 2: 2, 3: 2, 12: 1}
BLOCK = {4: "BC1", 5: "BC2", 6: "BC3"}


def seven(n: int) -> bytes:
    out = bytearray()
    while True:
        out.append(n & 0x7F | (0x80 if n > 0x7F else 0))
        n >>= 7
        if not n:
            return bytes(out)


def xnb(readers: list[str], index: int, content: bytes, packed: bool, tail: bytes = b"") -> bytes:
    body = seven(len(readers))
    for name in readers:
        body += seven(len(name.encode())) + name.encode() + struct.pack("<i", 0)
    body += seven(0) + seven(index) + content + tail
    if packed:
        body = struct.pack("<I", len(body)) + lz4.block.compress(body, store_size=False)
    flags = 0x41 if packed else 0x01
    return b"XNBw\x05" + bytes([flags]) + struct.pack("<I", 10 + len(body)) + body


def tex_content(fmt: int, w: int, h: int, levels: list[bytes]) -> bytes:
    out = struct.pack("<iIII", fmt, w, h, len(levels))
    return out + b"".join(struct.pack("<I", len(d)) + d for d in levels)


def random_level(rng: random.Random, fmt: int, w: int, h: int) -> bytes:
    if fmt in BLOCK:
        rgba = rng.randbytes(4 * w * h)
        return compress(rgba, w, h, BLOCK[fmt])
    return rng.randbytes(BYTES[fmt] * w * h)


def expand(fmt: int, raw: bytes, w: int, h: int) -> bytes:
    """What a 16-bit, Alpha8 or Color level shows, worked out here channel by channel."""
    if fmt == 0:
        return raw
    if fmt == 12:
        return b"".join(b"\xff\xff\xff" + bytes([a]) for a in raw)
    specs = {
        1: ((11, 5), (5, 6), (0, 5), None),
        2: ((10, 5), (5, 5), (0, 5), (15, 1)),
        3: ((8, 4), (4, 4), (0, 4), (12, 4)),
    }[fmt]
    out = bytearray()
    for (v,) in struct.iter_unpack("<H", raw):
        for spec in specs:
            top = (1 << spec[1]) - 1 if spec else 0
            out.append(255 if spec is None else round((v >> spec[0] & top) * 255 / top))
    return bytes(out)


def png_of(rgba: bytes, size: tuple[int, int]) -> bytes:
    out = io.BytesIO()
    Image.frombytes("RGBA", size, rgba).save(out, "PNG")
    return out.getvalue()


def sound_content(rng: random.Random) -> tuple[bytes, bytes, bytes]:
    channels, rate = rng.choice((1, 2)), rng.choice((22050, 44100))
    fmt = struct.pack("<HHIIHHH", 1, channels, rate, rate * 2 * channels, 2 * channels, 16, 0)
    data = rng.randbytes(2 * channels * rng.randint(1, 400))
    loop = struct.pack("<iii", 0, len(data) // (2 * channels), 7)
    return fmt, data, struct.pack("<I", len(fmt)) + fmt + struct.pack("<I", len(data)) + data + loop


def run(path: Path, out: Path):
    out.mkdir(exist_ok=True)
    return XnbDecoder().decode(path, out, None)


def quantized(fmt: int, rgba: bytes) -> bytes:
    """What a format keeps of RGBA pixels."""
    if fmt == 0:
        return rgba
    if fmt == 12:
        return expand(12, rgba[3::4], 0, 0)
    specs = {1: (5, 6, 5, None), 2: (5, 5, 5, 1), 3: (4, 4, 4, 4)}[fmt]
    out = bytearray(rgba)
    for c, bits in enumerate(specs):
        top = (1 << bits) - 1 if bits else 0
        out[c::4] = bytes(
            255 if not bits else round(round(e * top / 255) * 255 / top) for e in rgba[c::4]
        )
    return bytes(out)


class XnbTests(unittest.TestCase):
    def test_textures_decode_to_their_pixels_and_come_back(self) -> None:
        rng = random.Random(71)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(48):
                fmt = (0, 1, 2, 3, 12, 4, 5, 6)[case % 8]
                w, h = rng.randint(1, 13), rng.randint(1, 13)
                mips = rng.random() < 0.4
                count = max(w, h).bit_length() if mips else 1
                levels = [
                    random_level(rng, fmt, max(1, w >> n), max(1, h >> n)) for n in range(count)
                ]
                packed, tail = rng.random() < 0.4, rng.randbytes(rng.randint(0, 9))
                blob = xnb([TEX], 1, tex_content(fmt, w, h, levels), packed, tail)
                path = root / f"t{case}.xnb"
                path.write_bytes(blob)
                self.assertEqual(run(path, root / f"o{case}").kind, OutcomeKind.OK)
                shown = Image.open(root / f"o{case}" / f"t{case}.png").convert("RGBA").tobytes()
                block = BLOCK.get(fmt)
                want = decompress(levels[0], w, h, block) if block else expand(fmt, levels[0], w, h)
                self.assertEqual(shown, want, (case, fmt))
                same = root / f"same{case}.xnb"
                XnbDecoder().encode(root / f"o{case}" / f"t{case}.png", path, same, None)
                if not block and not packed and not mips:
                    self.assertEqual(same.read_bytes(), blob)  # unchanged: byte for byte
                size = (rng.randint(1, 17), rng.randint(1, 17))
                edit = rng.randbytes(4 * size[0] * size[1])
                (root / "edit.png").write_bytes(png_of(edit, size))
                done = XnbDecoder().encode(root / "edit.png", path, root / "back.xnb", None)
                self.assertEqual(done.kind, OutcomeKind.OK, done.error)
                back = root / "back.xnb"
                self.assertEqual(run(back, root / f"b{case}").kind, OutcomeKind.OK)
                again = Image.open(root / f"b{case}" / "back.png").convert("RGBA").tobytes()
                if not block:
                    self.assertEqual(again, quantized(fmt, edit))
                from viwo.plugins.xna.xnb import read_xnb

                parsed = read_xnb(back.read_bytes(), lz4)
                got = texture(parsed.body, parsed.start)
                self.assertEqual((got[0], got[1], got[2]), (fmt, *size))
                self.assertEqual(len(got[3]), max(size).bit_length() if mips else 1)
                self.assertEqual(parsed.body[got[4] :], tail)  # what follows is kept

    def test_an_lzx_texture_decodes_and_comes_back_uncompressed(self) -> None:
        from tests.test_lzx import encode as lzx_encode
        from tests.test_lzx import wrap as lzx_wrap

        rng = random.Random(81)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            level = rng.randbytes(64)
            plain = xnb([TEX], 1, tex_content(0, 4, 4, [level]), False)[10:]  # the body, plain
            frames = lzx_wrap(lzx_encode([("lit", b) for b in plain]))
            blob = b"XNBw\x05\x80" + struct.pack("<II", 14 + len(frames), len(plain)) + frames
            path = root / "t.xnb"
            path.write_bytes(blob)
            self.assertEqual(run(path, root / "o").kind, OutcomeKind.OK)
            self.assertEqual(Image.open(root / "o" / "t.png").convert("RGBA").tobytes(), level)
            edit = rng.randbytes(64)
            (root / "e.png").write_bytes(png_of(edit, (4, 4)))
            out = XnbDecoder().encode(root / "e.png", path, root / "back.xnb", None)
            self.assertEqual(out.kind, OutcomeKind.OK)
            self.assertIn("LZX", out.notes[0])
            back = (root / "back.xnb").read_bytes()
            self.assertEqual(back[5] & 0x80, 0)  # the LZX flag cleared: written uncompressed
            self.assertEqual(run(root / "back.xnb", root / "b").kind, OutcomeKind.OK)
            self.assertEqual(Image.open(root / "b" / "back.png").convert("RGBA").tobytes(), edit)

    def test_sounds_become_wav_and_come_back_with_their_loop(self) -> None:
        rng = random.Random(72)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(20):
                fmt, data, content = sound_content(rng)
                path = root / f"s{case}.xnb"
                path.write_bytes(xnb([SFX], 1, content, case % 2 == 1))
                self.assertEqual(run(path, root / f"o{case}").kind, OutcomeKind.OK)
                wav = (root / f"o{case}" / f"s{case}.wav").read_bytes()
                self.assertEqual((wav[:4], wav[8:12]), (b"RIFF", b"WAVE"))
                done = XnbDecoder().encode(
                    root / f"o{case}" / f"s{case}.wav", path, root / "same.xnb", None
                )
                self.assertEqual(done.kind, OutcomeKind.OK)
                if case % 2 == 0:
                    self.assertEqual((root / "same.xnb").read_bytes(), path.read_bytes())
                align = struct.unpack_from("<H", fmt, 12)[0]
                longer = data + rng.randbytes(align * rng.randint(1, 50))
                edited = (
                    wav[: wav.index(b"data")] + b"data" + struct.pack("<I", len(longer)) + longer
                )
                edited = edited[:4] + struct.pack("<I", len(edited) - 8) + edited[8:]
                (root / "edit.wav").write_bytes(edited)
                XnbDecoder().encode(root / "edit.wav", path, root / "back.xnb", None)
                from viwo.plugins.xna.xnb import read_xnb

                parsed = read_xnb((root / "back.xnb").read_bytes(), lz4)
                start, length, ms = struct.unpack_from("<iii", parsed.body, len(parsed.body) - 12)
                rate = struct.unpack_from("<I", fmt, 4)[0]
                self.assertEqual((start, length), (0, len(data) // align))  # still fits: kept
                self.assertEqual(ms, len(longer) // align * 1000 // rate)
                self.assertIn(longer, parsed.body)

    def test_what_cannot_be_read_is_refused_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = {
                "old": (b"XNBw\x04\x00" + struct.pack("<I", 12) + bytes(2), "version 4"),
                "font": (xnb([FONT], 1, b"\0" * 8, False), "SpriteFontReader"),
                "single": (xnb([TEX], 1, tex_content(13, 1, 1, [bytes(4)]), False), "Single"),
                "junk": (b"not an xnb at all", "not an XNB"),
            }
            for name, (blob, why) in cases.items():
                path = root / f"{name}.xnb"
                path.write_bytes(blob)
                self.assertIn(why, XnbDecoder().refuses(path))
                self.assertIn(why, run(path, root / name).error)
            with mock.patch("viwo.plugins.xna._lz4", lambda: None):
                path = root / "lz4.xnb"
                path.write_bytes(xnb([TEX], 1, tex_content(0, 1, 1, [bytes(4)]), True))
                self.assertIn("'lz4'", XnbDecoder().refuses(path))
            rng = random.Random(73)
            for _ in range(300):
                blob = bytearray(
                    xnb([TEX], 1, tex_content(1, 3, 3, [rng.randbytes(18)]), rng.random() < 0.5)
                )
                blob[rng.randrange(len(blob))] ^= 1 << rng.randrange(8)
                (root / "d.xnb").write_bytes(bytes(blob))
                run(root / "d.xnb", root / "d")  # an outcome, never a crash

    def test_detection_and_an_edited_png_end_to_end(self) -> None:
        rng = random.Random(74)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "g"
            (game / "Content").mkdir(parents=True)
            original = xnb([TEX], 1, tex_content(0, 4, 4, [rng.randbytes(64)]), False)
            (game / "Content" / "logo.xnb").write_bytes(original)
            (game / "FNA.dll").write_bytes(b"MZ")
            self.assertEqual(XnaPlugin().detect(FolderProbe(game)).confidence, 0.9)
            (root / "o").mkdir()
            XnbDecoder().decode(game / "Content" / "logo.xnb", root / "o", None)
            loose = {"kind": "loose", "member": "Content/logo.xnb"}
            work = workspace(
                root,
                game,
                {
                    "xnb/logo.xnb": (original, loose),
                    "png/logo.png": (
                        (root / "o" / "logo.png").read_bytes(),
                        decoded("xnb/logo.xnb", "logo.png", "xnb-builtin"),
                    ),
                },
            )
            edit = rng.randbytes(4 * 6 * 2)
            (work / "png" / "logo.png").write_bytes(png_of(edit, (6, 2)))
            report = repack(runtime(root), work, root / "copy")
            self.assertTrue(report["verified"], report)
            self.assertEqual(report["plan"][0]["ways"][0]["encoder"], "decode.xnb")
            run(root / "copy" / "Content" / "logo.xnb", root / "back")
            self.assertEqual(Image.open(root / "back" / "logo.png").convert("RGBA").tobytes(), edit)
            self.assertEqual((game / "Content" / "logo.xnb").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
