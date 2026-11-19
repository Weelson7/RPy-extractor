"""L3: Godot's imported textures (decode.ctex) and their way back (doc 18.3), property tests on
textures written here: `.ctex` (Godot 4) and `.stex` (Godot 3), PNG and WebP mipmaps with or
without Godot's tag, and the uncompressed 8-bit formats. Decoded, each shows its largest image;
an edited PNG written back keeps the original's header, form, tag and channels, gets the PNG's
size and a full mip chain when it had mipmaps, and decodes to the edit exactly; decoding what was
written and writing it again changes nothing. VRAM-compressed textures (DXT1, DXT3, DXT5,
RGTC_R, RGTC_RG, BPTC_RGBA, BPTC_RGBF/RGBFU, Godot 4's DXT5_RA_AS_RG) decode to what ViWo's
block decoders (Pillow for BC6H) show, and an edit goes back in the same block format, every mip
level, within the format's bound; BC6H says its clamp and its loss. ETC, ETC2, ASTC, PVRTC and
Basis textures, a missing Pillow and a Pillow without WebP are refused with the reason; end to
end, an edited PNG of a loose texture comes back as the texture in the patched copy."""

from __future__ import annotations

import io
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from tests.helpers import runtime
from tests.test_encode_bc import check, pillow, within_range
from tests.test_encoders import png_of
from tests.test_roundtrip_encode import decoded, workspace
from viwo.backends.blocks.decode_bc import decompress
from viwo.backends.blocks.encode_bc import size as size_of
from viwo.backends.blocks.encode_bptc import CLAMPED, HDR
from viwo.core.roundtrip import repack
from viwo.plugins.godot.ctex import CtexDecoder, parse, to_png
from viwo.plugins.godot.ctex_write import refusal, write_ctex
from viwo.plugins.godot.vram import level

MODES = {0: "L", 1: "LA", 2: "R", 3: "RG", 4: "RGB", 5: "RGBA"}


def raw_bytes(image: Image.Image, fmt: int) -> bytes:
    rgba = image.convert("RGBA").tobytes()
    if MODES[fmt] == "R":
        return rgba[0::4]
    if MODES[fmt] == "RG":
        return b"".join(rgba[i : i + 2] for i in range(0, len(rgba), 4))
    return image.convert(MODES[fmt]).tobytes()


def shown(image: Image.Image, fmt: int) -> bytes:
    """What a texture of Godot format `fmt` keeps of an image, as RGBA (R8 shown as grey, RG8
    with an empty blue)."""
    if MODES[fmt] not in ("R", "RG"):
        return image.convert(MODES[fmt]).convert("RGBA").tobytes()
    rgba = image.convert("RGBA").tobytes()
    n = len(rgba) // 4
    out = bytearray(b"\xff" * (4 * n))
    if MODES[fmt] == "R":
        out[0::4] = out[1::4] = out[2::4] = rgba[0::4]
    else:
        out[0::4], out[1::4], out[2::4] = rgba[0::4], rgba[1::4], bytes(n)
    return bytes(out)


def payload(image: Image.Image, kind: str, tag: bytes) -> bytes:
    out = io.BytesIO()
    if kind == "png":
        image.save(out, "PNG")
    else:
        webp = image.convert("RGBA" if "A" in image.mode else "RGB")
        webp.save(out, "WEBP", lossless=True, exact=True)
    return tag + out.getvalue()


def levels(image: Image.Image, mips: bool) -> list[Image.Image]:
    count = max(image.size).bit_length() if mips else 1
    sizes = [(max(1, image.width >> n), max(1, image.height >> n)) for n in range(count)]
    return [image.resize(s, Image.Resampling.BOX) for s in sizes]


def texture(rng, version: int, form: str, image: Image.Image, fmt: int, tag: bytes = b"") -> bytes:
    """A texture: form "raw" (format `fmt`), "png" or "webp" (image's own mode)."""
    mips = rng.random() < 0.5
    chain, (w, h) = levels(image, mips), image.size
    if form == "raw":
        body = b"".join(raw_bytes(level, fmt) for level in chain)
    else:
        parts = [payload(level, form, tag) for level in chain]
        body = b"".join(struct.pack("<I", len(p)) + p for p in parts)
    if version == 4:
        data = {"raw": 0, "png": 1, "webp": 2}[form]
        head = b"GST2" + struct.pack("<IIIIi12x", 1, w, h, rng.getrandbits(32), rng.randint(-1, 3))
        return head + struct.pack("<IHHII", data, w, h, len(chain) - 1, fmt) + body
    flags = rng.getrandbits(32) & ~0xBFFFFF  # stream and detect bits: not form, not mipmaps
    form_bits = {"raw": fmt, "png": 1 << 20, "webp": 1 << 21}[form]
    bits = (1 << 23 if mips else 0) | form_bits | flags
    head = b"GDST" + struct.pack("<HHHHII", w, 0, h, 0, rng.getrandbits(32), bits)
    return head + (struct.pack("<I", len(chain)) if form != "raw" else b"") + body


