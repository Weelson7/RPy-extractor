"""L3: REDengine RDAR archives (synthetic, raw segments; Kraken needs the game's DLL, L7)."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract
from viwo.plugins.redengine import RdarBuiltin
from viwo.plugins.redengine.rdar import CLASSES, KARK, Archive, Oodle, extension, root_class


def cr2w(root: str) -> bytes:
    """A minimal CR2W: strings table, names table with one name, a chunk table with one chunk."""
    strings = root.encode() + b"\0"
    header = b"CR2W" + struct.pack("<IIQIIIII", 195, 0, 0, 0, 0, 0, 0, 1)  # 40 bytes
    tables_at = 40
    strings_at = tables_at + 120
    names_at = strings_at + len(strings)
    chunks_at = names_at + 8
    tables = [
        (strings_at, len(strings), 0),
        (names_at, 1, 0),
        (0, 0, 0),
        (0, 0, 0),
        (chunks_at, 1, 0),
    ]
    tables += [(0, 0, 0)] * 5
    blob = header + b"".join(struct.pack("<III", *t) for t in tables)
    blob += strings + struct.pack("<II", 0, 0) + struct.pack("<HHIIIII", 0, 0, 0, 0, 0, 0, 0)
    return blob


def rdar(files: dict[int, list[bytes]]) -> bytes:
    """An archive whose members are stored raw (packed size == size)."""
    data_at = 40
    data, segments, entries = b"", [], []
    for name_hash, parts in files.items():
        first = len(segments)
        for part in parts:
            segments.append((data_at + len(data), len(part), len(part)))
            data += part
        entries.append(
            struct.pack("<QQIIIII", name_hash, 0, 0, first, len(segments), 0, 0) + b"\0" * 20
        )
    index = struct.pack("<IIQIII", 8, 0, 0, len(entries), len(segments), 0)
    index += b"".join(entries) + b"".join(struct.pack("<QII", *s) for s in segments)
    head = b"RDAR" + struct.pack("<IQIQQ", 12, data_at + len(data), len(index), 0, 0)
    head = head.ljust(data_at, b"\0")
    return head + data + index


class RedengineTests(unittest.TestCase):
    def test_root_class_and_extension(self) -> None:
        self.assertEqual(root_class(cr2w("CBitmapTexture")), "CBitmapTexture")
        self.assertEqual(extension(cr2w("CBitmapTexture")), "xbm")
        self.assertEqual(extension(cr2w("SomethingNew")), "cr2w")
        self.assertEqual(extension(b"KB2jwhatever"), "bk2")
        self.assertEqual(extension(b"\0\0\0\0"), "bin")

    def test_members_come_out_by_hash_with_their_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "cp"
            (game / "archive" / "pc" / "content").mkdir(parents=True)
            (game / "REDprelauncher.exe").write_bytes(b"MZ")
            archive = rdar({0x1234: [cr2w("CMesh"), b"buffer-bytes"], 0x99: [b"KB2jvideo"]})
            (game / "archive" / "pc" / "content" / "basegame_1.archive").write_bytes(archive)
            before = tree_hashes(game)
            result = extract(
                runtime(root),
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertEqual(tree_hashes(game), before)
            self.assertEqual(result.runs[0].plugin_id, "redengine")
            ws = root / "ws"
            self.assertTrue((ws / "mesh" / "0000000000001234.mesh").is_file())
            self.assertEqual(
                (ws / "buffer" / "0000000000001234.mesh.1.buffer").read_bytes(), b"buffer-bytes"
            )
            self.assertEqual((ws / "bk2" / "0000000000000099.bk2").read_bytes(), b"KB2jvideo")
            self.assertEqual(result.archives_extracted, 1)


def kark(raw: bytes) -> bytes:
    """A Kraken segment as the archives store it: KARK, the inflated size, then the payload
    (here the bytes reversed: the fake decompressor below undoes that)."""
    return KARK + struct.pack("<I", len(raw)) + raw[::-1]


class FakeOodle:
    def decompress(self, packed: bytes, size: int) -> bytes:
        return packed[::-1][:size]


def rdar_kraken(members: dict[int, bytes]) -> bytes:
    """rdar() with every segment Kraken-packed (packed size != size)."""
    archive = bytearray(rdar({h: [kark(raw)] for h, raw in members.items()}))
    index_pos, index_size = struct.unpack_from("<QI", archive, 8)
    files, segs = struct.unpack_from("<II", archive, index_pos + 16)
    at = index_pos + 28 + 56 * files
    for i, raw in enumerate(members.values()):  # the stored size is the inflated one
        offset, packed, _ = struct.unpack_from("<QII", archive, at + 16 * i)
        struct.pack_into("<QII", archive, at + 16 * i, offset, packed, len(raw))
    return bytes(archive)


class ArchivePropertyTests(unittest.TestCase):
    def test_a_corrupt_archive_only_ever_fails_as_bad_data(self) -> None:
        import io
        import random

        rng = random.Random(14)
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(400):
                members = {
                    rng.randrange(1 << 64): [rng.randbytes(rng.randint(0, 40))] for _ in range(3)
                }
                blob = bytearray(rdar(members))
                for _ in range(rng.randint(1, 8)):  # damage anywhere: header, data, index
                    blob[rng.randrange(len(blob))] = rng.randrange(256)
                if rng.random() < 0.2:
                    blob = blob[: rng.randrange(len(blob))]
                try:
                    archive = Archive(io.BytesIO(bytes(blob)))
                    for entry in archive.entries():
                        archive.write(entry, Path(tmp) / str(i), None)
                except (ValueError, struct.error):
                    pass  # what the backend turns into "bad RDAR: ..."
                self.assertIn(root_class(bytes(blob)), ("",) + tuple(CLASSES))  # never raises

    def test_kraken_members_need_the_games_decompressor_and_say_so(self) -> None:
        import io
        import random

        rng = random.Random(3)
        with tempfile.TemporaryDirectory() as tmp:
            members = {
                rng.randrange(1 << 64): b"KB2j" + rng.randbytes(rng.randint(1, 60))
                for _ in range(5)
            }
            blob = rdar_kraken(members)
            archive = Archive(io.BytesIO(blob))
            for entry in archive.entries():
                self.assertTrue(archive.write(entry, Path(tmp) / "with", FakeOodle()))
                self.assertFalse(archive.write(entry, Path(tmp) / "without", None))
            got = {int(p.stem, 16): p.read_bytes() for p in (Path(tmp) / "with").glob("*.bk2")}
            self.assertEqual(got, members)  # inflated byte for byte, typed from the content
            self.assertFalse(
                (Path(tmp) / "without").exists() and any((Path(tmp) / "without").iterdir())
            )
            ctx = mock.Mock()
            ctx.os.tools.locate.return_value = None
            ctx.cancel.cancelled = False
            path = Path(tmp) / "a.archive"
            path.write_bytes(blob)
            out = RdarBuiltin().extract(path, Path(tmp) / "plugin", ctx)  # no Oodle beside it
            self.assertTrue(any("Kraken-compressed member(s) skipped" in n for n in out.notes))
            self.assertTrue(any("keep their hashes" in n for n in out.notes))
            path.write_bytes(b"RDAR" + b"\xff" * 40)
            self.assertIn("bad RDAR", RdarBuiltin().extract(path, Path(tmp) / "bad", ctx).error)

    def test_empty_entries_and_a_packed_buffer_without_oodle(self) -> None:
        import io

        from viwo.plugins.redengine.rdar import Entry

        blob = bytearray(rdar({1: [b"main", b"buffer-raw"]}))
        archive = Archive(io.BytesIO(bytes(blob)))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(archive.write(Entry(5, ()), Path(tmp), None))  # nothing to write
            entry = next(archive.entries())
            buffer = entry.segments[1]
            packed = Entry(entry.name_hash, (entry.segments[0], (buffer[0], buffer[1], 99)))
            blob[buffer[0] : buffer[0] + 4] = KARK  # the buffer is now Kraken-packed
            archive = Archive(io.BytesIO(bytes(blob)))
            self.assertFalse(archive.write(packed, Path(tmp), None))  # skipped, so said

    def test_the_oodle_bridge(self) -> None:
        lib = mock.Mock()
        for got, want in ((5, b"\0" * 5), (0, None), (-1, None)):
            lib.OodleLZ_Decompress.return_value = got
            self.assertEqual(Oodle(lib).decompress(b"packed", 8), want)
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            archive = game / "archive" / "pc" / "content" / "a.archive"
            archive.parent.mkdir(parents=True)
            host = mock.Mock()
            self.assertIsNone(Oodle.beside(archive, host))  # no DLL in bin/x64
            (game / "bin" / "x64").mkdir(parents=True)
            (game / "bin" / "x64" / "oo2ext_7_win64.dll").write_bytes(b"MZ")
            for loaded, expect in ((lib, Oodle), (None, type(None))):
                host.load_native.return_value = loaded
                self.assertIsInstance(Oodle.beside(archive, host), expect)
            host.load_native.side_effect = OSError("not a valid Win32 application")
            self.assertIsNone(Oodle.beside(archive, host))


class NameListTests(unittest.TestCase):
    """The community path list: every listed path is found by its own hash, nothing else is."""

    class PlainOodle:  # the list arrives Kraken-compressed; here it is stored as is
        def decompress(self, packed: bytes, size: int) -> bytes:
            return packed[:size]

    def test_every_listed_path_is_found_by_its_hash_and_only_those(self) -> None:
        import random

        from viwo.plugins.redengine.names import Names, fnv1a64

        self.assertEqual(fnv1a64(b""), 0xCBF29CE484222325)  # FNV-1a 64 test vectors
        self.assertEqual(fnv1a64(b"a"), 0xAF63DC4C8601EC8C)
        rng = random.Random(3)
        paths = sorted(
            {
                "base\\"
                + "\\".join(rng.choice("abcxyz_") * rng.randint(1, 6) for _ in range(3))
                + ".mesh"
                for _ in range(300)
            }
        )
        plain = "\r\n".join(paths).encode()  # the last line has no line break after it
        with tempfile.TemporaryDirectory() as tmp:
            kark = Path(tmp) / "usedhashes.kark"
            kark.write_bytes(b"KARK" + struct.pack("<I", len(plain)) + plain)
            names = Names.load(kark, self.PlainOodle())
            try:
                for path in paths:
                    self.assertEqual(names.get(fnv1a64(path.encode())), path)
                listed = {fnv1a64(p.encode()) for p in paths}
                for other in (rng.getrandbits(64) for _ in range(200)):
                    if other not in listed:
                        self.assertIsNone(names.get(other))
            finally:
                names.close()
            self.assertIsNone(Names.load(kark, None))  # no Oodle: no names, said by the plugin

    def test_every_reason_members_keep_their_hashes_is_said(self) -> None:
        from types import SimpleNamespace

        from viwo.plugins.redengine import _names
        from viwo.plugins.redengine import rdar as rdar_module
        from viwo.plugins.redengine.names import Names, fnv1a64

        class Dead:
            def decompress(self, packed, size):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            kark = Path(tmp) / "usedhashes.kark"
            known = "base\\known.mesh"
            kark.write_bytes(b"KARK" + struct.pack("<I", len(known)) + known.encode())
            bad = Path(tmp) / "bad.kark"
            bad.write_bytes(b"NOPE")

            def ctx(tool, cancelled=False):
                located = SimpleNamespace(path=str(tool)) if tool else None
                return SimpleNamespace(
                    os=SimpleNamespace(tools=SimpleNamespace(locate=lambda spec: located)),
                    cancel=SimpleNamespace(cancelled=cancelled),
                )

            cases = (
                (None, self.PlainOodle(), "cp77-hashes"),
                (kark, None, "needs the game's Oodle"),
                (bad, self.PlainOodle(), "not a KARK file"),
                (kark.with_name("x.kark"), Dead(), "did not load"),
            )
            kark.with_name("x.kark").write_bytes(kark.read_bytes())
            for tool, oodle, why in cases:
                names, notes = _names(ctx(tool), oodle)
                self.assertIsNone(names)
                self.assertIn(why, " ".join(notes), tool)
            self.assertIsNone(Names.load(None, self.PlainOodle()))
            members = {fnv1a64(known.encode()): b"KB2jknown", 0x77: b"KB2junknown"}
            archive = Path(tmp) / "a.archive"
            archive.write_bytes(rdar_kraken(members))
            for oodle, note in ((self.PlainOodle(), "not in the path list"), (Dead(), "bad data")):
                with mock.patch.object(rdar_module.Oodle, "beside", return_value=oodle):
                    out = RdarBuiltin().extract(archive, Path(tmp) / note, ctx(kark))
                self.assertIn(note, " ".join(out.notes))
            with mock.patch.object(rdar_module.Oodle, "beside", return_value=FakeOodle()):
                stopped = RdarBuiltin().extract(archive, Path(tmp) / "cancel", ctx(kark, True))
            self.assertEqual(stopped.files, 0)  # a cancel stops before the first member

    def test_a_named_member_lands_at_its_path_an_unsafe_name_keeps_its_hash(self) -> None:
        import io

        from viwo.plugins.redengine.rdar import Archive

        data = rdar({0x10: [cr2w("CMesh"), b"buf"], 0x20: [b"KB2jv"]})
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            rdar_file = Archive(io.BytesIO(data))
            entries = {e.name_hash: e for e in rdar_file.entries()}
            rdar_file.write(entries[0x10], dest, None, "base\\props\\crate.mesh")
            rdar_file.write(entries[0x20], dest, None, "..\\..\\escape.bk2")
            self.assertTrue((dest / "base" / "props" / "crate.mesh").is_file())
            self.assertEqual((dest / "base" / "props" / "crate.mesh.1.buffer").read_bytes(), b"buf")
            self.assertTrue((dest / "0000000000000020.bk2").is_file())
            self.assertFalse((dest.parent / "escape.bk2").exists())


if __name__ == "__main__":
    unittest.main()
