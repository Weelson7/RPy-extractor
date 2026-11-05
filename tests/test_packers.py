"""L3: the patching arm for the engines ViWo reads itself (doc 18). For random archives and
random edits: ASAR, RGSSAD (v1 and v3) and DRS are rebuilt and read back with every edit in and
every other member unchanged; the VPK override, the XP3 patch archive, the Bethesda loose files and
the Warscape movie pack hold exactly the edits, read back byte for byte, written where the
engine loads them over its own archives; two XP3 archives' edits share one patch; a PFH5 pack is
refused by name; a damaged archive is a named failure."""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.test_containers import pack as pfh
from tests.test_formats import asar
from tests.test_rpgmaker import rgssad_v1, rgssad_v3
from viwo.contracts.types import OutcomeKind

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


def _files(rng: random.Random, sep: str = "/") -> dict[str, bytes]:
    names = {
        sep.join(["d" + str(rng.randint(0, 2)), f"f{i}.bin"]) for i in range(rng.randint(2, 9))
    }
    return {n: rng.randbytes(rng.randint(0, 400)) for n in sorted(names)}


def _edits(rng: random.Random, root: Path, names: list[str]) -> dict[str, Path]:
    edits = {}
    for i, name in enumerate(rng.sample(names, rng.randint(1, len(names)))):
        path = root / f"edit{i}"
        path.write_bytes(rng.randbytes(rng.randint(0, 500)))
        edits[name] = path
    return edits


def _read(backend, archive: Path, out: Path) -> dict[str, bytes]:
    out.mkdir(parents=True, exist_ok=True)
    result = backend.extract(archive, out, CTX)
    assert result.kind is OutcomeKind.OK, result.error
    return {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}


class RebuiltTests(unittest.TestCase):
    def test_asar_and_rgssad_are_rebuilt_with_every_edit_and_nothing_else_changed(self) -> None:
        from viwo.plugins.electron import AsarBuiltin
        from viwo.plugins.electron.pack import AsarWriter
        from viwo.plugins.rpgmaker.rgss import RgssadBuiltin
        from viwo.plugins.rpgmaker.rgss_pack import RgssadWriter

        kinds = (
            ("asar", asar, AsarWriter, AsarBuiltin, "/"),
            ("rgssad", rgssad_v1, RgssadWriter, RgssadBuiltin, "\\"),
            ("rgss3a", rgssad_v3, RgssadWriter, RgssadBuiltin, "\\"),
        )
        rng = random.Random(18)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(30):
                kind, build, writer, reader, sep = kinds[case % 3]
                files = _files(rng, sep)
                archive = root / f"c{case}.{kind}"
                archive.write_bytes(build(files))
                plain = {n.replace("\\", "/"): d for n, d in files.items()}
                edits = _edits(rng, root, sorted(plain))
                out = writer().pack(archive, edits, CTX)
                self.assertEqual((out.kind, out.files), (OutcomeKind.OK, len(files)), kind)
                got = _read(reader(), archive, root / f"o{case}")
                want = {n: (edits[n].read_bytes() if n in edits else d) for n, d in plain.items()}
                self.assertEqual(got, want, kind)
            self._drs(rng, root)
            (root / "bad.asar").write_bytes(b"not an archive at all")
            self.assertEqual(AsarWriter().pack(root / "bad.asar", {}, CTX).kind, OutcomeKind.FAILED)

    def _drs(self, rng: random.Random, root: Path) -> None:
        from tests.test_containers import drs
        from viwo.plugins.genie import DrsBuiltin
        from viwo.plugins.genie.pack import DrsWriter

        for case in range(8):
            tables = {
                ext: {rng.randint(1, 9999): rng.randbytes(rng.randint(0, 300)) for _ in range(4)}
                for ext in rng.sample(["slp", "wav", "shp"], rng.randint(1, 3))
            }
            archive = root / f"g{case}.drs"
            archive.write_bytes(drs(tables))
            plain = {f"{i}.{ext}": d for ext, files in tables.items() for i, d in files.items()}
            edits = _edits(rng, root, sorted(plain))
            self.assertEqual(DrsWriter().pack(archive, edits, CTX).kind, OutcomeKind.OK)
            got = _read(DrsBuiltin(), archive, root / f"go{case}")
            want = {n: (edits[n].read_bytes() if n in edits else d) for n, d in plain.items()}
            self.assertEqual(got, want)


class OverrideTests(unittest.TestCase):
    def test_each_override_holds_exactly_the_edits_where_the_engine_loads_it(self) -> None:
        from viwo.plugins.bethesda.pack import LooseOverride
        from viwo.plugins.kirikiri.pack import Xp3Writer
        from viwo.plugins.source.pack import VpkWriter
        from viwo.plugins.warscape.pack import MoviePack

        cases = (
            (VpkWriter, "tf/tf2_misc_dir.vpk", "tf/custom/!viwo_tf2_misc.vpk"),
            (Xp3Writer, "game/data.xp3", "game/patch.xp3"),
            (LooseOverride, "Data/Skyrim - Textures0.bsa", "Data"),
            (MoviePack, "data/data.pack", "data/viwo_data.pack"),
        )
        rng = random.Random(19)
        with tempfile.TemporaryDirectory() as tmp:
            for case in range(24):
                writer, container, where = cases[case % 4]
                root = Path(tmp) / str(case)
                path = root / container
                path.parent.mkdir(parents=True)
                path.write_bytes(pfh({"x": b"y"}) if writer is MoviePack else b"game archive")
                before = path.read_bytes()
                edits = _edits(rng, root, sorted(_files(rng)))
                packer = writer()
                out = packer.pack(path, edits, CTX)
                self.assertEqual((out.kind, out.files), (OutcomeKind.OK, len(edits)), writer)
                self.assertTrue(packer.override)
                self.assertEqual(packer.output_for(path), root / where)
                self.assertEqual(packer.verify(root / where, edits, CTX), [])
                self.assertEqual(path.read_bytes(), before)  # the game's archive is untouched
                victim = next(iter(edits))
                edits[victim].write_bytes(b"changed after packing")
                self.assertEqual(packer.verify(root / where, edits, CTX), [victim])

    def test_two_archives_share_one_patch_and_newer_packs_are_refused_by_name(self) -> None:
        from viwo.plugins.kirikiri.pack import Xp3Writer
        from viwo.plugins.warscape.pack import MoviePack

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / "a", root / "b"
            first.write_bytes(b"one")
            second.write_bytes(b"two")
            for name in ("data.xp3", "voice.xp3"):
                (root / name).write_bytes(b"x")
            Xp3Writer().pack(root / "data.xp3", {"bg/a.png": first}, CTX)
            Xp3Writer().pack(root / "voice.xp3", {"voice/b.ogg": second}, CTX)
            both = {"bg/a.png": first, "voice/b.ogg": second}
            self.assertEqual(Xp3Writer().verify(root / "patch.xp3", both, CTX), [])
            (root / "patch2.xp3").write_bytes(b"the game's own patch")  # never overwritten
            (root / "w.pack").write_bytes(pfh({"a": b"x"}, b"PFH5"))
            refused = MoviePack().pack(root / "w.pack", {"a": first}, CTX)
            self.assertEqual(refused.kind, OutcomeKind.FAILED)
            self.assertIn("PFH5", refused.error)


if __name__ == "__main__":
    unittest.main()
