"""L3: LÖVE games, property tests on `.love` zips and fused executables written here (the zip
appended after the executable's bytes, its offsets relative to its own start, as `copy /b` makes
it): every member comes out byte for byte; the rebuild keeps the executable's bytes and every
member the edit did not touch, carries every edit and every new member, and is read back by
LÖVE's own rule (PhysFS: what lies before the zip is worked out from the end record); a fused
executable is recognised only beside LÖVE's library; end to end, a member of a fused game is
extracted, edited and repacked into the patched copy, the game left as it was."""

from __future__ import annotations

import io
import random
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts.types import OutcomeKind
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.core.roundtrip import repack
from viwo.plugins.love2d import Love2dPlugin, LovePacker, LoveZip, identify_love

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


def love_zip(members: dict[str, bytes], rng: random.Random) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, data in members.items():
            kind = rng.choice((zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED))
            zf.writestr(name, data, compress_type=kind)
    return out.getvalue()


def members_of(rng: random.Random) -> dict[str, bytes]:
    names = {
        f"{rng.choice(['', 'assets/', 'lib/x/'])}f{i}.{rng.choice(['lua', 'png', 'ogg'])}"
        for i in range(rng.randint(1, 8))
    }
    return {
        "main.lua": b"function love.draw() end",
        **{n: rng.randbytes(rng.randint(0, 400)) for n in names},
    }


def physfs_members(blob: bytes) -> dict[str, bytes]:
    """The members as PhysFS finds them: from the end record, what lies before the zip is the
    distance between where the central directory is and where its offset says it is."""
    at = blob.rfind(b"PK\x05\x06")
    size, offset = struct.unpack_from("<II", blob, at + 12)
    start = at - (offset + size)
    with zipfile.ZipFile(io.BytesIO(blob[start:] if start else blob)) as zf:
        return {i.filename: zf.read(i) for i in zf.infolist()}


def read(archive: Path, out: Path) -> dict[str, bytes]:
    result = LoveZip().extract(archive, out, CTX)
    assert result.kind is OutcomeKind.OK, result.error
    return {f.relative_to(out).as_posix(): f.read_bytes() for f in out.rglob("*") if f.is_file()}


class LoveTests(unittest.TestCase):
    def test_love_and_fused_games_come_out_and_are_rebuilt_with_the_edits(self) -> None:
        rng = random.Random(51)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(30):
                folder = root / f"c{case}"
                folder.mkdir()
                members = members_of(rng)
                fused = case % 2 == 1
                stub = b"MZ" + rng.randbytes(rng.randint(50, 500)) if fused else b""
                archive = folder / ("game.exe" if fused else "game.love")
                archive.write_bytes(stub + love_zip(members, rng))
                (folder / "love.dll").write_bytes(b"MZ")
                blob = archive.read_bytes()
                self.assertIsNotNone(identify_love(archive, blob[:64], blob[-64:]))
                self.assertEqual(read(archive, folder / "out"), members)
                edits = {}
                for name in rng.sample(sorted(members), rng.randint(0, len(members))):
                    edits[name] = folder / f"e{len(edits)}"
                    edits[name].write_bytes(rng.randbytes(rng.randint(0, 300)))
                if rng.random() < 0.3:
                    edits["new/added.lua"] = folder / "added"
                    edits["new/added.lua"].write_text("return 1")
                done = LovePacker().pack(archive, edits, CTX)
                self.assertEqual(done.kind, OutcomeKind.OK, done.error)
                want = {**members, **{m: p.read_bytes() for m, p in edits.items()}}
                rebuilt = archive.read_bytes()
                self.assertEqual(rebuilt[: len(stub)], stub)  # the executable's own bytes
                self.assertEqual(physfs_members(rebuilt), want)
                self.assertEqual(read(archive, folder / "back"), want)

    def test_fused_needs_the_runtime_and_detection(self) -> None:
        rng = random.Random(52)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "game.exe"
            exe.write_bytes(b"MZ" + rng.randbytes(100) + love_zip({"main.lua": b"x"}, rng))
            blob = exe.read_bytes()
            self.assertIsNone(identify_love(exe, blob[:64], blob[-64:]))  # no love.dll beside
            self.assertIsNone(identify_love(root / "a.love", b"MZ", b""))
            self.assertEqual(Love2dPlugin().detect(FolderProbe(root)).confidence, 0.0)
            (root / "love.dll").write_bytes(b"MZ")
            self.assertEqual(Love2dPlugin().detect(FolderProbe(root)).confidence, 0.9)
            (root / "notzip.exe").write_bytes(b"MZ" + bytes(100))
            bad = LovePacker().pack(root / "notzip.exe", {}, CTX)
            self.assertEqual(bad.kind, OutcomeKind.FAILED)
            self.assertFalse((root / "notzip.exe.viwo-tmp").exists())  # nothing left behind
            loose = root / "src"
            loose.mkdir()
            (loose / "main.lua").write_text("")
            (loose / "conf.lua").write_text("")
            self.assertEqual(Love2dPlugin().detect(FolderProbe(loose)).confidence, 0.6)

    def test_a_fused_game_end_to_end(self) -> None:
        rng = random.Random(53)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "Blob"
            game.mkdir()
            stub = b"MZ" + rng.randbytes(300)
            members = {"main.lua": b"print('hi')", "assets/title.txt": b"Blob Quest"}
            (game / "Blob.exe").write_bytes(stub + love_zip(members, rng))
            (game / "love.dll").write_bytes(b"MZ")
            before = tree_hashes(game)
            rt, request = runtime(root), ExtractionRequest(str(game), str(root / "ws"))
            result = extract(rt, request, "j", lambda e: None, CancelToken())
            self.assertEqual(result.runs[0].plugin_id, "love2d", result.warnings)
            edited = next((root / "ws").rglob("title.txt"))
            edited.write_bytes(b"Blob Quest, edited")
            report = repack(rt, root / "ws", root / "copy")
            self.assertTrue(report["verified"], report)
            fused = (root / "copy" / "Blob.exe").read_bytes()
            self.assertEqual(fused[: len(stub)], stub)
            self.assertEqual(physfs_members(fused)["assets/title.txt"], b"Blob Quest, edited")
            self.assertEqual(tree_hashes(game), before)


if __name__ == "__main__":
    unittest.main()
