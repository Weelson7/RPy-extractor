"""L3: GameMaker `FORM` data files (unarchive.gamemaker, pack.gamemaker), property tests on
containers the test builds byte by byte the way GameMaker lays them out (a FORM of named chunks,
the first GEN8; TXTR with embedded PNGs; AUDO and STRG as pointer lists of absolute offsets to
u32-length-prefixed entries). Every chunk comes out, the PNG textures, the audio and the strings
are decoded, a raw chunk and a texture read back when edited in place, a size change and an edit
to the read-only strings.json are refused by name, an untrusted chunk name cannot escape, and
damage never crashes the reader."""

from __future__ import annotations

import json
import random
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace

from viwo.contracts import workspace as ws
from viwo.contracts.types import CancelToken, OutcomeKind
from viwo.core.pipeline.probe import FolderProbe
from viwo.plugins.gamemaker import GameMakerPlugin, GmUnarchiver, GmWriter, identify_gm


def ctx() -> SimpleNamespace:
    return SimpleNamespace(cancel=CancelToken())


def png_bytes(rgb=(200, 40, 40), w: int = 4, h: int = 4) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    raw = b"".join(b"\0" + bytes(rgb) * w for _ in range(h))
    header = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _pointer_list(entries: list[bytes]):
    """A chunk payload builder: u32 count, u32 absolute offset per entry, then the entries."""

    def build(start: int) -> bytes:
        cur, offs, blob = 4 + 4 * len(entries), [], b""
        for entry in entries:
            offs.append(start + cur)
            blob += entry
            cur += len(entry)
        head = struct.pack("<I", len(entries)) + b"".join(struct.pack("<I", o) for o in offs)
        return head + blob

    return build


def txtr(pngs: list[bytes]):
    return _pointer_list(pngs)


def audo(blobs: list[bytes]):
    return _pointer_list([struct.pack("<I", len(b)) + b for b in blobs])


def strg(strings: list[str]):
    return _pointer_list([struct.pack("<I", len(s.encode())) + s.encode() + b"\0" for s in strings])


def raw(data: bytes):
    return lambda _start: data


def build_form(specs: list[tuple[str, object]]) -> bytes:
    sizes = [len(b(0)) for _name, b in specs]
    at, starts = 8, []
    for sz in sizes:
        starts.append(at + 8)
        at += 8 + sz
    out = bytearray(b"FORM" + struct.pack("<I", at - 8))
    for (name, b), start, sz in zip(specs, starts, sizes):
        out += name.encode("latin-1") + struct.pack("<I", sz) + b(start)
    return bytes(out)


WAV = b"RIFF" + struct.pack("<I", 20) + b"WAVEfmt " + b"\0" * 12
OGG = b"OggS" + b"\0" * 20
STRINGS = ["hello", "obj_player", "日本語"]


def a_game() -> bytes:
    pngs = [png_bytes((200, 40, 40)), png_bytes((10, 220, 90), 8, 8)]
    return build_form(
        [
            ("GEN8", raw(b"\x01\x02\x03\x04" + b"\0" * 36)),
            ("TXTR", txtr(pngs)),
            ("AUDO", audo([WAV, OGG])),
            ("STRG", strg(STRINGS)),
            ("CODE", raw(b"some bytecode here, fixed length.")),
        ]
    )


def extract(blob: bytes, dest: Path) -> tuple[dict, tuple]:
    dest.mkdir(parents=True, exist_ok=True)
    arc = dest / "data.win"
    arc.write_bytes(blob)
    out = GmUnarchiver().extract(arc, dest / "o", ctx())
    assert out.kind is OutcomeKind.OK, out.error
    got = {
        p.relative_to(dest / "o").as_posix(): p.read_bytes()
        for p in (dest / "o").rglob("*")
        if p.is_file() and p.name != ws.NAMES_FILE
    }
    return got, out.notes


