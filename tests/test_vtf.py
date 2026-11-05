"""L3: Source textures (decode.vtf). For random sizes, mipmap counts, frame counts and header
versions (7.0-7.5, the resource table from 7.3), the PNG holds exactly the largest mipmap of the
first frame: raw formats pixel for pixel, block-compressed ones as Pillow decodes the same blocks;
a texture cut short, a format not decoded yet and a damaged header are named failures."""

from __future__ import annotations

import io
import random
import struct
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from viwo.contracts.types import OutcomeKind
from viwo.plugins.source.vtf import RAW, VtfDecoder, _size, to_png


def vtf(rng, fmt: int, size: tuple, mips: int, minor: int, frames: int, top: bytes, env=False):
    """A VTF whose largest mipmap's first frame (first face) is `top` (everything else random);
    an env map has 6 faces, 7 before 7.5 (the sphere map VTFLib reads too)."""
    w, h = size
    data, faces = b"", (7 if minor < 5 else 6) if env else 1
    for level in range(mips - 1, -1, -1):
        mw, mh = max(1, w >> level), max(1, h >> level)
        for layer in range(frames * faces):
            data += top if (level == 0 and layer == 0) else rng.randbytes(_size(fmt, mw, mh))
    resources = minor >= 3
    hsize = 96 if resources else 80
    head = b"VTF\0" + struct.pack("<IIIHHIH", 7, minor, hsize, w, h, 0x4000 * env, frames)
    head += b"\0" * (52 - len(head)) + struct.pack("<iBiBB", fmt, mips, -1, 0, 0)
    head += struct.pack("<H", 1)
    if resources:
        head += b"\0" * (68 - len(head)) + struct.pack("<I", 1) + b"\0" * 8
        head += struct.pack("<3sxI", b"\x30\0\0", hsize)
    return head + b"\0" * (hsize - len(head)) + data


class VtfTests(unittest.TestCase):
    def test_the_png_is_the_largest_mipmap_of_the_first_frame(self) -> None:
        rng = random.Random(23)
        for _ in range(60):
            fmt = rng.choice([*RAW, 13, 14, 15])
            w, h = rng.choice([4, 8, 16, 32, 64]), rng.choice([4, 8, 16, 32])
            mips = rng.randint(1, min(w, h).bit_length())
            top = rng.randbytes(_size(fmt, w, h))
            env = rng.random() < 0.4  # a cubemap: its faces are layers of every mipmap
            blob = vtf(rng, fmt, (w, h), mips, rng.randint(0, 5), rng.randint(1, 3), top, env)
            got = Image.open(io.BytesIO(to_png(blob)))
            self.assertEqual(got.size, (w, h))
            if fmt in RAW:
                _, mode, raw = RAW[fmt]
                want = Image.frombytes(mode, (w, h), top, "raw", raw)
                self.assertEqual(got.convert(mode).tobytes(), want.tobytes(), fmt)
            else:
                alone = vtf(rng, fmt, (w, h), 1, 2, 1, top)  # the same blocks, no other data
                self.assertEqual(got.tobytes(), Image.open(io.BytesIO(to_png(alone))).tobytes())

    def test_every_problem_is_a_named_failure(self) -> None:
        rng = random.Random(24)
        whole = vtf(rng, 13, (16, 16), 3, 2, 1, rng.randbytes(_size(13, 16, 16)))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = {
                "cut": whole[:-10],
                "header": b"VTF\0" + bytes(100),
                "not": b"PNG nothing",
            }
            cases["format"] = whole[:52] + struct.pack("<i", 24) + whole[56:]
            for name, blob in cases.items():
                (root / f"{name}.vtf").write_bytes(blob)
                out = VtfDecoder().decode(root / f"{name}.vtf", root, None)
                self.assertEqual(out.kind, OutcomeKind.FAILED, name)
                self.assertIn(f"{name}.vtf", out.error)
            (root / "ok.vtf").write_bytes(whole)
            self.assertEqual(VtfDecoder().decode(root / "ok.vtf", root, None).files, 1)
            self.assertTrue((root / "ok.png").is_file())


if __name__ == "__main__":
    unittest.main()
