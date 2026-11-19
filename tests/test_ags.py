"""L3: AGS CLIB packfiles, property tests on libraries written here byte by byte in every version
the engine reads (6, 10, 11, 15, 20, 21, 30), alone or behind an executable (64- or 32-bit tail
offset), with multi-file parts: every asset comes out byte for byte (a part's from its file, a
missing part's named), an unchanged library is rebuilt byte for byte, an edited one reads back with
the edits and every other asset as it was (an edited asset of another part moved into the first);
unknown versions and damage are named failures; end to end, an asset of a library behind the game's
executable is extracted, edited and repacked into the patched copy, the game left as it was."""

from __future__ import annotations

import random
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts.types import OutcomeKind
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.core.roundtrip import repack
from viwo.plugins.ags import AgsPlugin, ClibBuiltin, identify_clib
from viwo.plugins.ags.clib import HEAD, KEY, SEED, TAIL, next_rand, read_lib
from viwo.plugins.ags.pack import ClibWriter

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


class Enc:
    """Version 21's stream: each byte plus the generator's next value."""

    def __init__(self, seed: int) -> None:
        self.state = (seed + SEED) & 0xFFFFFFFF

    def __call__(self, raw: bytes) -> bytes:
        out = bytearray()
        for b in raw:
            self.state, r = next_rand(self.state)
            out.append((b + r) & 0xFF)
        return bytes(out)


def text_key(name: str, width: int, rng: random.Random) -> bytes:
    raw = bytes((c + KEY[i % len(KEY)]) & 0xFF for i, c in enumerate(name.encode() + b"\0"))
    return raw + rng.randbytes(width - len(raw)) if width else raw


def _toc(version: int, assets: list, parts: list, offsets: list, rng: random.Random) -> bytes:
    """The table after `CLIB\\x1a`, the version and the part index (versions 10+)."""
    n, sizes, uids = len(assets), [len(a[1]) for a in assets], [a[2] for a in assets]
    if version == 30:
        out = struct.pack("<iI", 0, len(parts)) + b"".join(p.encode() + b"\0" for p in parts)
        out += struct.pack("<I", n)
        for (name, data, uid), offset in zip(assets, offsets):
            out += name.encode() + b"\0" + struct.pack("<Bqq", uid, offset, len(data))
        return out
    arrays = struct.pack(f"<{n}I{n}I{n}B", *offsets, *sizes, *uids)
    if version == 21:
        seed = rng.getrandbits(31)
        enc = Enc(seed)
        out = struct.pack("<i", seed) + enc(struct.pack("<I", len(parts)))
        out += b"".join(enc(p.encode() + b"\0") for p in parts) + enc(struct.pack("<I", n))
        return out + b"".join(enc(a[0].encode() + b"\0") for a in assets) + enc(arrays)
    if version == 20:
        out = struct.pack("<I", len(parts)) + b"".join(p.encode() + b"\0" for p in parts)
        out += struct.pack("<I", n)
        for name, _, _ in assets:
            out += struct.pack("<h", (len(name) + 1) * 5) + text_key(name, 0, rng)
        return out + arrays
    out = struct.pack("<I", len(parts)) + b"".join(p.encode().ljust(20, b"\0") for p in parts)
    out += struct.pack("<I", n)
    for name, _, _ in assets:
        plain = name.encode() + b"\0"
        out += text_key(name, 25, rng) if version >= 11 else plain + rng.randbytes(25 - len(plain))
    return out + arrays


def _v6(assets: list, rng: random.Random) -> bytes:
    shift, n = rng.randint(1, 100), len(assets)
    names = b"".join(bytes(c + shift for c in a[0].encode()).ljust(13, b"\0") for a in assets)
    head = HEAD + b"\x06" + bytes([shift, 0]) + struct.pack("<H", n) + rng.randbytes(13)
    sizes = struct.pack(f"<{n}I", *(len(a[1]) for a in assets))
    return head + names + sizes + rng.randbytes(2 * n) + b"".join(a[1] for a in assets)


