"""L4: Cyberpunk 2077 round trip (pack.archive). An edited member goes into an override archive in
the patched copy's `archive/pc/mod/`, named to load first; a member known by name is packed under
the game's hash of its path and one known only by its hash keeps that hash; the archive is read
back and every edited member that differs or is missing is named; a missing tool, a failed run
and a run that wrote no archive are said. End to end through a fake WolvenKit that writes a real
RDAR: extract, edit, repack, verified, the game untouched. Verified on real data: a texture of a
mod archive edited, packed by WolvenKit 9.1.0 and read back through the game's own Oodle."""

from __future__ import annotations

import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime, tree_hashes
from tests.test_redengine import cr2w, rdar
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts.types import OutcomeKind
from viwo.core.pipeline.runner import extract
from viwo.core.roundtrip import repack
from viwo.plugins.redengine.names import fnv1a64
from viwo.plugins.redengine.pack import PREFIX, WolvenKitPack, member_hash, stage

REPO = Path(__file__).resolve().parents[1]
FAKE = """import sys
from pathlib import Path
sys.path.insert(0, {repo!r})
from tests.test_redengine import rdar
from viwo.plugins.redengine.names import fnv1a64
args = sys.argv[1:]
root, out = Path(args[1]), Path(args[args.index("-o") + 1])
members = {{}}
for f in sorted(p for p in root.rglob("*") if p.is_file()):
    rel = f.relative_to(root)
    digits = rel.stem if rel.stem.isdigit() and len(rel.parts) == 1 else ""
    key = int(digits) if digits else fnv1a64(str(rel).replace("/", "\\\\").encode())
    members[key] = [f.read_bytes()]
(out / f"{{root.name}}.archive").write_bytes(rdar(members))
print("[ 0: Success ] - Finished packing")
"""


def fake_wolvenkit(folder: Path) -> Path:
    script = folder / "fake_wk_pack.py"
    script.write_text(FAKE.format(repo=str(REPO)))
    if sys.platform != "win32":
        script.write_text(f"#!{sys.executable}\n" + FAKE.format(repo=str(REPO)))
        script.chmod(0o755)
        return script
    wrapper = folder / "fake_wk_pack.cmd"
    wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
    return wrapper


def ctx(root: Path, run=None, located: bool = True):
    from viwo.os import select_os

    tool = SimpleNamespace(argv_prefix=(str(fake_wolvenkit(root)),))
    real = select_os()
    host = SimpleNamespace(
        tools=SimpleNamespace(locate=lambda s: tool if located else None),
        process=SimpleNamespace(run=run or real.process.run),
        load_native=real.load_native,
    )
    return SimpleNamespace(os=host, scratch=root / "scratch", cancel=None)


def random_members(rng: random.Random, folder: Path) -> dict[str, Path]:
    members = {}
    for i in range(rng.randint(1, 8)):
        if rng.random() < 0.5:
            name = f"{rng.getrandbits(64):016x}.{rng.choice(('mesh', 'xbm', 'ent'))}"
        else:
            name = f"base/dir{rng.randint(0, 3)}/file{i}.{rng.choice(('mesh', 'xbm'))}"
        source = folder / f"edit{i}"
        source.write_bytes(rng.randbytes(rng.randint(0, 300)))
        members[name] = source
    return members


