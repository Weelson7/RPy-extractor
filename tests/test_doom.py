"""L3: Doom plugin: WAD directory, lump decoders (picture, flat, DMX sound), pipeline."""

from __future__ import annotations

import io
import struct
import tempfile
import unittest
import wave
import zlib
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.plugins.doom import DoomPlugin, lumps
from viwo.plugins.doom.wad import directory, layout

PALETTE = bytes(i % 256 for i in range(768))


def make_wad(path: Path, entries: list[tuple[str, bytes]], kind: bytes = b"PWAD") -> Path:
    body, table = b"", b""
    for name, data in entries:
        table += struct.pack("<ii8s", 12 + len(body), len(data), name.encode())
        body += data
    path.write_bytes(kind + struct.pack("<ii", len(entries), 12 + len(body)) + body + table)
    return path


def make_picture() -> bytes:
    """2x3 picture: column 0 has pixels 5,6 at rows 0-1; column 1 has pixel 7 at row 2."""
    head = struct.pack("<HHhh", 2, 3, -4, 9)
    col0 = bytes([0, 2, 0, 5, 6, 0, 0xFF])
    col1 = bytes([2, 1, 0, 7, 0, 0xFF])
    start = 8 + 8
    return head + struct.pack("<II", start, start + len(col0)) + col0 + col1


def make_sound(samples: bytes, rate: int = 11025) -> bytes:
    padded = b"\x80" * 16 + samples + b"\x80" * 16
    return struct.pack("<HHI", 3, rate, len(padded)) + padded


def png_pixels(data: bytes) -> tuple[int, int, bytes, bytes]:
    width, height = struct.unpack(">II", data[16:24])
    grab = data.find(b"grAb")
    idat = data.find(b"IDAT")
    (size,) = struct.unpack(">I", data[idat - 4 : idat])
    raw = zlib.decompress(data[idat + 4 : idat + 4 + size])
    rows = b"".join(raw[y * (width * 4 + 1) + 1 : (y + 1) * (width * 4 + 1)] for y in range(height))
    return width, height, rows, data[grab + 4 : grab + 12] if grab > 0 else b""


class LumpTests(unittest.TestCase):
    def test_picture_with_transparency_and_offsets(self) -> None:
        width, height, rgba, grab = png_pixels(lumps.picture(make_picture(), PALETTE))
        self.assertEqual((width, height), (2, 3))
        self.assertEqual(struct.unpack(">ii", grab), (-4, 9))
        pixel = lambda x, y: rgba[(y * 2 + x) * 4 : (y * 2 + x) * 4 + 4]  # noqa: E731
        self.assertEqual(pixel(0, 0), PALETTE[15:18] + b"\xff")
        self.assertEqual(pixel(1, 2), PALETTE[21:24] + b"\xff")
        self.assertEqual(pixel(1, 0)[3], 0)  # transparent

    def test_bad_pictures_flats_and_sounds_are_rejected(self) -> None:
        self.assertIsNone(lumps.picture(b"\x02\x00\x03\x00" + b"\0" * 4 + b"\xff" * 8, PALETTE))
        self.assertIsNone(lumps.picture(make_picture()[:-3], PALETTE))
        self.assertIsNone(lumps.flat(b"\0" * 100, PALETTE))
        self.assertIsNone(lumps.dmx_sound(struct.pack("<HHI", 3, 11025, 999) + b"\0"))

    def test_flat_and_sound(self) -> None:
        self.assertEqual(png_pixels(lumps.flat(bytes(4096), PALETTE))[:2], (64, 64))
        with wave.open(io.BytesIO(lumps.dmx_sound(make_sound(b"\x10\x20\x30")))) as wav:
            self.assertEqual((wav.getframerate(), wav.readframes(10)), (11025, b"\x10\x20\x30"))

    def test_magic_and_text(self) -> None:
        self.assertEqual(lumps.by_magic(b"MUS\x1a...."), ".mus")
        self.assertEqual(lumps.by_magic(b"RIFF\0\0\0\0WAVEfmt "), ".wav")
        self.assertTrue(lumps.is_text(b"actor Foo {\n}\n"))
        self.assertFalse(lumps.is_text(b"\x00\x01"))