def library(version: int, assets: list, parts: list, rng: random.Random) -> bytes:
    """assets: [(name, data, part)]; the first part's data follows the table in its order."""
    if version == 6:
        return _v6(assets, rng)
    head = HEAD + bytes([version, 0])
    state = rng.getstate()
    size = len(head) + len(_toc(version, assets, parts, [0] * len(assets), rng))
    offsets, at, other = [], size, {}
    for _, data, uid in assets:
        if uid:
            offsets.append(6 + 1 + other.get(uid, 0))  # in its part, after its own header
            other[uid] = other.get(uid, 0) + len(data)
        else:
            offsets.append(at)
            at += len(data)
    rng.setstate(state)  # the same seed and padding
    toc = _toc(version, assets, parts, offsets, rng)
    return head + toc + b"".join(d for _, d, uid in assets if uid == 0)


def part(version: int, index: int, assets: list) -> bytes:
    return HEAD + bytes([version, index]) + b"".join(d for _, d, uid in assets if uid == index)


def behind(lib: bytes, version: int, rng: random.Random, wide: bool) -> bytes:
    stub = b"MZ" + rng.randbytes(rng.randint(10, 300))
    offset = struct.pack("<q" if wide else "<i", len(stub))
    return stub + lib + offset + TAIL


def random_assets(rng: random.Random, version: int, parts: int) -> list:
    letters = "abcdefghijklmnopqrstuvwxyz"
    names = {
        "".join(rng.choice(letters) for _ in range(rng.randint(1, 8))) + ".dat" for _ in range(6)
    }
    uids = [0] if version == 6 else list(range(parts))
    return [(n, rng.randbytes(rng.randint(0, 200)), rng.choice(uids)) for n in sorted(names)]


def read(archive: Path, out: Path) -> dict:
    result = ClibBuiltin().extract(archive, out, CTX)
    assert result.kind is OutcomeKind.OK, result.error
    return {f.name: f.read_bytes() for f in out.rglob("*") if f.is_file()}


