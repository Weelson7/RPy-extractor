"""L3: the guards the third audit added. Every built-in unpacker keeps a member whose name
Windows cannot write under an altered name, records the original (provenance gives it, so the
round trip writes the member back under it) and says so; it counts what it skips by reason (a
name that leads out, a part file that is missing, an archive cut short), the run lists every
note among its warnings, and nothing lands outside the destination. A zero
declared size never means "inflate without a limit". A crafted SLP row or Doom column that
runs on past its size is refused, a legit one still decodes. An MV System.json key that does
not open the images is replaced by the one the PNG signature gives, and said. A junction in a
game folder is never walked into. Two Lua chunks of one stem both get a decompiled file."""

from __future__ import annotations

import io
import json
import os
import pickle
import random
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import runtime, tree_hashes
from tests.test_containers import tpac
from tests.test_formats import asar, ba2, bsa, vpk
from tests.test_renpy import make_rpa
from tests.test_rpgmaker import KEY, encrypt_mv, rgssad_v3
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts import workspace as ws
from viwo.contracts.types import OutcomeKind

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))
UNSAFE = ("con.txt", "a:b.txt", "y.txt ", "nul.png", "c:evil.txt")


def _names(rng: random.Random) -> tuple[dict[str, bytes], int]:
    """Random members, some under a name no OS may write; (members, how many unsafe)."""
    files = {f"d{rng.randint(0, 2)}/f{i}.bin": rng.randbytes(rng.randint(1, 90)) for i in range(6)}
    bad = rng.sample(UNSAFE, rng.randint(0, 3))
    files.update({f"d0/{name}": b"bad" for name in bad})
    return files, len(bad)


def _said(notes, words: str) -> int:
    """The count a note gives for a reason, 0 when no note names it."""
    found = [int(n.split()[0]) for n in notes if words in n]
    return found[0] if found else 0


def _outside(root: Path) -> set[Path]:
    """Files neither an archive (a*) nor under an out* destination."""
    return {
        p for p in root.rglob("*")
        if p.is_file() and not p.relative_to(root).parts[0].startswith(("out", "a"))
    }  # fmt: skip


class UnsafeNamesTests(unittest.TestCase):
    def test_every_unpacker_keeps_an_unwritable_name_altered_and_records_it(self) -> None:
        from viwo.plugins.bethesda import Ba2Builtin, BsaBuiltin
        from viwo.plugins.electron import AsarBuiltin
        from viwo.plugins.renpy.rpa import RpaSafe
        from viwo.plugins.rpgmaker.rgss import RgssadBuiltin
        from viwo.plugins.source import VpkBuiltin
        from viwo.plugins.taleworlds import TpacBuiltin

        builders = {
            "asar": (AsarBuiltin, ".asar", asar),
            "ba2": (Ba2Builtin, ".ba2", ba2),
            "bsa": (BsaBuiltin, ".bsa", lambda f: bsa({k.split("/")[-1]: v for k, v in f.items()})),
            "rgss": (RgssadBuiltin, ".rgss3a", lambda f: rgssad_v3(f)),
            "vpk": (VpkBuiltin, "_dir.vpk", lambda f: vpk({k: (v, 0) for k, v in f.items()})[0]),
            "tpac": (TpacBuiltin, ".tpac", lambda f: tpac({k: [v] for k, v in f.items()})),
        }
        rng = random.Random(31)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(24):
                kind = rng.choice(sorted(builders) + ["rpa"])
                files, bad = _names(rng)
                archive = root / f"a{case}{builders.get(kind, (0, '.rpa'))[1]}"
                if kind == "rpa":
                    make_rpa(archive, files)
                    backend = RpaSafe()
                else:
                    backend_type, _, build = builders[kind]
                    archive.write_bytes(build(files))
                    backend = backend_type()
                dest = root / f"out{case}"
                dest.mkdir()
                out = backend.extract(archive, dest, CTX)
                self.assertEqual(out.kind, OutcomeKind.OK, (kind, out.error))
                self.assertEqual(_said(out.notes, "altered"), bad, (kind, out.notes))
                record = ws.renamed(dest)
                self.assertEqual(len(record), bad, kind)
                originals = {orig: dest / alt for alt, orig in record.items()}
                if kind == "tpac":  # one .<n>.bin per segment: the record names the item
                    continue
                self.assertEqual(out.files, len(files), kind)  # every member out, none lost
                for name, data in files.items():
                    name = f"textures/ui/{name.split('/')[-1]}" if kind == "bsa" else name
                    self.assertEqual(originals.get(name, dest / name).read_bytes(), data, name)
                self.assertEqual(_outside(root), set())


