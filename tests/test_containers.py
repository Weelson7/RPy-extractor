"""L3: the flat container plugins added for the owner's library: Genie DRS, Warscape PFH pack."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract
from viwo.plugins.genie import HEADER as DRS_HEADER
from viwo.plugins.genie import MAGIC as DRS_MAGIC

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 40


def drs(tables: dict[str, dict[int, bytes]]) -> bytes:
    """A DRS with one table per extension: {ext: {file id: bytes}}."""
    head = DRS_MAGIC.ljust(40, b"\0") + b"1.00" + b"tribe".ljust(12, b"\0")
    specs_at = DRS_HEADER + 8
    entries_at = specs_at + 12 * len(tables)
    data_at = entries_at + 12 * sum(len(files) for files in tables.values())
    specs, entries, data = b"", b"", b""
    for ext, files in tables.items():
        specs += struct.pack(
            "<4sII", b" " + ext[::-1].encode(), entries_at + len(entries), len(files)
        )
        for file_id, blob in files.items():
            entries += struct.pack("<III", file_id, data_at + len(data), len(blob))
            data += blob
    return head + struct.pack("<II", len(tables), data_at) + specs + entries + data


def pack(files: dict[str, bytes], magic: bytes = b"PFH4", stamps: bool = False) -> bytes:
    index = b""
    for name, blob in files.items():
        index += struct.pack("<I", len(blob)) + (struct.pack("<I", 7) if stamps else b"")
        index += name.replace("/", "\\").encode() + b"\0"
    kind = 2 | (0x10 if stamps else 0)
    head = magic + struct.pack("<6I", kind, 0, 0, len(files), len(index), 1533548507)
    return head + index + b"".join(files.values())


class ContainerTests(unittest.TestCase):
    def run_game(self, root: Path, name: str, files: dict[str, bytes]):
        game = root / name
        for rel, data in files.items():
            (game / rel).parent.mkdir(parents=True, exist_ok=True)
            (game / rel).write_bytes(data)
        before = tree_hashes(game)
        result = extract(
            runtime(root),
            ExtractionRequest(str(game), str(root / f"ws-{name}")),
            "j",
            lambda e: None,
            CancelToken(),
        )
        self.assertEqual(tree_hashes(game), before)
        return result, root / f"ws-{name}"

    def test_drs_members_come_out_by_id_and_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = drs({"slp": {50100: b"SLP1", 50101: b"SLP2"}, "wav": {5000: b"RIFFwav"}})
            result, ws = self.run_game(
                Path(tmp), "aoe", {"resources/graphics.drs": archive, "empires2.exe": b"MZ"}
            )
            self.assertEqual(result.runs[0].plugin_id, "genie")
            self.assertEqual((ws / "slp" / "50100.slp").read_bytes(), b"SLP1")
            self.assertEqual((ws / "wav" / "5000.wav").read_bytes(), b"RIFFwav")
            self.assertEqual(result.archives_extracted, 1)

    def test_pack_members_keep_their_paths_and_block_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = {
                "ui/skins/a.png": PNG,
                "db/units_tables/data": b"table",
                "../escape.txt": b"no",
            }
            for magic, stamps in ((b"PFH4", False), (b"PFH5", True)):
                root = Path(tmp) / magic.decode()
                game_files = {"data/data.pack": pack(files, magic, stamps), "Rome2.exe": b"MZ"}
                result, ws = self.run_game(root, "rome", game_files)
                self.assertEqual(result.runs[0].plugin_id, "warscape")
                self.assertEqual((ws / "png" / "a.png").read_bytes(), PNG)
                self.assertEqual((ws / "noext" / "data").read_bytes(), b"table")
                self.assertFalse((root / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