class ClibTests(unittest.TestCase):
    def test_every_version_comes_out_and_is_rebuilt_byte_for_byte(self) -> None:
        rng = random.Random(41)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(42):
                version = (6, 10, 11, 15, 20, 21, 30)[case % 7]
                assets = random_assets(rng, version, 2 if case % 3 == 0 else 1)
                parts = ["game.ags", "game.001"]
                lib = library(version, assets, parts, rng)
                folder = root / f"c{case}"
                folder.mkdir()
                if case % 2 and version != 6:
                    blob = behind(lib, version, rng, wide=version >= 30 or case % 4 == 1)
                else:
                    blob = lib
                archive = folder / ("game.exe" if blob is not lib else "game.ags")
                archive.write_bytes(blob)
                if any(uid for _, _, uid in assets):
                    (folder / "game.001").write_bytes(part(version, 1, assets))
                self.assertIsNotNone(identify_clib(archive, blob[:64], blob[-64:]))
                self.assertEqual(read(archive, folder / "out"), {n: d for n, d, _ in assets})
                self.assertEqual(ClibWriter().pack(archive, {}, CTX).kind, OutcomeKind.OK)
                self.assertEqual(archive.read_bytes(), blob, (case, version))

    def test_edits_read_back_and_parts_move_into_the_first(self) -> None:
        rng = random.Random(42)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(42):
                version = (6, 10, 11, 15, 20, 21, 30)[case % 7]
                assets = random_assets(rng, version, 2)
                lib = library(version, assets, ["game.ags", "game.001"], rng)
                folder = root / f"c{case}"
                folder.mkdir()
                archive = folder / ("game.exe" if case % 2 and version != 6 else "game.ags")
                blob = behind(lib, version, rng, version >= 30) if archive.suffix == ".exe" else lib
                archive.write_bytes(blob)
                (folder / "game.001").write_bytes(part(version, 1, assets))
                edits = {}
                for name, _, _ in rng.sample(assets, rng.randint(1, len(assets))):
                    edits[name] = folder / f"{name}.edit"
                    edits[name].write_bytes(rng.randbytes(rng.randint(0, 300)))
                base = read_lib(archive).base
                done = ClibWriter().pack(archive, edits, CTX)
                self.assertEqual(done.kind, OutcomeKind.OK, done.error)
                (folder / "game.001").unlink()  # every edit is in the first part now
                got = read(archive, folder / "out")
                for name, data, uid in assets:
                    if name in edits:
                        self.assertEqual(got[name], edits[name].read_bytes())
                    elif uid == 0:
                        self.assertEqual(got[name], data)
                self.assertEqual(archive.read_bytes()[:base], blob[:base])  # the executable kept
                self.assertEqual(
                    (read_lib(archive).version, read_lib(archive).base), (version, base)
                )

    def test_parts_unknown_versions_and_damage_are_named(self) -> None:
        rng = random.Random(43)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = [("a.dat", b"aa", 0), ("b.dat", b"bb", 1)]
            (root / "game.ags").write_bytes(library(30, assets, ["game.ags", "game.001"], rng))
            done = ClibBuiltin().extract(root / "game.ags", root / "o", CTX)
            self.assertEqual(done.files, 1)
            self.assertIn("game.001", done.notes[0])  # the missing part is named
            (root / "game.001").write_bytes(part(30, 1, assets))
            done = ClibBuiltin().extract(root / "game.001", root / "p", CTX)
            self.assertEqual((done.files, done.notes[0][:6]), (0, "part 1"))
            (root / "new.ags").write_bytes(HEAD + b"\x1f\x00" + bytes(20))
            self.assertIn(
                "version 31", ClibBuiltin().extract(root / "new.ags", root / "n", CTX).error
            )
            self.assertIsNone(identify_clib(root / "x.exe", b"MZ", b"MZ" * 32))
            for _ in range(300):
                version = rng.choice((6, 10, 11, 20, 21, 30))
                blob = bytearray(library(version, random_assets(rng, version, 1), ["g"], rng))
                if rng.random() < 0.5:
                    blob = blob[: rng.randrange(len(blob))]
                else:
                    blob[rng.randrange(len(blob))] ^= 1 << rng.randrange(8)
                (root / "d.ags").write_bytes(bytes(blob))
                ClibBuiltin().extract(root / "d.ags", root / "d", CTX)  # a result, never a crash

    def test_detection_and_an_edit_behind_the_executable_end_to_end(self) -> None:
        rng = random.Random(44)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "Quest"
            game.mkdir()
            assets = [("room1.crm", b"room one", 0), ("game28.dta", b"game data", 0)]
            (game / "Quest.exe").write_bytes(
                behind(library(21, assets, ["Quest.exe"], rng), 21, rng, False)
            )
            (game / "acsetup.cfg").write_text("[misc]\n")
            self.assertEqual(AgsPlugin().detect(FolderProbe(game)).confidence, 0.9)
            before = tree_hashes(game)
            rt, request = runtime(root), ExtractionRequest(str(game), str(root / "ws"))
            result = extract(rt, request, "j", lambda e: None, CancelToken())
            self.assertEqual(result.runs[0].plugin_id, "ags", result.warnings)
            edited = next((root / "ws").rglob("room1.crm"))
            self.assertEqual(edited.read_bytes(), b"room one")
            edited.write_bytes(b"room one, repainted")
            report = repack(rt, root / "ws", root / "copy")
            self.assertTrue(report["verified"], report)
            got = read(root / "copy" / "Quest.exe", root / "back")
            self.assertEqual(got, {"room1.crm": b"room one, repainted", "game28.dta": b"game data"})
            self.assertEqual(tree_hashes(game), before)  # the game: only read


if __name__ == "__main__":
    unittest.main()
