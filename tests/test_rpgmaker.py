"""L3: RPG Maker: RGSSAD v1/v3 archives and MV/MZ encrypted media."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_png, runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.plugins.rpgmaker import RpgMakerPlugin
from viwo.plugins.rpgmaker.mv import HEADER
from viwo.plugins.rpgmaker.rgss import MASK, _advance, decrypt, entries

KEY = bytes.fromhex("d41d8cd98f00b204e9800998ecf8427e")


def rgssad_v1(files: dict[str, bytes]) -> bytes:
    out, key = bytearray(b"RGSSAD\x00\x01"), 0xDEADCAFE
    for name, data in files.items():
        raw = name.encode()
        out += struct.pack("<I", len(raw) ^ key)
        key = _advance(key)
        for byte in raw:
            out.append(byte ^ (key & 0xFF))
            key = _advance(key)
        out += struct.pack("<I", len(data) ^ key)
        key = _advance(key)
        out += decrypt(data, key)  # XOR is its own inverse
    return bytes(out)


def rgssad_v3(files: dict[str, bytes], seed: int = 1234) -> bytes:
    key = (seed * 9 + 3) & MASK
    table_size = sum(16 + len(n) for n in files) + 16
    offset, table, body = 12 + table_size, bytearray(), bytearray()
    for i, (name, data) in enumerate(files.items()):
        raw, file_key = name.encode(), 0x1000 + i
        table += struct.pack("<4I", offset ^ key, len(data) ^ key, file_key ^ key, len(raw) ^ key)
        table += bytes(b ^ ((key >> (8 * (j % 4))) & 0xFF) for j, b in enumerate(raw))
        body += decrypt(data, file_key)
        offset += len(data)
    table += struct.pack("<4I", key, 0, 0, 0)
    return b"RGSSAD\x00\x03" + struct.pack("<I", seed) + bytes(table) + bytes(body)


def encrypt_mv(data: bytes) -> bytes:
    head = bytes(a ^ b for a, b in zip(data[:16], KEY))
    return HEADER + head + data[16:]


class RgssTests(unittest.TestCase):
    def test_v1_and_v3_round_trip(self) -> None:
        files = {"Graphics\\Titles\\title.png": b"PNG" * 50, "Audio\\BGM\\a.ogg": b"OggS1"}
        for blob in (rgssad_v1(files), rgssad_v3(files)):
            got = {n.decode(): decrypt(blob[o : o + s], k) for n, o, s, k in entries(blob)}
            self.assertEqual(got, files)


class RpgMakerPipelineTests(unittest.TestCase):
    def test_vxace_archive_and_mv_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            png = make_png(root / "face.png").read_bytes()
            vx = root / "vx"
            vx.mkdir()
            (vx / "Game.rgss3a").write_bytes(
                rgssad_v3({"Graphics\\Faces\\Actor1.png": png, "..\\evil.txt": b"x"})
            )
            mv = root / "mv"
            (mv / "www" / "data").mkdir(parents=True)
            (mv / "www" / "img" / "faces").mkdir(parents=True)
            (mv / "www" / "data" / "System.json").write_text(
                json.dumps({"encryptionKey": KEY.hex()})
            )
            (mv / "www" / "img" / "faces" / "Actor2.rpgmvp").write_bytes(encrypt_mv(png))
            (mv / "www" / "js").mkdir()
            (mv / "www" / "js" / "rpg_core.js").write_text("//")
            self.assertEqual(RpgMakerPlugin().detect(FolderProbe(mv)).confidence, 0.9)
            before = tree_hashes(mv)
            for game in (vx, mv):
                request = ExtractionRequest(str(game), str(root / f"ws-{game.name}"))
                result = extract(runtime(root), request, "j", lambda e: None, CancelToken())
                self.assertEqual(result.runs[0].plugin_id, "rpgmaker", result.warnings)
            self.assertEqual((root / "ws-vx" / "png" / "Actor1.png").read_bytes(), png)
            self.assertFalse(list(root.rglob("evil.txt")))  # traversal entry skipped
            self.assertEqual((root / "ws-mv" / "png" / "Actor2.png").read_bytes(), png)
            self.assertFalse((root / "ws-mv" / "rpgmvp").exists())  # decoded, not copied raw
            (mv / "www" / "data" / "System.json").unlink()  # key recovered from the PNG header
            request = ExtractionRequest(str(mv), str(root / "ws-mv2"), plugins=("rpgmaker",))
            extract(runtime(root), request, "j", lambda e: None, CancelToken())
            self.assertEqual((root / "ws-mv2" / "png" / "Actor2.png").read_bytes(), png)
            self.assertEqual(
                tree_hashes(mv) | {}, {k: v for k, v in before.items() if "System" not in k}
            )


if __name__ == "__main__":
    unittest.main()