def noise(rng, size: tuple[int, int], mode: str) -> Image.Image:
    return Image.frombytes("RGBA", size, rng.randbytes(size[0] * size[1] * 4)).convert(mode)


def random_texture(rng) -> tuple[bytes, int, str, int]:
    """(texture, version, form, fmt: the Godot format whose channels it keeps)."""
    version, form = rng.choice((3, 4)), rng.choice(("raw", "png", "webp"))
    size = (rng.randint(1, 24), rng.randint(1, 24))
    if form == "raw":
        fmt = rng.choice(list(MODES))
        return texture(rng, version, form, noise(rng, size, "RGBA"), fmt), version, form, fmt
    mode = rng.choice(("RGB", "RGBA") if form == "webp" else ("L", "LA", "RGB", "RGBA"))
    tag = rng.choice((b"", b"PNG " if form == "png" else b"WEBP"))
    fmt = {"L": 0, "LA": 1, "RGB": 4, "RGBA": 5}[mode]
    return texture(rng, version, form, noise(rng, size, mode), fmt, tag), version, form, fmt


class CtexTests(unittest.TestCase):
    def test_decoded_textures_show_their_largest_image(self) -> None:
        rng = random.Random(81)
        for _ in range(60):
            image = noise(rng, (rng.randint(1, 20), rng.randint(1, 20)), "RGBA")
            fmt, version = rng.choice(list(MODES)), rng.choice((3, 4))
            blob = texture(rng, version, "raw", image, fmt)
            got = Image.open(io.BytesIO(to_png(blob))).convert("RGBA").tobytes()
            self.assertEqual(got, shown(image, fmt), (version, fmt))
            form = rng.choice(("png", "webp"))
            blob = texture(rng, version, form, image, 5, rng.choice((b"", b"WEBP", b"PNG ")))
            self.assertEqual(Image.open(io.BytesIO(to_png(blob))).tobytes(), image.tobytes())

    def test_an_edit_written_back_keeps_the_originals_shape_and_shows_the_edit(self) -> None:
        rng = random.Random(82)
        for _ in range(80):
            original, version, form, fmt = random_texture(rng)
            before = parse(original)
            edit = noise(rng, (rng.randint(1, 30), rng.randint(1, 30)), "RGBA")
            blob = write_ctex(png_of(edit), original)
            after = parse(blob)
            self.assertEqual((after.version, after.kind, after.tag), (version, form, before.tag))
            self.assertEqual((after.width, after.height, after.mips), (*edit.size, before.mips))
            got = Image.open(io.BytesIO(to_png(blob))).convert("RGBA").tobytes()
            self.assertEqual(got, shown(edit, fmt), (version, form, fmt))
            kept = ((0, 8), (16, 40), (48, 52)) if version == 4 else ((0, 4), (6, 8), (10, 20))
            for start, end in kept:  # everything but the size and mipmap fields
                self.assertEqual(blob[start:end], original[start:end], (version, start))
            count = max(edit.size).bit_length() if before.mips else 1
            self.check_chain(blob, after, edit.size, count, fmt)
            again = write_ctex(to_png(blob), blob)  # encode(decode(x)) shows x's image again
            self.assertEqual(to_png(again), to_png(blob))

    def check_chain(self, blob: bytes, tex, size: tuple[int, int], count: int, fmt: int) -> None:
        sizes = [(max(1, size[0] >> n), max(1, size[1] >> n)) for n in range(count)]
        if tex.kind == "raw":
            step = {0: 1, 1: 2, 2: 1, 3: 2, 4: 3, 5: 4}[fmt]
            self.assertEqual(len(blob) - tex.head, sum(w * h * step for w, h in sizes))
            return
        self.assertEqual(len(tex.payloads), count)
        for (at, length), want in zip(tex.payloads, sizes):
            data = blob[at + len(tex.tag) : at + length]
            self.assertEqual(Image.open(io.BytesIO(data)).size, want)
        self.assertEqual(sum(4 + n for _, n in tex.payloads) + tex.head, len(blob))

    def test_what_cannot_go_back_says_why(self) -> None:
        rng = random.Random(83)
        image = noise(rng, (4, 4), "RGBA")
        basis = bytearray(texture(rng, 4, "raw", image, 5))
        basis[36:40] = struct.pack("<I", 3)
        cases = [(basis, "Basis Universal")]
        for version, fmt, why in (
            (4, 25, "format 25 \\(ETC\\): no ETC decoder"),
            (4, 30, "ETC2"),
            (4, 33, "ETC2"),
            (4, 36, "ASTC"),
            (3, 26, "PVRTC"),
            (3, 29, "format 29 \\(ETC\\)"),
            (3, 34, "ETC2"),  # Godot 3's 34 is ETC2_RGB8, Godot 4's DXT5_RA_AS_RG
            (4, 8, "not 8-bit"),
        ):
            blob = bytearray(texture(rng, version, "raw", image, 5))
            struct.pack_into("<I", blob, 48 if version == 4 else 16, fmt)
            cases.append((blob, why))
        for blob, why in cases:
            self.assertRegex(refusal(bytes(blob[:64])), why)
            with self.assertRaisesRegex(ValueError, why):
                write_ctex(png_of(image), bytes(blob))
        webp = texture(rng, 4, "webp", image, 5, b"WEBP")
        png = texture(rng, 3, "png", image, 5, b"PNG ")
        self.assertEqual((refusal(webp[:64]), refusal(png[:64])), ("", ""))
        with mock.patch("PIL.features.check", return_value=False):
            self.assertIn("without WebP", refusal(webp[:64]))
            self.assertEqual(refusal(png[:64]), "")
        with mock.patch.dict(sys.modules, {"PIL": None}):
            self.assertIn("pip install Pillow", refusal(png[:64]))
        self.assertIn("not a Godot texture", refusal(b"GDPC" + bytes(60)))

    def test_the_backend_names_the_file_it_could_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, rng = Path(tmp), random.Random(84)
            (root / "t.ctex").write_bytes(b"GST2" + bytes(10))
            out = CtexDecoder().decode(root / "t.ctex", root, None)
            self.assertIn("t.ctex", out.error)
            (root / "t.ctex").write_bytes(texture(rng, 4, "png", noise(rng, (3, 3), "RGB"), 4))
            self.assertTrue(CtexDecoder().decode(root / "t.ctex", root, None).ok)
            self.assertEqual(CtexDecoder().refuses(root / "t.ctex"), "")
            (root / "e.png").write_bytes(b"not a png")
            failed = CtexDecoder().encode(root / "e.png", root / "t.ctex", root / "o.ctex", None)
            self.assertIn("e.png", failed.error)


