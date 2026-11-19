"""L3: Godot's imported textures (decode.ctex) and their way back (doc 18.3), property tests on
textures written here: `.ctex` (Godot 4) and `.stex` (Godot 3), PNG and WebP mipmaps with or
without Godot's tag, and the uncompressed 8-bit formats. Decoded, each shows its largest image;
an edited PNG written back keeps the original's header, form, tag and channels, gets the PNG's
size and a full mip chain when it had mipmaps, and decodes to the edit exactly; decoding what was
written and writing it again changes nothing. VRAM-compressed and Basis textures, a missing
Pillow and a Pillow without WebP are refused with the reason; end to end, an edited PNG of a
loose texture comes back as the texture in the patched copy."""

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
from tests.test_encoders import png_of
from tests.test_roundtrip_encode import decoded, workspace
from viwo.core.roundtrip import repack
from viwo.plugins.godot.ctex import CtexDecoder, parse, to_png
from viwo.plugins.godot.ctex_write import refusal, write_ctex

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
        vram4 = bytearray(texture(rng, 4, "raw", image, 5))
        vram4[48:52] = struct.pack("<I", 17)
        vram3 = bytearray(texture(rng, 3, "raw", image, 5))
        vram3[16:20] = struct.pack("<I", 19)
        for blob, why in ((basis, "Basis Universal"), (vram4, "format 17"), (vram3, "format 19")):
            self.assertIn(why, refusal(bytes(blob[:64])))
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
