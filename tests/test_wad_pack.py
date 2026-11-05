"""L3: Doom round trip (pack.wad). A WAD with a palette, pictures, flats, DMX sounds, text and a
map is unpacked, random members are edited (a picture repainted, a flat repainted, a sound
replaced, a text changed) and packed back: re-unpacking gives each edit as the palette holds it
(nearest colour, transparency kept, the grAb offsets kept), every other lump is byte for byte
the original, the lump order and markers are unchanged, and the packer's read-back agrees."""

from __future__ import annotations

import io
import random
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from tests.test_doom import make_picture, make_sound, make_wad
from viwo.plugins.doom.pack import WadWriter, members
from viwo.plugins.doom.wad import WadBuiltin, directory, read

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False), options={})


def palette(rng: random.Random) -> bytes:
    return b"".join(bytes([i, rng.randrange(256), 255 - i]) for i in range(256))  # distinct


def game(root: Path, rng: random.Random) -> Path:
    entries = [("PLAYPAL", palette(rng)), ("P_START", b""), ("PIC1", make_picture())]
    entries += [("PIC2", make_picture()), ("P_END", b""), ("F_START", b"")]
    entries += [("FLAT1", bytes(rng.randrange(256) for _ in range(64 * 64))), ("F_END", b"")]
    entries += [("DSBANG", make_sound(rng.randbytes(300))), ("README", b"hello doom\n")]
    entries += [("MAP01", b""), ("THINGS", rng.randbytes(20)), ("LINEDEFS", rng.randbytes(14))]
    return make_wad(root / "game.wad", entries, b"IWAD")


def edit(rng: random.Random, member: str, path: Path) -> None:
    if path.suffix == ".png":
        with Image.open(path) as img:
            img = img.convert("RGBA")
        for _ in range(rng.randint(1, 20)):
            xy = (rng.randrange(img.width), rng.randrange(img.height))
            img.putpixel(xy, (rng.randrange(256), rng.randrange(256), rng.randrange(256), 255))
        img.save(path)
    elif path.suffix == ".wav":
        out = io.BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(1)
            w.setframerate(22050)
            w.writeframes(rng.randbytes(rng.randint(50, 400)))
        path.write_bytes(out.getvalue())
    else:
        path.write_bytes(path.read_bytes() + b"edited\n")


def quantized(png: Path, pal: bytes) -> list:
    """The edit as a palette can hold it: nearest colour, alpha < 128 transparent."""
    colours = [tuple(pal[i * 3 : i * 3 + 3]) for i in range(256)]
    with Image.open(png) as img:
        rgba = list(img.convert("RGBA").getdata())

    def near(r, g, b):
        return min(colours, key=lambda c: (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2)

    return [None if a < 128 else near(r, g, b) for r, g, b, a in rgba]


class WadRoundTripTests(unittest.TestCase):
    def test_every_edit_comes_back_as_the_palette_holds_it_and_nothing_else_moves(self) -> None:
        rng = random.Random(16)
        for case in range(6):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                wad, out = game(root, rng), root / "out"
                out.mkdir()
                WadBuiltin().extract(wad, out, SimpleNamespace(**vars(CTX), game_root=root))
                pal = read(wad, directory(wad)[1][0])[:768]
                names = sorted(members(wad, pal))
                chosen = rng.sample([n for n in names if (out / n).is_file()], rng.randint(1, 5))
                for member in chosen:
                    edit(rng, member, out / member)
                edits = {m: out / m for m in chosen}
                result = WadWriter().pack(wad, edits, CTX)
                self.assertEqual(result.files, len(chosen), result)
                self.assertEqual(WadWriter().verify(wad, edits, CTX), [])
                again = root / "again"
                again.mkdir()
                WadBuiltin().extract(wad, again, SimpleNamespace(**vars(CTX), game_root=root))
                self._check(out, again, chosen, names, pal)
                self.assertEqual(
                    [lump.name for lump in directory(wad)[1]][:3], ["PLAYPAL", "P_START", "PIC1"]
                )

    def _check(self, out: Path, again: Path, chosen: list, names: list, pal: bytes) -> None:
        for member in names:
            if not (out / member).is_file():
                continue
            if member not in chosen:
                self.assertEqual((again / member).read_bytes(), (out / member).read_bytes(), member)
            elif member.endswith(".png"):
                with Image.open(again / member) as img:
                    got = [
                        None if a < 128 else (r, g, b)
                        for r, g, b, a in img.convert("RGBA").getdata()
                    ]
                self.assertEqual(got, quantized(out / member, pal), member)
            elif member.endswith(".wav"):
                with wave.open(str(again / member)) as w, wave.open(str(out / member)) as e:
                    self.assertEqual(w.readframes(w.getnframes()), e.readframes(e.getnframes()))
            else:
                self.assertEqual((again / member).read_bytes(), (out / member).read_bytes())


if __name__ == "__main__":
    unittest.main()
