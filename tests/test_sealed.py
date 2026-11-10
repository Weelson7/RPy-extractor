"""L3: the plugin system is sealed. A new engine plugin is one folder under viwo/plugins/ and
nothing else: written here as a real built-in package (a `.seal` archive is a zip under another
name, with a distro profile of its own) on `viwo.plugins.__path__`, where discovery looks. With
no change to core, it is discovered, loaded, bound to its slot, given its own distro, detected
on a game, and a real extraction unpacks its archives into the workspace. (`viwo config
generate` then writes its two distro files: generated, not written by hand.)"""

import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

import viwo.plugins
from tests.helpers import runtime
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract
from viwo.core.wiring import distros, registry

PLUGIN = '''
"""A .seal archive is a zip under another name (the sealed-plugin test)."""

import zipfile
from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import safe_member

MANIFEST = PluginManifest("sealed", "Sealed", "0.1.0", engine_type="sealed", profile="sealed")


class SealUnarchiver(Unarchiver):
    backend_id, owner, license = "seal-zip", "sealed", "MIT"

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        written = 0
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                rel = safe_member(info.filename)
                if rel is None or info.is_dir():
                    continue
                target = dest.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
                written += 1
        return Outcome(OutcomeKind.OK, written)


class SealedPlugin(EnginePlugin):
    manifest = property(lambda self: MANIFEST)

    def detect(self, probe: GameProbe) -> DetectionResult:
        hits = probe.with_suffix(".seal")
        score = 0.95 if hits else 0.0
        return DetectionResult("sealed", score, (f"{len(hits)} .seal archive(s)",), "sealed")

    def slot_definitions(self):
        return (SlotDefinition("unarchive.seal", "unarchive", "sealed", "seal-zip",
                               suffixes=(".seal",), magic=(b"PK\\x03\\x04",)),)

    def backends(self):
        return (SealUnarchiver(),)
'''


class SealedTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        package = self.root / "plugins" / "sealed"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(textwrap.dedent(PLUGIN), encoding="utf-8")
        viwo.plugins.__path__.append(str(package.parent))  # where discovery looks for built-ins
        saved = dict(registry.BUILTIN_PLUGINS)
        registry.BUILTIN_PLUGINS.update(registry._discover_builtins())

        def restore() -> None:
            viwo.plugins.__path__.remove(str(package.parent))
            registry.BUILTIN_PLUGINS.clear()
            registry.BUILTIN_PLUGINS.update(saved)
            sys.modules.pop("viwo.plugins.sealed", None)

        self.addCleanup(restore)

    def test_a_new_engine_needs_no_change_outside_its_folder(self) -> None:
        self.assertEqual(registry.BUILTIN_PLUGINS["sealed"], "viwo.plugins.sealed:SealedPlugin")
        (self.root / "rt").mkdir()
        rt = runtime(self.root / "rt")
        self.assertIn("sealed", rt.plugins)
        self.assertEqual(rt.bindings["unarchive.seal"].main, "seal-zip")  # bound to its slot
        self.assertIn("sealed", distros.profiles())  # its own distro, from its manifest
        on = distros.enabled_for("sealed")
        self.assertEqual({p for p, v in on.items() if v}, {"generic", "sealed"})
        self.assertFalse(distros.enabled_for("custom")["sealed"])  # it has its own profile
        with tempfile.TemporaryDirectory() as tmp:
            for os_id in distros.OSES:
                probe = Path(tmp) / f"{os_id}-sealed.ini"
                probe.write_text(distros.render(os_id, "sealed"), encoding="utf-8")
                self.assertEqual(distros.check(probe), [], os_id)
        game = self.root / "game"
        game.mkdir()
        with zipfile.ZipFile(game / "data.seal", "w") as zf:
            zf.writestr("text/readme.txt", "sealed")
            zf.writestr("art/hero.bin", b"\x00\x01")
        result = extract(
            rt, ExtractionRequest(str(game), str(self.root / "ws")), "j", lambda e: None,
            CancelToken(),
        )  # fmt: skip
        self.assertIn("seal-zip", result.by_backend)  # unpacked by the new plugin's backend
        self.assertEqual((self.root / "ws" / "txt" / "readme.txt").read_text(), "sealed")
        self.assertTrue((self.root / "ws" / "bin" / "hero.bin").is_file())


if __name__ == "__main__":
    unittest.main()