class UnitTests(unittest.TestCase):
    def test_the_hash_is_the_games_and_a_hash_name_keeps_its_own(self) -> None:
        rng = random.Random(1)
        for _ in range(50):
            value = rng.getrandbits(64)
            self.assertEqual(member_hash(f"{value:016x}.mesh"), value)
        self.assertEqual(member_hash("base/a/b.mesh"), fnv1a64(b"base\\a\\b.mesh"))
        self.assertEqual(member_hash("00ce2b7fd745dfab"), fnv1a64(b"00ce2b7fd745dfab"))  # no ext

    def test_staging_writes_every_safe_member_once(self) -> None:
        rng = random.Random(2)
        with tempfile.TemporaryDirectory() as tmp:
            members = random_members(rng, Path(tmp))
            members["../escape.mesh"] = next(iter(members.values()))
            root = Path(tmp) / "stage"
            self.assertEqual(stage(members, root), len(members) - 1)  # the unsafe one skipped
            for member in members:
                if member.startswith(".."):
                    continue
                head = member.split(".")[0]
                rel = str(int(head, 16)) + member[16:] if len(head) == 16 else member
                self.assertTrue((root / rel).is_file(), rel)
            self.assertFalse((Path(tmp) / "escape.mesh").exists())

    def test_the_override_loads_from_the_mod_folder_first(self) -> None:
        for folder in ("content", "mod"):
            out = WolvenKitPack().output_for(Path("g/archive/pc") / folder / "basegame_1.archive")
            self.assertEqual(out, Path("g/archive/pc/mod") / f"{PREFIX}basegame_1.archive")
        self.assertLess(PREFIX, "0")  # before every name that starts with a digit or letter


class PackTests(unittest.TestCase):
    def test_every_edit_is_packed_and_read_back_and_damage_is_named(self) -> None:
        rng = random.Random(3)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            container = root / "archive" / "pc" / "content" / "basegame_1.archive"
            container.parent.mkdir(parents=True)
            for n in range(6):
                members = random_members(rng, root)
                packer, c = WolvenKitPack(), ctx(root)
                out = packer.pack(container, members, c)
                self.assertEqual((out.kind, out.files), (OutcomeKind.OK, len(members)))
                packed = packer.output_for(container)
                self.assertEqual(packer.verify(packed, members, c), [])
                victim = rng.choice(sorted(members))
                members[victim].write_bytes(members[victim].read_bytes() + b"!")
                ghost = root / "ghost"
                ghost.write_bytes(b"never packed")
                bad = packer.verify(packed, {**members, "base/ghost.mesh": ghost}, c)
                self.assertEqual(sorted(bad), sorted([victim, "base/ghost.mesh"]))

    def test_every_failure_is_said(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            container = root / "archive" / "pc" / "content" / "a.archive"
            members = {"base/x.mesh": root / "x"}
            (root / "x").write_bytes(b"x")
            gone = WolvenKitPack().pack(container, members, ctx(root, located=False))
            self.assertEqual(gone.kind, OutcomeKind.UNAVAILABLE)
            crash = SimpleNamespace(ok=False, stdout="", stderr="Unhandled exception\n")
            out = WolvenKitPack().pack(container, members, ctx(root, lambda *a, **k: crash))
            self.assertEqual((out.kind, out.error), (OutcomeKind.FAILED, "Unhandled exception"))
            quiet = SimpleNamespace(ok=True, stdout="", stderr="")
            out = WolvenKitPack().pack(container, members, ctx(root, lambda *a, **k: quiet))
            self.assertEqual(out.error, "WolvenKit wrote no archive")


class RoundTripTests(unittest.TestCase):
    def test_extract_edit_repack_verified_and_the_game_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "cp"
            content = game / "archive" / "pc" / "content"
            content.mkdir(parents=True)
            (game / "REDprelauncher.exe").write_bytes(b"MZ")
            members = {0x1234: [cr2w("CMesh"), b"buffer"], 0x99: [b"KB2jvideo"]}
            (content / "basegame_1.archive").write_bytes(rdar(members))
            before = tree_hashes(game)
            rt = runtime(root, f"[tools]\nwolvenkit = {fake_wolvenkit(root)}\n")
            ws = root / "ws"
            request = ExtractionRequest(str(game), str(ws))
            extract(rt, request, "j", lambda e: None, CancelToken())
            edited = ws / "mesh" / "0000000000001234.mesh"
            edited.write_bytes(edited.read_bytes() + b"-edited")
            report = repack(rt, ws, root / "patched")
            self.assertTrue(report["verified"], report)
            [item] = [r for r in report["results"] if r["slot"] == "pack.archive"]
            self.assertEqual(item["output"], f"archive/pc/mod/{PREFIX}basegame_1.archive")
            self.assertEqual(tree_hashes(game), before)  # the game is never written


if __name__ == "__main__":
    unittest.main()
