"""L3: archive formats of the smaller engine plugins: asar, VPK, XP3, BSA, BA2."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract
from viwo.plugins.kirikiri import MAGIC as XP3

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 40


def asar(files: dict[str, bytes]) -> bytes:
    tree, body = {"files": {}}, b""
    for name, data in files.items():
        node = tree
        *dirs, leaf = name.split("/")
        for d in dirs:
            node = node["files"].setdefault(d, {"files": {}})
        node["files"][leaf] = {"size": len(data), "offset": str(len(body))}
        body += data
    raw = json.dumps(tree).encode()
    pickle = struct.pack("<I", len(raw)) + raw
    pickle += b"\0" * (-len(pickle) % 4)
    return struct.pack("<III", 4, len(pickle) + 4, len(pickle)) + pickle + body


def vpk(files: dict[str, tuple[bytes, int]]) -> tuple[bytes, bytes]:
    """(_dir.vpk, _000.vpk); files map path -> (data, 0 inline or 1 in part 000)."""
    tree, inline, part = b"", b"", b""
    for path, (data, where) in files.items():
        folder, _, rest = path.rpartition("/")
        stem, _, ext = rest.rpartition(".")
        offset = len(inline) if not where else len(part)
        index = 0x7FFF if not where else 0
        tree += ext.encode() + b"\0" + folder.encode() + b"\0" + stem.encode() + b"\0"
        tree += struct.pack("<IHHIIH", 0, 0, index, offset, len(data), 0xFFFF) + b"\0\0"
        inline, part = (inline + data, part) if not where else (inline, part + data)
    return struct.pack("<III", 0x55AA1234, 1, len(tree) + 1) + tree + b"\0" + inline, part


def xp3(files: list[tuple[str, bytes, bool]]) -> bytes:
    body, index = b"", b""
    for name, data, encrypted in files:
        packed = zlib.compress(data)
        offset = 19 + len(body)
        body += packed
        raw = name.encode("utf-16-le")
        info = (
            struct.pack("<IQQH", 0x80000000 if encrypted else 0, len(data), len(packed), len(name))
            + raw
        )
        segm = struct.pack("<IQQQ", 1, offset, len(data), len(packed))
        inner = (
            b"info"
            + struct.pack("<Q", len(info))
            + info
            + b"segm"
            + struct.pack("<Q", len(segm))
            + segm
        )
        index += b"File" + struct.pack("<Q", len(inner)) + inner
    packed = zlib.compress(index)
    tail = b"\x01" + struct.pack("<QQ", len(packed), len(index)) + packed
    return XP3 + struct.pack("<Q", 19 + len(body)) + body + tail


def bsa(files: dict[str, bytes]) -> bytes:
    """Version 104, one folder, names included, compressed by default (one stored file)."""
    folder = b"textures\\ui"
    items = list(files.items())
    names = b"".join(n.encode() + b"\0" for n, _ in items)
    header_end = 36 + 16 + 1 + len(folder) + 1 + 16 * len(items) + len(names)
    records, body, offset = b"", b"", header_end
    for i, (name, data) in enumerate(items):
        stored = i == 0  # toggle bit: this one is not compressed
        blob = data if stored else struct.pack("<I", len(data)) + zlib.compress(data)
        records += struct.pack("<QII", i, len(blob) | (0x40000000 if stored else 0), offset)
        body, offset = body + blob, offset + len(blob)
    head = b"BSA\0" + struct.pack(
        "<8I", 104, 36, 0x7, 1, len(items), len(folder) + 1, len(names), 0
    )
    folders = struct.pack("<QII", 0, len(items), 0) + bytes([len(folder) + 1]) + folder + b"\0"
    return head + folders + records + names + body


def ba2(files: dict[str, bytes]) -> bytes:
    items = list(files.items())
    records_end = 24 + 36 * len(items)
    records, body = b"", b""
    for name, data in items:
        packed = zlib.compress(data)
        records += struct.pack(
            "<I4sIIQIII",
            0,
            b"txt\0",
            0,
            0x100100,
            records_end + len(body),
            len(packed),
            len(data),
            0xBAADF00D,
        )
        body += packed
    table = b"".join(struct.pack("<H", len(n)) + n.encode() for n, _ in items)
    head = b"BTDX" + struct.pack("<I4sIQ", 1, b"GNRL", len(items), records_end + len(body))
    return head + records + body + table


def ba2_texture(block: bytes) -> bytes:
    """DX10 BA2 with one 4x4 BC1 texture (one chunk, stored)."""
    name = b"Textures/ui/icon.dds"
    record = struct.pack("<I4sIBBHHHBBBB", 0, b"dds\0", 0, 0, 1, 24, 4, 4, 1, 71, 0, 0)
    offset = 24 + len(record) + 24
    chunk = struct.pack("<QIIHHI", offset, 0, len(block), 0, 0, 0xBAADF00D)
    table = struct.pack("<H", len(name)) + name
    head = b"BTDX" + struct.pack("<I4sIQ", 1, b"DX10", 1, offset + len(block))
    return head + record + chunk + block + table


class FormatPipelineTests(unittest.TestCase):
    def test_ba2_texture_becomes_a_valid_dds(self) -> None:
        from viwo.core.carve import scan
        from viwo.plugins.bethesda.archives import ba2_files

        [(name, dds)] = list(ba2_files(ba2_texture(b"\xaa" * 8)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "icon.dds"
            path.write_bytes(dds)
            hits = scan(path, CancelToken())
        self.assertEqual(
            (name, [(h.offset, h.size, h.suffix) for h in hits]),
            ("Textures/ui/icon.dds", [(0, 156, ".dds")]),
        )

    def run_game(self, root: Path, name: str, files: dict[str, bytes]):
        game = root / name
        for rel, data in files.items():
            (game / rel).parent.mkdir(parents=True, exist_ok=True)
            (game / rel).write_bytes(data)
        before = tree_hashes(game)
        request = ExtractionRequest(str(game), str(root / f"ws-{name}"))
        result = extract(runtime(root), request, "j", lambda e: None, CancelToken())
        self.assertEqual(tree_hashes(game), before)
        return result, root / f"ws-{name}"

    def test_engine_inside_an_asar_is_redetected(self) -> None:
        """Doc 3.1 / 14.2 #3: after the wrapper is unpacked, detection runs once inside it."""
        with tempfile.TemporaryDirectory() as tmp:
            inner = {
                "www/js/rpg_core.js": b"//mv",
                "www/data/System.json": b"{}",
                "www/img/a.png": PNG,
            }
            files = {"resources/app.asar": asar(inner), "electron.exe": b"MZ"}
            result, ws = self.run_game(Path(tmp), "wrapped", files)
            self.assertEqual(result.runs[0].plugin_id, "electron")
            self.assertIn("rpgmaker", {r.plugin_id for r in result.runs})
            self.assertTrue(
                any("Re-detected rpgmaker" in line for line in result.logs), result.logs
            )
            self.assertEqual((ws / "png" / "a.png").read_bytes(), PNG)

    def test_all_formats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result, ws = self.run_game(
                root,
                "electron",
                {
                    "resources/app.asar": asar({"img/title.png": PNG, "../x.txt": b"no"}),
                    "electron.exe": b"MZ",
                },
            )
            self.assertEqual(
                (result.runs[0].plugin_id, (ws / "png" / "title.png").read_bytes()),
                ("electron", PNG),
            )
            self.assertFalse(list(root.rglob("x.txt")))
            vdir, v000 = vpk({"materials/logo.png": (PNG, 0), "sound/hit.wav": (b"RIFFwav", 1)})
            result, ws = self.run_game(
                root, "source", {"hl2/pak01_dir.vpk": vdir, "hl2/pak01_000.vpk": v000}
            )
            self.assertEqual(result.runs[0].plugin_id, "source")
            self.assertEqual(
                ((ws / "png" / "logo.png").read_bytes(), (ws / "wav" / "hit.wav").read_bytes()),
                (PNG, b"RIFFwav"),
            )
            self.assertFalse((ws / "vpk").exists())  # parts are not copied raw
            entries = [
                ("bg/sky.png", PNG, False),
                ("scenario/first.ks", b"*start", False),
                ("se/locked.ogg", b"x", True),
            ]
            result, ws = self.run_game(root, "kirikiri", {"data.xp3": xp3(entries)})
            self.assertEqual(
                ((ws / "png" / "sky.png").read_bytes(), (ws / "ks" / "first.ks").read_bytes()),
                (PNG, b"*start"),
            )
            self.assertFalse((ws / "ogg").exists())  # game-specific cipher: not guessed
            result, ws = self.run_game(
                root,
                "skyrim",
                {
                    "Data/Skyrim - Interface.bsa": bsa({"a.png": PNG, "b.txt": b"hello" * 20}),
                    "Data/Skyrim.esm": b"TES4",
                },
            )
            self.assertEqual(result.runs[0].plugin_id, "bethesda")
            self.assertEqual(
                ((ws / "png" / "a.png").read_bytes(), (ws / "txt" / "b.txt").read_bytes()),
                (PNG, b"hello" * 20),
            )
            result, ws = self.run_game(
                root, "fo4", {"Data/Fallout4 - Misc.ba2": ba2({"Strings/readme.txt": b"vault"})}
            )
            self.assertEqual((ws / "txt" / "readme.txt").read_bytes(), b"vault")


if __name__ == "__main__":
    unittest.main()
