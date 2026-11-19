"""L3: the way back of the decoders (doc 18.3), property tests. For random images and tables:
VTF and DDS (uncompressed) written back decode to exactly the PNG's pixels and keep the
original's header facts; an SLP sheet written back decodes to the sheet (palette colours,
player colours, shadows, transparency), and so does a decoded random SLP written back; a Total
War table decoded and written back is byte for byte the original, and an edit lands with the
original's flags and order; an edited `.rpy` is the member that replaces its `.rpyc`. What has
no way back says why (audio, video, a block-compressed DDS, an animated VTF)."""

from __future__ import annotations

import io
import json
import random
import struct
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tests.test_slp import COLORS, PAL
from tests.test_slp import encode as random_slp
from tests.test_vtf import vtf
from viwo.contracts.types import OutcomeKind
from viwo.core import decode
from viwo.core.encode_dds import write_dds
from viwo.plugins.genie.slp import PLAYER, SHADOW, SlpDecoder, frames, sheet
from viwo.plugins.genie.slp_write import write_slp
from viwo.plugins.renpy.decompile import UnrpycCli
from viwo.plugins.source.vtf import RAW, VtfDecoder, _size, header, to_png
from viwo.plugins.source.vtf_write import write_vtf
from viwo.plugins.warscape.loc import LocBuiltin, read_entries, read_loc, write_loc