class CutShortTests(unittest.TestCase):
    def test_an_archive_cut_short_says_what_it_lost(self) -> None:
        from viwo.plugins.electron import AsarBuiltin
        from viwo.plugins.rpgmaker.rgss import RgssadBuiltin
        from viwo.plugins.taleworlds import TpacBuiltin

        rng = random.Random(32)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(12):
                files = {f"f{i}.bin": rng.randbytes(rng.randint(20, 80)) for i in range(4)}
                kind, backend = rng.choice(
                    [("asar", AsarBuiltin()), ("rgss", RgssadBuiltin()), ("tpac", TpacBuiltin())]
                )
                blob = {"asar": asar, "rgss": rgssad_v3}.get(kind, lambda f: None)(files)
                if kind == "tpac":
                    blob = tpac({k: [v] for k, v in files.items()})
                cut = rng.randint(1, 15)  # inside the last member's data
                archive = root / f"c{case}.{kind}"
                archive.write_bytes(blob[:-cut])
                dest = root / f"out{case}"
                dest.mkdir()
                out = backend.extract(archive, dest, CTX)
                self.assertEqual(out.kind, OutcomeKind.OK, out.error)
                self.assertEqual(_said(out.notes, "cut short"), 1, (kind, out.notes))
                self.assertEqual(len(list(dest.rglob("*.bin*"))), len(files) - 1, kind)

    def test_vpk_counts_a_missing_part_and_a_short_one(self) -> None:
        from viwo.plugins.source import VpkBuiltin

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vdir, part = vpk({"a/x.bin": (b"x" * 40, 0), "b/y.bin": (b"y" * 50, 1)})
            (root / "p_dir.vpk").write_bytes(vdir)
            (root / "o1").mkdir()
            out = VpkBuiltin().extract(root / "p_dir.vpk", root / "o1", CTX)
            self.assertEqual(_said(out.notes, "part file is missing"), 1, out.notes)
            (root / "p_000.vpk").write_bytes(part[:-7])
            (root / "o2").mkdir()
            out = VpkBuiltin().extract(root / "p_dir.vpk", root / "o2", CTX)
            self.assertEqual(_said(out.notes, "cut short"), 1, out.notes)

    def test_rpa_member_past_the_end_is_written_and_said(self) -> None:
        from viwo.plugins.renpy.rpa import RpaSafe

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = {"a.txt": [(25, 10**6, b"")], "../up.txt": [(25, 3, b"")]}
            make_rpa(root / "x.rpa", {}, "2.0", payload=pickle.dumps(index, protocol=2))
            (root / "o").mkdir()
            out = RpaSafe().extract(root / "x.rpa", root / "o", CTX)
            self.assertEqual(out.files, 1)
            self.assertEqual(_said(out.notes, "shorter than the index"), 1, out.notes)
            self.assertEqual(_said(out.notes, "leads out of the folder"), 1, out.notes)
            self.assertFalse((root / "up.txt").exists())

    def test_a_stored_xp3_segment_past_the_end_fails_and_zero_is_no_bomb(self) -> None:
        from viwo.plugins.kirikiri import _segment

        with self.assertRaises(ValueError):
            _segment(io.BytesIO(b"abc"), False, 0, 10, 10)
        bomb = zlib.compress(bytes(1 << 22))
        calls = []
        real = zlib.decompressobj

        class Spy:
            def __init__(self):
                self.inner = real()

            def decompress(self, data, limit=0):
                calls.append(limit)
                return self.inner.decompress(data, limit)

        with mock.patch.object(zlib, "decompressobj", Spy):
            with self.assertRaises(ValueError):
                _segment(io.BytesIO(bomb), True, 0, 0, len(bomb))
        self.assertEqual(calls, [1])  # a declared size of 0 still bounds the inflate


