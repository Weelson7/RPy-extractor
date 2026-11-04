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


def _ctx(root: Path, run, located=True, key_problem=""):
    from types import SimpleNamespace

    tool = SimpleNamespace(argv_prefix=("tool",), path="tool")
    return SimpleNamespace(
        os=SimpleNamespace(
            tools=SimpleNamespace(locate=lambda spec: tool if located else None),
            process=SimpleNamespace(run=run),
        ),
        cancel=None,
        scratch=root / "scratch",
        options={},
        tool_output=lambda *a, **k: None,
    )


def _tool(ok: bool = True, stderr: str = "", seen: list | None = None):
    """A fake process runner answering ok or not, recording each argv in `seen`."""
    from types import SimpleNamespace

    def run(argv, **kw):
        if seen is not None:
            seen.append(argv)
        return SimpleNamespace(ok=ok, stderr=stderr, stdout="", returncode=0 if ok else 1)

    return run


class PakPropertyTests(unittest.TestCase):
    def test_footers_never_lie_or_raise(self) -> None:
        import random

        rng = random.Random(6)
        for _ in range(500):
            tail = bytearray(rng.randbytes(rng.randint(0, 300)))
            if rng.random() < 0.6 and len(tail) > 30:
                at = rng.randrange(len(tail) - 4)
                tail[at : at + 4] = PAK_MAGIC
            info = pak_info(Path("x.pak"), bytes(tail))
            if info is not None:
                at = bytes(tail).rfind(PAK_MAGIC)
                self.assertTrue(1 <= info.version <= 15)
                self.assertEqual(info.version, struct.unpack_from("<I", tail, at + 4)[0])

    def test_unpack_failures_are_classified_and_the_key_never_shown(self) -> None:
        from types import SimpleNamespace

        from viwo.contracts.types import OutcomeKind
        from viwo.plugins.unreal.pak import RepakCli, RetocLegacy, RetocUnpack

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pak = make_pak(root / "a.pak", KEY)
            hexkey = KEY.hex()
            self.assertEqual(
                RepakCli().extract(pak, root, _ctx(root, None, located=False)).kind,
                OutcomeKind.UNAVAILABLE,
            )
            for said, kind in (
                (f"wrong AES key 0x{hexkey}", OutcomeKind.NEEDS_KEY),
                (f"Encrypted index, key {hexkey.upper()}", OutcomeKind.NEEDS_KEY),
                (f"disk full while writing ({hexkey})", OutcomeKind.FAILED),
            ):
                run = lambda argv, s=said, **k: SimpleNamespace(  # noqa: E731
                    ok=False, stderr=s, stdout="", returncode=1
                )
                ctx = _ctx(root, run)
                ctx.options = {"aes_key": "0x" + hexkey}
                out = RepakCli().extract(pak, root / "o", ctx)
                self.assertEqual(out.kind, kind, said)
                self.assertNotIn(hexkey, out.error.lower())  # never shown back
            self.assertEqual(RetocLegacy().argv(Path("g.utoc"), Path("d"))[0], "to-legacy")
            self.assertEqual(RetocUnpack().argv(Path("g.utoc"), Path("d"))[0], "unpack")

    def test_patch_paks_use_the_games_version_and_count_what_was_packed(self) -> None:

        from viwo.contracts.types import OutcomeKind
        from viwo.plugins.unreal.pak import REPAK_VERSIONS, RepakPatch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "edit.uasset"
            src.write_bytes(b"edited")
            members = {"Game/Content/Hero.uasset": src, "../escape.uasset": src}
            for version in (3, 8, 11):
                pak = make_pak(root / f"v{version}.pak", version=version)
                seen = []
                out = RepakPatch().pack(pak, members, _ctx(root, _tool(seen=seen)))
                self.assertEqual(seen[0][seen[0].index("--version") + 1], REPAK_VERSIONS[version])
                self.assertEqual(seen[0][-1], str(root / f"v{version}_P.pak"))
                self.assertEqual(out.files, 1)  # the unsafe member was never packed
                self.assertEqual(out.notes, ())
            (root / "v8.sig").write_bytes(b"sig")
            fail = _tool(ok=False, stderr="locked")
            self.assertEqual(
                RepakPatch().pack(pak, members, _ctx(root, fail)).kind, OutcomeKind.FAILED
            )
            ok = _tool()
            signed = RepakPatch().pack(root / "v8.pak", members, _ctx(root, ok))
            self.assertIn("signed game", signed.notes[0])
            missing = RepakPatch().pack(pak, members, _ctx(root, None, located=False))
            self.assertEqual(missing.kind, OutcomeKind.UNAVAILABLE)
            with open(root / "short.pak", "wb") as fh:
                fh.write(b"\0" * 8)
            from viwo.plugins.unreal.pak import PakInfo, key_opens

            self.assertFalse(key_opens(root / "short.pak", PakInfo(8, 1 << 20, 16, True), KEY))


class KeyPropertyTests(unittest.TestCase):
    def test_any_spelling_of_a_key_parses_to_it_and_nothing_else_does(self) -> None:
        import base64
        import random

        from viwo.plugins.unreal.keys import parse_key

        rng = random.Random(9)
        for _ in range(200):
            key = rng.randbytes(32)
            for text in (
                key.hex(),
                "0x" + key.hex().upper(),
                base64.b64encode(key).decode().rstrip("="),
            ):
                self.assertEqual(parse_key(f"  {text} "), key)
            short = rng.randbytes(rng.choice([0, 16, 31, 33]))
            self.assertIsNone(parse_key(short.hex()))
            self.assertIsNone(parse_key("not a key !" * rng.randint(1, 4)))

    def test_every_reason_a_key_is_missing_is_said(self) -> None:
        from types import SimpleNamespace

        from viwo.plugins.unreal.keys import ENCRYPTED, UTOC_FLAGS, resolve_key

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            utoc = root / "g.utoc"
            utoc.write_bytes(bytes(UTOC_FLAGS) + bytes([ENCRYPTED]) + bytes(20))
            plain = root / "plain.utoc"
            plain.write_bytes(bytes(UTOC_FLAGS + 21))
            ctx = SimpleNamespace(options={}, game_root=root, log=lambda *a, **k: None)
            self.assertEqual(resolve_key(plain, ctx), ("", ""))  # nothing to unlock
            self.assertIn("give the AES key", resolve_key(utoc, ctx)[1])  # no pak to verify on
            make_pak(root / "g.pak", KEY)
            ctx.options = {"find_key": False}
            self.assertIn("give the AES key", resolve_key(utoc, ctx)[1])
            ctx.options = {}
            self.assertIn("no key in the game's executables", resolve_key(utoc, ctx)[1])
            key_exe(root / "Game.exe", KEY)
            self.assertEqual(resolve_key(utoc, ctx), (KEY.hex(), ""))  # found and verified
            ctx.options = {"aes_key": "0x12"}
            self.assertIn("32 bytes", resolve_key(utoc, ctx)[1])


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
