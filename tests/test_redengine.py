"""L3: REDengine RDAR archives (synthetic, raw segments; Kraken needs the game's DLL, L7)."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract
from viwo.plugins.redengine.rdar import extension, root_class


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
                (ws / "buffer" / "0000000000001234.1.buffer").read_bytes(), b"buffer-bytes"
            )
            self.assertEqual((ws / "bk2" / "0000000000000099.bk2").read_bytes(), b"KB2jvideo")
            self.assertEqual(result.archives_extracted, 1)


if __name__ == "__main__":
    unittest.main()