class RunSaysNotesTests(unittest.TestCase):
    def test_the_run_lists_every_unpacker_note_and_provenance_keeps_names(self) -> None:
        from viwo.core.pipeline.runner import extract

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            (game / "resources").mkdir(parents=True)
            (game / "electron.exe").write_bytes(b"MZ")
            (game / "resources" / "app.asar").write_bytes(asar({"a.txt": b"a", "con.txt": b"c"}))
            before = tree_hashes(game)
            result = extract(
                runtime(root), ExtractionRequest(str(game), str(root / "ws")), "j",
                lambda e: None, CancelToken(),
            )  # fmt: skip
            said = [f for f in result.warnings if "altered" in f]
            self.assertEqual(len(said), 1, result.warnings)
            self.assertIn("app.asar", said[0])
            records = (root / "ws" / ws.PROVENANCE_FILE).read_text().splitlines()
            members = {json.loads(r)["member"] for r in records}
            self.assertIn("con.txt", members)  # the archive's own name, for the round trip
            self.assertEqual(tree_hashes(game), before)


class WrapperExportTests(unittest.TestCase):
    def test_an_export_from_inside_a_wrapper_is_derived_never_mapped_to_the_game(self) -> None:
        import json

        from tests.helpers import make_png
        from viwo.core.pipeline.runner import extract

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            png = make_png(root / "p.png").read_bytes()
            inner = {
                "www/js/rpg_core.js": b"//mv",
                "www/data/System.json": json.dumps({"encryptionKey": KEY.hex()}).encode(),
                "www/img/a.rpgmvp": encrypt_mv(png),
            }
            game = root / "g"
            (game / "resources").mkdir(parents=True)
            (game / "electron.exe").write_bytes(b"MZ")
            (game / "resources" / "app.asar").write_bytes(asar(inner))
            result = extract(
                runtime(root), ExtractionRequest(str(game), str(root / "ws")), "j",
                lambda e: None, CancelToken(),
            )  # fmt: skip
            self.assertEqual([r.plugin_id for r in result.runs], ["electron", "rpgmaker"])
            records = [
                json.loads(line)
                for line in (root / "ws" / ws.PROVENANCE_FILE).read_text().splitlines()
            ]
            [image] = [r for r in records if r["path"] == "png/a.png"]
            self.assertEqual((image["kind"], image["container"]), ("derived", ""))
            self.assertEqual((root / "ws" / "png" / "a.png").read_bytes(), png)


class UnluacNamesTests(unittest.TestCase):
    def test_two_chunks_of_one_stem_both_keep_their_lua(self) -> None:
        from viwo.core.analysis import managed

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunks = [root / "a" / "main.lua", root / "b" / "main.luac", root / "main.out"]
            for chunk in chunks:
                chunk.parent.mkdir(exist_ok=True)
                chunk.write_bytes(b"Lua")

            def run(ctx, argv, env):
                Path(argv[argv.index("--output") + 1]).write_text(f"-- {argv[-1]}")
                return SimpleNamespace(timed_out=False)

            tool = SimpleNamespace(argv_prefix=("unluac",))
            ctx = SimpleNamespace(
                os=SimpleNamespace(tools=SimpleNamespace(locate=lambda spec: tool)),
                staging=root / "out", log=lambda *a, **k: None,
            )  # fmt: skip
            ctx.staging.mkdir()
            with (
                mock.patch.object(managed, "_run", run),
                mock.patch.object(managed, "java_env", return_value={}),
            ):
                out = managed.Unluac().analyze(SimpleNamespace(paths=chunks), ctx)
            self.assertEqual(out.files, 3)
            sources = sorted(p.read_text() for p in ctx.staging.iterdir())
            self.assertEqual(sources, sorted(f"-- {c}" for c in chunks))