VRAM = {17: "BC1", 18: "BC2", 19: "BC3", 20: "BC4", 21: "BC5", 22: "BC7", 23: "BC6HS"}
VRAM |= {24: "BC6H", 34: "BC3RA"}


def vram_texture(rng, version: int, image: Image.Image, fmt: int) -> bytes:
    """A VRAM-compressed texture of `image` in Godot format `fmt`, its blocks by ViWo's encoder."""
    chain, (w, h), kind = levels(image, rng.random() < 0.5), image.size, VRAM[fmt]
    body = b"".join(level(picture, kind) for picture in chain)
    if version == 4:
        head = b"GST2" + struct.pack("<IIIIi12x", 1, w, h, rng.getrandbits(32), -1)
        return head + struct.pack("<IHHII", 0, w, h, len(chain) - 1, fmt) + body
    bits = (1 << 23 if len(chain) > 1 else 0) | fmt | (rng.getrandbits(32) & ~0xBFFFFF)
    return b"GDST" + struct.pack("<HHHHII", w, 0, h, 0, rng.getrandbits(32), bits) + body


def seen(kind: str, data: bytes, size: tuple[int, int]) -> bytes:
    """What the top level shows as RGBA: ViWo's decoders, Pillow for BC6H, Godot's swizzle."""
    if kind.startswith("BC6"):
        return pillow(kind, data[: size_of(kind, *size)], *size)
    rgba = bytearray(decompress(data, *size, "BC3" if kind == "BC3RA" else kind))
    if kind == "BC3RA":
        n = len(rgba) // 4
        rgba[1::4], rgba[2::4], rgba[3::4] = rgba[3::4], bytes(n), b"\xff" * n
    return bytes(rgba)