class GameMakerReadTests(unittest.TestCase):
    def test_every_chunk_texture_audio_and_string_comes_out(self) -> None:
        pngs = [png_bytes((200, 40, 40)), png_bytes((10, 220, 90), 8, 8)]
        with tempfile.TemporaryDirectory() as tmp:
            got, _ = extract(a_game(), Path(tmp))
        self.assertEqual(got["textures/0000.png"], pngs[0])
        self.assertEqual(got["textures/0001.png"], pngs[1])
        self.assertEqual(got["audio/0000.wav"], WAV)
        self.assertEqual(got["audio/0001.ogg"], OGG)
        self.assertEqual(json.loads(got["strings.json"].decode()), STRINGS)
        self.assertEqual(got["chunks/GEN8.bin"], b"\x01\x02\x03\x04" + b"\0" * 36)
        self.assertEqual(got["chunks/CODE.bin"], b"some bytecode here, fixed length.")
        self.assertNotIn("chunks/TXTR.bin", got)  # decoded chunks are not also raw (no overlap)
        self.assertNotIn("chunks/AUDO.bin", got)
        self.assertNotIn("chunks/STRG.bin", got)

    def test_detection_and_identify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "g"
            game.mkdir()
            (game / "data.win").write_bytes(a_game())
            self.assertEqual(GameMakerPlugin().detect(FolderProbe(game)).confidence, 0.9)
        head = b"FORM" + b"\0" * 4 + b"GEN8"
        self.assertIsNotNone(identify_gm(Path("data.win"), head, b""))
        self.assertIsNone(identify_gm(Path("x.aiff"), b"FORM" + b"\0" * 4 + b"AIFF", b""))

    def test_an_untrusted_chunk_name_cannot_escape(self) -> None:
        blob = build_form([("GEN8", raw(b"\0" * 8)), ("../x", raw(b"danger"))])
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            out = GmUnarchiver().extract(_write(dest / "data.win", blob), dest / "o", ctx())
            self.assertIs(out.kind, OutcomeKind.OK)
            self.assertFalse((dest / "x.bin").exists())  # did not land outside dest

    def test_damage_never_crashes(self) -> None:
        rng = random.Random(7)
        good = a_game()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for case in range(200):
                blob = bytearray(good)
                if blob and rng.random() < 0.5:
                    blob = blob[: rng.randrange(len(blob))]
                elif blob:
                    blob[rng.randrange(len(blob))] ^= 1 << rng.randrange(8)
                GmUnarchiver().extract(
                    _write(dest / f"d{case}.win", bytes(blob)), dest / f"o{case}", ctx()
                )


class GameMakerPackTests(unittest.TestCase):
    def test_same_size_edits_read_back_and_size_changes_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            arc = _write(dest / "data.win", a_game())
            new_code = _write(dest / "code.bin", b"SOME BYTECODE HERE, FIXED LENGTH!")  # same len
            out = GmWriter().pack(arc, {"chunks/CODE.bin": new_code}, ctx())
            self.assertIs(out.kind, OutcomeKind.OK, out.error)
            got, _ = extract(arc.read_bytes(), dest / "back")
            self.assertEqual(got["chunks/CODE.bin"], b"SOME BYTECODE HERE, FIXED LENGTH!")
            self.assertEqual(got["textures/0000.png"], png_bytes((200, 40, 40)))
            bigger = _write(dest / "big.bin", b"x" * 999)
            bad = GmWriter().pack(arc, {"chunks/CODE.bin": bigger}, ctx())
            self.assertIs(bad.kind, OutcomeKind.FAILED)
            self.assertIn("size changed", bad.error)

    def test_a_texture_edit_reads_back_and_strings_json_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            arc = _write(dest / "data.win", a_game())
            new_png = _write(dest / "t.png", png_bytes((5, 5, 240)))  # same 4x4 PNG, same length
            self.assertEqual(len(new_png.read_bytes()), len(png_bytes((200, 40, 40))))
            out = GmWriter().pack(arc, {"textures/0000.png": new_png}, ctx())
            self.assertIs(out.kind, OutcomeKind.OK, out.error)
            got, _ = extract(arc.read_bytes(), dest / "back")
            self.assertEqual(got["textures/0000.png"], new_png.read_bytes())
            refuse = GmWriter().pack(arc, {"strings.json": _write(dest / "s.json", b"[]")}, ctx())
            self.assertIs(refuse.kind, OutcomeKind.FAILED)
            self.assertIn("read-only", refuse.error)


def _write(path: Path, blob: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return path


if __name__ == "__main__":
    unittest.main()