class CraftedImageTests(unittest.TestCase):
    def test_a_row_or_column_that_runs_on_is_refused(self) -> None:
        from tests.test_doom import make_picture
        from viwo.plugins.doom.lumps import picture
        from viwo.plugins.genie.slp import _row

        colors = [(i, i, i, 255) for i in range(256)]
        with self.assertRaises(ValueError):
            _row(b"\x00" * 5000 + b"\x0f", 0, colors, 10)  # empty copies, never a pixel
        palette = bytes(range(256)) * 3
        self.assertIsNotNone(picture(make_picture(), palette))
        endless = (1).to_bytes(2, "little") * 2 + bytes(4) + (12).to_bytes(4, "little")
        endless += bytes(4) * 500 + b"\xff"  # 500 empty posts for a column one pixel high
        self.assertIsNone(picture(endless, palette))


class MvKeyTests(unittest.TestCase):
    def test_a_decoy_key_is_replaced_and_said_an_unheadered_file_kept(self) -> None:
        from tests.helpers import make_png
        from viwo.plugins.rpgmaker.mv import game_images, opens, verified_key

        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / "www" / "data").mkdir(parents=True)
            png = make_png(game / "plain.png").read_bytes()
            (game / "plain.png").unlink()
            (game / "www" / "img").mkdir()
            (game / "www" / "img" / "a.rpgmvp").write_bytes(encrypt_mv(png))
            images = game_images(game)
            self.assertTrue(opens(KEY, images))
            decoy = "00" * 16
            (game / "www" / "data" / "System.json").write_text(f'{{"encryptionKey":"{decoy}"}}')
            key, note = verified_key(game, images)
            self.assertEqual((key, bool(note)), (KEY, True))
            (game / "www" / "data" / "System.json").write_text(f'{{"encryptionKey":"{KEY.hex()}"}}')
            self.assertEqual(verified_key(game, images), (KEY, ""))


class JunctionTests(unittest.TestCase):
    def test_a_junction_in_a_game_folder_is_never_walked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "game" / "Data").mkdir(parents=True)
            (root / "game" / "Data" / "a.pak").write_bytes(b"a")
            (root / "elsewhere").mkdir()
            (root / "elsewhere" / "secret.txt").write_bytes(b"s")
            link = root / "game" / "loop"
            if sys.platform == "win32":
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(root / "elsewhere")],
                    check=True, capture_output=True,
                )  # fmt: skip
            else:
                os.symlink(root / "elsewhere", link)
            self.assertTrue(ws.link_like(link))
            self.assertFalse(ws.link_like(root / "game" / "Data"))
            seen = {name for _, _, names in ws.walk(root / "game") for name in names}
            self.assertEqual(seen, {"a.pak"})
            from viwo.core.pipeline.guard import snapshot

            self.assertEqual(set(snapshot(root / "game")), {"Data/a.pak"})
            from viwo.core.pipeline.unpack import files_under
            from viwo.core.roundtrip import _copy_tree

            found = [p.name for p, _ in files_under(root / "game", "game", set())]
            self.assertEqual(found, ["a.pak"])  # UNPACK sees the game only
            left = _copy_tree(root / "game", root / "copy", lambda e: None)
            self.assertEqual(left, ["loop (a linked folder, not entered)"])  # said
            self.assertFalse((root / "copy" / "loop").exists())
            self.assertTrue((root / "copy" / "Data" / "a.pak").is_file())


if __name__ == "__main__":
    unittest.main()