def as_ra(rgba: bytes) -> bytes:
    """Red and green moved where DXT5_RA_AS_RG stores them: red and alpha."""
    out = bytearray(len(rgba))
    out[0::4], out[3::4] = rgba[0::4], rgba[1::4]
    return bytes(out)


class VramTests(unittest.TestCase):
    def test_vram_textures_decode_and_go_back_in_their_block_format(self) -> None:
        rng = random.Random(86)
        for fmt, kind in list(VRAM.items()) * 3:
            version = 4 if fmt == 34 else rng.choice((3, 4))
            image = noise(rng, (rng.randint(1, 12), rng.randint(1, 12)), "RGBA")
            original = vram_texture(rng, version, image, fmt)
            tex = parse(original)
            self.assertEqual((tex.kind, tex.block), ("vram", kind))
            got = Image.open(io.BytesIO(to_png(original))).convert("RGBA").tobytes()
            self.assertEqual(got, seen(kind, original[tex.head :], image.size), kind)
            edit = noise(rng, (rng.randint(1, 14), rng.randint(1, 14)), "RGBA")
            blob = write_ctex(png_of(edit), original)
            after = parse(blob)
            self.assertEqual((after.fmt, after.width, after.height), (fmt, *edit.size))
            count = max(edit.size).bit_length() if tex.mips else 1
            sizes = [(max(1, edit.width >> n), max(1, edit.height >> n)) for n in range(count)]
            core = "BC3" if kind == "BC3RA" else kind
            self.assertEqual(len(blob) - after.head, sum(size_of(core, *s) for s in sizes))
            shown = seen(kind, blob[after.head :], edit.size)
            want = edit.tobytes()
            if kind == "BC3RA":  # Godot's convert_rg_to_ra_rgba8, both ways
                shown, want = as_ra(shown), as_ra(want)
            check(self, want, shown, core, edit.size, within_range)

    def test_bc6h_says_its_clamp_and_its_loss(self) -> None:
        rng = random.Random(87)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for fmt, hdr in ((24, True), (23, True), (22, False)):
                image = noise(rng, (8, 8), "RGBA")
                (root / "t.ctex").write_bytes(vram_texture(rng, 4, image, fmt))
                out = CtexDecoder().decode(root / "t.ctex", root, None)
                self.assertEqual(out.notes, (CLAMPED,) if hdr else ())
                back = CtexDecoder().encode(root / "t.png", root / "t.ctex", root / "o.ctex", None)
                self.assertEqual(back.notes, (HDR,) if hdr else ())
            cut = vram_texture(rng, 4, noise(rng, (8, 8), "RGBA"), 24)[:60]
            with self.assertRaisesRegex(ValueError, "BC6H data cut short"):
                to_png(cut)


class RepackTests(unittest.TestCase):
    def test_an_edited_png_comes_back_as_the_texture_in_the_copy(self) -> None:
        rng = random.Random(85)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "g"
            (game / ".godot" / "imported").mkdir(parents=True)
            original = texture(rng, 4, "webp", noise(rng, (8, 8), "RGBA"), 5, b"WEBP")
            member = ".godot/imported/icon.png-0f.ctex"
            (game / member).write_bytes(original)
            loose = {"kind": "loose", "member": member}
            work = workspace(
                root,
                game,
                {
                    "ctex/icon.png-0f.ctex": (original, loose),
                    "png/icon.png-0f.png": (
                        to_png(original),
                        decoded("ctex/icon.png-0f.ctex", "icon.png-0f.png", "ctex-builtin"),
                    ),
                },
            )
            edit = noise(rng, (12, 6), "RGBA")
            (work / "png" / "icon.png-0f.png").write_bytes(png_of(edit))
            rt = runtime(root)
            report = repack(rt, work, root / "copy")
            self.assertTrue(report["verified"], report)
            way = report["plan"][0]["ways"][0]
            self.assertEqual((way["encoder"], way["member"]), ("decode.ctex", member))
            back = (root / "copy" / member).read_bytes()
            self.assertEqual(Image.open(io.BytesIO(to_png(back))).tobytes(), edit.tobytes())
            self.assertEqual((game / member).read_bytes(), original)  # the game: only read


if __name__ == "__main__":
    unittest.main()
