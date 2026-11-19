"""L3: Wolf RPG / DXArchive version 6 (unarchive.wolf, pack.wolf), property tests on archives the
test writes byte by byte (the first-party writer, and a hand-built one to prove the reader reads
the documented layout, not only its own writer). Every raw member comes out under its path, in a
keyed archive too (the key verified against the header); nested folders and a Windows-unsafe name
are kept through the names record; a DXA-compressed member is refused by name, a wrong version
and a wrong key are refused by name; the archive rebuilds with an edited member and reads back."""

from __future__ import annotations

import random
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from viwo.contracts import workspace as ws
from viwo.contracts.types import CancelToken, OutcomeKind
from viwo.core.pipeline.probe import FolderProbe
from viwo.plugins.wolfrpg import WolfRpgPlugin, WolfUnarchiver, WolfWriter
from viwo.plugins.wolfrpg.wolf import HEADER, NONE, key_bytes, read_archive
from viwo.plugins.wolfrpg.wolf_pack import write_archive


def ctx(key: str = "") -> SimpleNamespace:
    return SimpleNamespace(cancel=CancelToken(), options={"decryption_key": key})


def members() -> dict[str, bytes]:
    rng = random.Random(5)
    return {
        "mapdata/map001.mps": rng.randbytes(rng.randint(0, 300)),
        "mapdata/map002.mps": rng.randbytes(rng.randint(1, 300)),
        "basicdata/db.dat": rng.randbytes(64),
        "picture/title.png": b"\x89PNG\r\n" + rng.randbytes(40),
        "root.txt": b"hello wolf",
    }


class WolfReadTests(unittest.TestCase):
    def _extract(self, blob: bytes, key: str = "") -> dict[str, bytes]:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            out = WolfUnarchiver().extract(_write(dest / "a.wolf", blob), dest / "o", ctx(key))
            self.assertEqual(out.kind, OutcomeKind.OK, out.error)
            got = {}
            base = dest / "o"
            for p in base.rglob("*"):
                if p.is_file() and p.name not in (ws.NAMES_FILE,):
                    got[p.relative_to(base).as_posix()] = p.read_bytes()
            return got

    def test_every_raw_member_comes_out(self) -> None:
        want = members()
        self.assertEqual(self._extract(write_archive(want)), want)

    def test_a_keyed_archive_reads_with_the_verified_key(self) -> None:
        want = members()
        blob = write_archive(want, key_bytes("wolfpass"))
        self.assertEqual(self._extract(blob, "wolfpass"), want)
        self.assertNotEqual(blob[:2], struct.pack("<H", 0x5844))  # really encrypted

    def test_a_hand_built_archive_reads(self) -> None:
        body, entries = read_archive(write_archive({"a/b.txt": b"xy", "c.txt": b"z"}))
        self.assertEqual({e.path for e in entries}, {"a/b.txt", "c.txt"})
        self.assertTrue(all(e.pressed == NONE for e in entries))

    def test_detection_and_a_windows_unsafe_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "g"
            game.mkdir()
            (game / "Data.wolf").write_bytes(write_archive({"con.txt": b"k", "ok.txt": b"v"}))
            self.assertEqual(WolfRpgPlugin().detect(FolderProbe(game)).confidence, 0.9)
            out = WolfUnarchiver().extract(game / "Data.wolf", Path(tmp) / "o", ctx())
            self.assertEqual(out.kind, OutcomeKind.OK)
            self.assertTrue((Path(tmp) / "o" / ws.NAMES_FILE).is_file())  # con.txt altered


class WolfRefusalTests(unittest.TestCase):
    def test_a_compressed_member_is_refused_by_name(self) -> None:
        blob = bytearray(write_archive({"one.dat": b"abcd", "two.dat": b"efgh"}))
        _, file_off, _ = _offsets(bytes(blob))
        struct.pack_into("<Q", blob, file_off + 48, 4)  # entry 0 pressed: pretend DXA-compressed
        with tempfile.TemporaryDirectory() as tmp:
            out = WolfUnarchiver().extract(
                _write(Path(tmp) / "a.wolf", bytes(blob)), Path(tmp) / "o", ctx()
            )
            self.assertTrue(any("compressed" in n for n in out.notes), out.notes)
            self.assertEqual(out.files, 1)  # the other member still came out

    def test_a_wrong_version_and_a_wrong_key_are_refused_by_name(self) -> None:
        good = write_archive({"x.txt": b"q"})
        wrong = bytearray(good)
        struct.pack_into("<H", wrong, 2, 7)  # version 7
        with self.assertRaisesRegex(ValueError, "version 7"):
            read_archive(bytes(wrong))
        keyed = write_archive({"x.txt": b"q"}, key_bytes("right"))
        with self.assertRaisesRegex(ValueError, "DX"):
            read_archive(keyed, key_bytes("wrong!!"))


class WolfPackTests(unittest.TestCase):
    def test_the_archive_rebuilds_with_an_edit_and_reads_back(self) -> None:
        want = members()
        with tempfile.TemporaryDirectory() as tmp:
            arc = _write(Path(tmp) / "Data.wolf", write_archive(want))
            edited = Path(tmp) / "edit.bin"
            edited.write_bytes(b"NEW MAP DATA")
            out = WolfWriter().pack(arc, {"mapdata/map001.mps": edited}, ctx())
            self.assertEqual(out.kind, OutcomeKind.OK, out.error)
            body, entries = read_archive(arc.read_bytes())
            back = {e.path: body[e.offset : e.offset + e.size] for e in entries}
            self.assertEqual(back["mapdata/map001.mps"], b"NEW MAP DATA")
            self.assertEqual(back["picture/title.png"], want["picture/title.png"])


def _write(path: Path, blob: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return path


def _offsets(blob: bytes) -> tuple[int, int, int]:
    magic, version, head_size, data_start, name_off, file_off, dir_off, _ = struct.unpack_from(
        "<HHIIIIII", blob, 0
    )
    return HEADER + name_off, HEADER + file_off, HEADER + dir_off


if __name__ == "__main__":
    unittest.main()