class WadTests(unittest.TestCase):
    def test_directory_bounds_and_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wad = make_wad(
                Path(tmp) / "a.wad", [("S_START", b""), ("TROOA1", b"x"), ("S_END", b"")]
            )
            kind, entries = directory(wad)
            self.assertEqual(
                (kind, [e.name for e in entries]), (b"PWAD", ["S_START", "TROOA1", "S_END"])
            )
            self.assertEqual([(e.name, s) for e, s, _ in layout(entries)], [("TROOA1", "sprites")])
            broken = Path(tmp) / "b.wad"
            broken.write_bytes(b"PWAD" + struct.pack("<ii", 5, 9999))
            with self.assertRaises(ValueError):
                directory(broken)

    def test_maps_are_grouped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wad = make_wad(
                Path(tmp) / "m.wad",
                [("MAP01", b""), ("THINGS", b"t"), ("LINEDEFS", b"l"), ("CREDIT", b"c")],
            )
            got = [(e.name, m) for e, _, m in layout(directory(wad)[1])]
            self.assertEqual(got, [("THINGS", "MAP01"), ("LINEDEFS", "MAP01"), ("CREDIT", "")])

    def test_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_wad(root / "mod.wad", [("X", b"x")])
            self.assertEqual(DoomPlugin().detect(FolderProbe(root)).confidence, 0.6)
            make_wad(root / "freedoom2.wad", [("X", b"x")], b"IWAD")
            self.assertEqual(DoomPlugin().detect(FolderProbe(root)).confidence, 0.9)


class DoomPipelineTests(unittest.TestCase):
    def test_iwad_and_pwad_extract_without_touching_the_game(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            make_wad(
                game / "doom2.wad",
                [
                    ("PLAYPAL", PALETTE),
                    ("TITLEPIC", make_picture()),
                    ("DSPISTOL", make_sound(b"\x01\x02")),
                    ("D_RUNNIN", b"MUS\x1a" + b"\0" * 12),
                    ("DEHACKED", b"Patch File\n"),
                    ("MAP01", b""),
                    ("THINGS", b"\0" * 10),
                    ("LINEDEFS", b"\0" * 14),
                    ("F_START", b""),
                    ("FLOOR0_1", bytes(4096)),
                    ("F_END", b""),
                    ("S_START", b""),
                    ("TROOA1", make_picture()),
                    ("S_END", b""),
                ],
                b"IWAD",
            )
            make_wad(
                game / "mod.wad", [("S_START", b""), ("POSSA1", make_picture()), ("S_END", b"")]
            )
            (game / "broken.wad").write_bytes(b"PWAD" + struct.pack("<ii", 3, 999999))
            before = tree_hashes(game)
            rt = runtime(root, "[plugins]\ndoom = on\n")
            request = ExtractionRequest(str(game), str(root / "ws"), plugins=("doom",))
            result = extract(rt, request, "j", lambda e: None, CancelToken())
            ws = root / "ws"
            names = lambda ext: sorted(p.name for p in (ws / ext).iterdir())  # noqa: E731
            self.assertEqual(
                names("png"), ["FLOOR0_1.png", "POSSA1.png", "TITLEPIC.png", "TROOA1.png"]
            )
            self.assertEqual(names("wav"), ["DSPISTOL.wav"])
            self.assertEqual(names("mus"), ["D_RUNNIN.mus"])
            self.assertIn("MAP01_THINGS.lmp", names("lmp"))
            self.assertIn("DEHACKED.txt", names("txt"))
            self.assertEqual(result.by_backend.get("wad-builtin"), 2)
            self.assertTrue(any("broken.wad" in w for w in result.warnings), result.warnings)
            self.assertEqual(tree_hashes(game), before)


if __name__ == "__main__":
    unittest.main()
