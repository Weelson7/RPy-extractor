"""L3: Unreal plugin: pak footers, AES key verification, key finder, fake repak/retoc tools."""

from __future__ import annotations

import stat
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.identify import identify
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.plugins.unreal import SLOTS, UnrealPlugin
from viwo.plugins.unreal.aes import SBOX, _expand, _mul, decrypt_block
from viwo.plugins.unreal.keys import _from_movs, parse_key
from viwo.plugins.unreal.pak import PAK_MAGIC, UTOC_MAGIC, pak_info

KEY = bytes(range(100, 132))


def encrypt_block(key: bytes, block: bytes) -> bytes:
    """Forward AES-256 (test only) to build encrypted fixtures."""
    rounds, s = _expand(key), [a ^ b for a, b in zip(block, _expand(key)[0])]
    for rnd in range(1, 15):
        s = [SBOX[b] for b in s]
        s = [s[((c + r) % 4) * 4 + r] for c in range(4) for r in range(4)]
        if rnd < 14:
            mixed = []
            for c in range(4):
                a = s[c * 4 : c * 4 + 4]
                for r in range(4):
                    mixed.append(
                        _mul(a[r], 2) ^ _mul(a[(r + 1) % 4], 3) ^ a[(r + 2) % 4] ^ a[(r + 3) % 4]
                    )
            s = mixed
        s = [a ^ b for a, b in zip(s, rounds[rnd])]
    return bytes(s)


def make_pak(path: Path, key: bytes | None = None, version: int = 8) -> Path:
    data = b"\0" * 64
    index = struct.pack("<i", 10) + b"../../../\0" + b"\0" * 2
    if key:
        index = encrypt_block(key, index)
    footer = b"\0" * 16 + bytes([1 if key else 0]) + PAK_MAGIC
    footer += struct.pack("<IQQ", version, len(data), len(index)) + b"\0" * 20 + b"\0" * 160
    path.write_bytes(data + index + footer)
    return path


def key_exe(path: Path, key: bytes) -> Path:
    movs = b"".join(
        b"\xc7\x45" + struct.pack("<b", -32 + 4 * i) + key[i * 4 : i * 4 + 4] for i in range(8)
    )
    path.write_bytes(b"MZ" + b"\x90" * 5000 + movs + b"\xc3" * 5000)
    return path


FAKE = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
key = args[args.index("--aes-key") + 1] if "--aes-key" in args else ""
src = Path(args[-1] if "{tool}" == "repak" else args[-2])
out = Path(args[args.index("--output") + 1] if "{tool}" == "repak" else args[-1])
if src.read_bytes()[-245 + 16 : -245 + 17] == b"\\x01" and key != "0x{key}":
    sys.exit("AES key needed or wrong")
(out / "Game" / "Content").mkdir(parents=True, exist_ok=True)
(out / "Game" / "Content" / "Hero.uasset").write_bytes(b"\\xc1\\x83\\x2a\\x9e" + src.name.encode())
"""


def fake_tools(folder: Path) -> str:
    lines = []
    for tool in ("repak", "retoc"):
        script = folder / f"fake_{tool}.py"
        script.write_text(FAKE.format(python=sys.executable, tool=tool, key=KEY.hex()))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        path = script
        if sys.platform == "win32":
            path = folder / f"fake_{tool}.cmd"
            path.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
        lines.append(f"{tool} = {path}")
    return "[plugins]\nunreal = on\n[tools]\n" + "\n".join(lines) + "\n"


class CryptoTests(unittest.TestCase):
    def test_fips_197_vector_and_round_trip(self) -> None:
        key, plain = bytes(range(32)), bytes.fromhex("00112233445566778899aabbccddeeff")
        cipher = bytes.fromhex("8ea2b7ca516745bfeafc49904b496089")
        self.assertEqual(decrypt_block(key, cipher), plain)
        self.assertEqual(encrypt_block(key, plain), cipher)

    def test_key_parsing_and_finder(self) -> None:
        self.assertEqual(parse_key("0x" + KEY.hex()), KEY)
        self.assertEqual(parse_key(__import__("base64").b64encode(KEY).decode()), KEY)
        self.assertIsNone(parse_key("abc"))
        with tempfile.TemporaryDirectory() as tmp:
            exe = key_exe(Path(tmp) / "Game-Win64-Shipping.exe", KEY)
            self.assertIn(KEY, _from_movs(exe.read_bytes()))


class IdentifyTests(unittest.TestCase):
    def test_footer_versions_and_other_paks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            info = pak_info(make_pak(root / "a.pak", KEY))
            self.assertEqual((info.version, info.encrypted_index), (8, True))
            self.assertFalse(pak_info(make_pak(root / "b.pak", version=3)).encrypted_index)
            (root / "quake.pak").write_bytes(b"PACK" + b"\0" * 300)
            self.assertIsNone(identify(root / "quake.pak", SLOTS))
            self.assertEqual(identify(root / "a.pak", SLOTS).slot_id, "unarchive.upak")
            (root / "global.utoc").write_bytes(UTOC_MAGIC + b"\0" * 100)
            self.assertEqual(identify(root / "global.utoc", SLOTS).slot_id, "unarchive.utoc")
            self.assertEqual(UnrealPlugin().detect(FolderProbe(root)).confidence, 0.92)


class UnrealPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.game = self.root / "game"
        (self.game / "Game" / "Content" / "Paks").mkdir(parents=True)
        self.paks = self.game / "Game" / "Content" / "Paks"
        self.rt = runtime(self.root, fake_tools(self.root))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_it(self, **options):
        self.runs = getattr(self, "runs", 0) + 1
        request = ExtractionRequest(
            str(self.game),
            str(self.root / f"ws{self.runs}"),
            plugins=("unreal",),
            plugin_options={"unreal": options},
        )
        events = []
        result = extract(self.rt, request, "j", events.append, CancelToken())
        return result, [e.message for e in events]

    def test_plain_and_encrypted_with_key_from_the_executable(self) -> None:
        make_pak(self.paks / "pakchunk0-Windows.pak")
        make_pak(self.paks / "pakchunk1-Windows.pak", KEY)
        key_exe(self.game / "Game-Win64-Shipping.exe", KEY)
        before = tree_hashes(self.game)
        result, messages = self.run_it()
        self.assertEqual(result.archives_extracted, 2, result.warnings)
        self.assertTrue(any("AES key found" in m for m in messages))
        self.assertFalse(any(KEY.hex() in m for m in messages))  # the key is never logged
        self.assertEqual(
            sorted(p.name for p in (self.root / "ws1" / "uasset").iterdir()),
            ["Hero.uasset", "Hero__1.uasset"],
        )
        self.assertEqual(tree_hashes(self.game), before)

    def test_missing_key_is_needs_key_and_user_key_wins(self) -> None:
        make_pak(self.paks / "pakchunk1-Windows.pak", KEY)
        key_exe(self.game / "Game-Win64-Shipping.exe", bytes(range(1, 33)))
        result, _ = self.run_it()
        self.assertEqual(result.archives_extracted, 0)
        self.assertTrue(any("needs_key" in w for w in result.warnings), result.warnings)
        result, _ = self.run_it(aes_key=KEY.hex(), find_key=False)
        self.assertEqual(result.archives_extracted, 1, result.warnings)


if __name__ == "__main__":
    unittest.main()