def png_of(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def noise(rng, size: tuple[int, int], alpha: bool = True) -> Image.Image:
    data = bytearray(rng.randbytes(size[0] * size[1] * 4))
    if not alpha:
        data[3::4] = b"\xff" * (size[0] * size[1])
    return Image.frombytes("RGBA", size, bytes(data))


class VtfBackTests(unittest.TestCase):
    def test_a_png_written_back_decodes_to_its_pixels_in_the_originals_shape(self) -> None:
        rng = random.Random(31)
        for _ in range(40):
            fmt = rng.choice([0, 1, 2, 3, 11, 12, 13, 15, 16])
            w0, h0 = rng.choice([4, 8, 16]), rng.choice([4, 8, 32])
            mips, minor = rng.randint(1, min(w0, h0).bit_length()), rng.randint(0, 5)
            original = vtf(rng, fmt, (w0, h0), mips, minor, 1, rng.randbytes(_size(fmt, w0, h0)))
            size = rng.choice([(w0, h0), (rng.randint(1, 40), rng.randint(1, 40))])
            alpha = RAW.get(fmt, (4, "RGBA"))[1] in ("RGBA",) or fmt not in RAW
            edit = noise(rng, size, alpha)
            blob = write_vtf(png_of(edit), original)
            info = header(blob)
            self.assertEqual((info["width"], info["height"]), size)
            self.assertEqual(info["format"], fmt if fmt in RAW else 12)  # BGRA8888 for DXT
            self.assertEqual(info["mips"] > 1, mips > 1)
            got = Image.open(io.BytesIO(to_png(blob)))
            mode = RAW[info["format"]][1]
            self.assertEqual(got.convert(mode).tobytes(), edit.convert(mode).tobytes(), fmt)
            again = write_vtf(to_png(blob), blob)  # encode(decode(x)) shows x's pixels again
            self.assertEqual(to_png(again), to_png(blob))

    def test_an_animated_or_cube_texture_is_refused_by_name(self) -> None:
        rng = random.Random(32)
        png = png_of(noise(rng, (8, 8)))
        for count, env in ((3, False), (1, True)):
            original = vtf(rng, 12, (8, 8), 1, 4, count, rng.randbytes(256), env)
            with self.assertRaisesRegex(ValueError, "only single images"):
                write_vtf(png, original)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.png").write_bytes(png)
            (root / "a.vtf").write_bytes(vtf(rng, 12, (8, 8), 1, 4, 3, rng.randbytes(256)))
            out = VtfDecoder().encode(root / "a.png", root / "a.vtf", root / "o.vtf", None)
            self.assertEqual(out.kind, OutcomeKind.FAILED)
            self.assertIn("a.png", out.error)


def dds(fmt: str, size: tuple[int, int], mips: int = 1, caps2: int = 0) -> bytes:
    """An original DDS: `fmt` is a byte order (BGRA, RGBA, BGRX, BGR, L), DXT1, or DX10:<n>."""
    w, h = size
    flags = 0x1007 | (0x20000 if mips > 1 else 0)
    head = struct.pack("<4sIIIIIII44x", b"DDS ", 124, flags, h, w, 0, 0, mips)
    if fmt == "DXT1" or fmt.startswith("DX10"):
        pf = struct.pack("<II4s20x", 32, 0x4, fmt[:4].encode())
    else:
        masks = [0xFF << (8 * fmt.index(c)) if c in fmt else 0 for c in "RGBA"]
        bits, kind = 8 * len(fmt), 0x20000 if fmt == "L" else 0x40 | (0x1 if "A" in fmt else 0)
        masks = [0xFF, 0, 0, 0] if fmt == "L" else masks
        pf = struct.pack("<II4sIIIII", 32, kind, b"\0" * 4, bits, *masks)
    tail = struct.pack("<IIIII", 0x1000, caps2, 0, 0, 0)
    extra = struct.pack("<IIIII", int(fmt[5:]), 3, 0, 1, 0) if fmt.startswith("DX10") else b""
    return head + pf + tail + extra + b"\0" * (w * h * 4)


def dds_pixels(blob: bytes) -> tuple[tuple[int, int], bytes]:
    """The largest image of an uncompressed DDS, as RGBA (a reader of its own, by the masks)."""
    h, w = struct.unpack_from("<II", blob, 12)
    flags, fourcc, bits, *masks = struct.unpack_from("<I4sIIIII", blob, 80)
    if flags & 0x4:  # DX10, R8G8B8A8 or B8G8R8A8
        order = "RGBA" if struct.unpack_from("<I", blob, 128)[0] in (28, 29) else "BGRA"
        masks, bits, at = [0xFF << (8 * order.index(c)) for c in "RGBA"], 32, 148
    else:
        at = 128
    step, data = bits // 8, blob[at:]
    out = bytearray(b"\xff" * (w * h * 4))
    for i, mask in enumerate(masks if not flags & 0x20000 else [masks[0]] * 3):
        if mask:
            byte = (mask.bit_length() - 1) // 8
            out[i::4] = data[byte : byte + w * h * step : step]
    return (w, h), bytes(out)


class DdsBackTests(unittest.TestCase):
    def test_an_uncompressed_dds_written_back_holds_the_pngs_pixels(self) -> None:
        rng = random.Random(41)
        for _ in range(40):
            fmt = rng.choice(["BGRA", "RGBA", "ABGR", "BGRX", "BGR", "RGB", "L", "DX10:28"])
            size = (rng.randint(1, 33), rng.randint(1, 33))
            edit = noise(rng, size, alpha="A" in fmt or fmt.startswith("DX10"))
            if fmt == "L":
                edit = edit.convert("L").convert("RGBA")
            original = dds(fmt, (8, 8), rng.choice([1, 4]))
            blob = write_dds(png_of(edit), original)
            got_size, pixels = dds_pixels(blob)
            self.assertEqual(got_size, size)
            want = edit.convert("RGBA").tobytes()
            if "A" not in fmt and not fmt.startswith("DX10"):
                want = Image.frombytes("RGBA", size, want).convert("RGB").convert("RGBA").tobytes()
            self.assertEqual(pixels, want, fmt)
            if fmt in ("BGRA", "RGBA"):  # Pillow reads the same file to the same pixels
                self.assertEqual(Image.open(io.BytesIO(blob)).convert("RGBA").tobytes(), want)

    def test_block_compressed_and_cube_maps_say_why_they_stay_one_way(self) -> None:
        png = png_of(noise(random.Random(42), (4, 4)))
        for original, why in (
            (dds("DXT1", (4, 4)), "encoder ViWo does not ship"),
            (dds("DX10:71", (4, 4)), "encoder ViWo does not ship"),
            (dds("BGRA", (4, 4), caps2=0x200), "cube map"),
        ):
            with self.assertRaisesRegex(ValueError, why):
                write_dds(png, original)
        image, audio = decode.FfmpegImage(), decode.VgmstreamCli()
        self.assertTrue(image.encodes)
        self.assertFalse(audio.encodes or decode.FfmpegVideo().encodes)
        self.assertIn("proprietary", audio.one_way)
        self.assertIn("proprietary", decode.FfmpegVideo().one_way)
        self.assertIn("proprietary", decode.BinkGame().one_way)


def random_sheet(rng, sizes: list[tuple[int, int]]) -> Image.Image:
    """A sprite sheet in the decoder's layout: palette colours (player ones included),
    shadows and transparency inside each frame, nothing outside."""

    def pick():
        return rng.choice([None, SHADOW, *(COLORS[rng.randrange(256)] for _ in "ab")])

    return sheet([(w, h, [[pick() for _ in range(w)] for _ in range(h)]) for w, h in sizes])


class SlpBackTests(unittest.TestCase):
    def test_a_sheet_written_back_decodes_to_the_same_sheet(self) -> None:
        rng = random.Random(51)
        for _ in range(25):
            sizes = [(rng.randint(1, 30), rng.randint(1, 10)) for _ in range(rng.randint(1, 20))]
            original, _ = random_slp(rng, sizes)
            edit = random_sheet(rng, sizes)
            blob, outside = write_slp(png_of(edit), original, COLORS)
            self.assertEqual(outside, 0)
            self.assertEqual(sheet(frames(blob, COLORS)).tobytes(), edit.tobytes())
            full = Image.new("RGBA", edit.size, COLORS[40])  # paint over the cells' padding
            lost = edit.width * edit.height - sum(w * h for w, h in sizes)
            self.assertEqual(write_slp(png_of(full), original, COLORS)[1], lost)  # counted
            self.assertEqual(blob[:32], original[:32])  # header and comment kept
            for i in range(len(sizes)):  # sizes, hotspots, palette and properties kept
                self.assertEqual(
                    blob[40 + 32 * i : 64 + 32 * i], original[40 + 32 * i : 64 + 32 * i]
                )

    def test_a_decoded_sprite_written_back_decodes_the_same(self) -> None:
        rng = random.Random(52)
        for _ in range(25):
            sizes = [(rng.randint(1, 70), rng.randint(1, 6)) for _ in range(rng.randint(1, 4))]
            original, _ = random_slp(rng, sizes)
            shown = sheet(frames(original, COLORS))
            again, _ = write_slp(png_of(shown), original, COLORS)
            self.assertEqual(sheet(frames(again, COLORS)).tobytes(), shown.tobytes())

    def test_a_player_colour_stays_one_and_a_wrong_sheet_is_named(self) -> None:
        rng = random.Random(53)
        original, _ = random_slp(rng, [(3, 1)])
        edit = sheet([(3, 1, [[COLORS[PLAYER + 2], (1, 2, 3, 255), None]])])
        blob, _ = write_slp(png_of(edit), original, COLORS)
        self.assertIn(bytes([0x16, 2]), blob)  # one player colour (count 1, colour 2)
        near = min(COLORS, key=lambda c: sum((a - b) ** 2 for a, b in zip(c, (1, 2, 3))))
        self.assertEqual(frames(blob, COLORS)[0][2][0][1], near)  # not in the palette: nearest
        with self.assertRaisesRegex(ValueError, "the SLP needs"):
            write_slp(png_of(Image.new("RGBA", (5, 5))), original, COLORS)
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            for folder, name, data in (("slp", "1.slp", original), ("png", "1.png", png_of(edit))):
                (ws / folder).mkdir()
                (ws / folder / name).write_bytes(data)
            missing = SlpDecoder().encode(
                ws / "png" / "1.png", ws / "slp" / "1.slp", ws / "o", None
            )
            self.assertIn("palette", missing.error)
            (ws / "bina").mkdir()
            (ws / "bina" / "50500.bina").write_text(PAL, encoding="ascii")
            done = SlpDecoder().encode(ws / "png" / "1.png", ws / "slp" / "1.slp", ws / "o", None)
            self.assertTrue(done.ok, done.error)
            self.assertEqual((ws / "o").read_bytes(), blob)


def loc(rng, rows: list[tuple[str, str, int]], version: int = 1) -> bytes:
    from viwo.plugins.warscape.loc import MAGIC, _field

    body = b"".join(_field(k) + _field(t) + bytes([f]) for k, t, f in rows)
    return MAGIC + struct.pack("<II", version, len(rows)) + body


def text(rng) -> str:
    return "".join(rng.choice("abc é漢\n\"'{}") for _ in range(rng.randint(0, 12)))


class LocBackTests(unittest.TestCase):
    def test_decoded_then_written_back_is_the_original_and_edits_keep_order_and_flags(self):
        rng = random.Random(61)
        for _ in range(40):
            keys = list(dict.fromkeys(f"k{rng.randint(0, 999)}" for _ in range(rng.randint(0, 9))))
            rows = [(k, text(rng), rng.choice((0, 1))) for k in keys]
            original = loc(rng, rows, rng.choice((1, 2)))
            self.assertEqual(write_loc(read_loc(original), original), original)
            edited = {k: text(rng) for k in keys if rng.random() < 0.8}
            edited |= {f"new{i}": text(rng) for i in range(rng.randint(0, 2))}
            version, back = read_entries(write_loc(edited, original))
            self.assertEqual(version, read_entries(original)[0])
            self.assertEqual({k: t for k, t, _ in back}, edited)
            flags = {k: f for k, _, f in rows}
            kept = [(k, f) for k, _, f in back if k in flags]
            self.assertEqual(kept, [(k, flags[k]) for k in keys if k in edited])  # order, flags

    def test_a_table_that_is_not_one_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "t.loc").write_bytes(loc(None, [("a", "b", 1)]))
            for bad in ("[1, 2]", "{damaged", '{"a": 3}'):
                (root / "t.json").write_text(bad, encoding="utf-8")
                out = LocBuiltin().encode(root / "t.json", root / "t.loc", root / "o.loc", None)
                self.assertEqual(out.kind, OutcomeKind.FAILED, bad)
            (root / "t.json").write_text(json.dumps({"a": "B"}), encoding="utf-8")
            done = LocBuiltin().encode(root / "t.json", root / "t.loc", root / "o.loc", None)
            self.assertTrue(done.ok)
            self.assertEqual(read_loc((root / "o.loc").read_bytes()), {"a": "B"})


class RpycBackTests(unittest.TestCase):
    def test_the_edited_script_is_the_member_that_replaces_the_compiled_one(self) -> None:
        unrpyc = UnrpycCli()
        self.assertEqual(unrpyc.member_back("game/script.rpyc"), "game/script.rpy")
        self.assertEqual(unrpyc.member_back("Script.RPYC"), "Script.RPY")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "s.rpy").write_text("label start:\n    'é'\n", encoding="utf-8")
            done = unrpyc.encode(root / "s.rpy", root / "s.rpyc", root / "o.rpy", None)
            self.assertTrue(done.ok)
            self.assertEqual((root / "o.rpy").read_bytes(), (root / "s.rpy").read_bytes())
            (root / "s.rpy").write_bytes(b"\xff\xfe broken")
            bad = unrpyc.encode(root / "s.rpy", root / "s.rpyc", root / "o.rpy", None)
            self.assertIn("not UTF-8", bad.error)


if __name__ == "__main__":
    unittest.main()
