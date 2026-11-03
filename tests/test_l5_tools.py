"""L5: core backends against real third-party tools (doc 17.2; skipped unless VIWO_L5=1).

Tools are found the way the product finds them: the pinned copies under the repository's
`third_party/` (what `viwo install --all` fills, locally and in the CI real-tools job) plus the
`VIWO_<ID>` environment overrides that the tool locator honours. A test skips, with the tool
named, only when the tool is absent from both."""

from __future__ import annotations

import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import make_rar, runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core import thirdparty
from viwo.core.pipeline.runner import extract

L5 = unittest.skipUnless(os.environ.get("VIWO_L5"), "L5 real-tool test (set VIWO_L5=1)")
HOME = Path(__file__).resolve().parent.parent  # the repository: startup.ini and third_party/


def real_runtime(root: Path, body: str = ""):
    """A runtime whose third_party/ is the repository's, with the ini and env overrides."""
    with mock.patch.object(thirdparty, "home_of", lambda config: HOME):
        return runtime(root, body)


def tool(dep_id: str) -> Path | None:
    """Executable path of a pinned tool: VIWO_<ID> override, else third_party/<id>/."""
    value = os.environ.get(f"VIWO_{dep_id.upper()}", "")
    if value and Path(value).exists():
        return Path(value)
    found = thirdparty.found_tools(HOME).get(dep_id)
    return Path(found) if isinstance(found, str) else None


def need(case: unittest.TestCase, *dep_ids: str) -> list[Path]:
    paths = [tool(d) for d in dep_ids]
    missing = [d for d, p in zip(dep_ids, paths) if p is None]
    if missing:
        case.skipTest(f"{', '.join(missing)} not installed: run `viwo install {' '.join(missing)}`")
    return [p for p in paths if p is not None]


def run_extract(rt, game: Path, workspace: Path):
    return extract(
        rt, ExtractionRequest(str(game), str(workspace)), "j", lambda e: None, CancelToken()
    )


@L5
class SevenZipTest(unittest.TestCase):
    def test_7z_through_its_slot(self) -> None:
        try:
            import py7zr
        except ImportError:
            self.skipTest("py7zr not installed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            (root / "src.txt").write_text("seven")
            with py7zr.SevenZipFile(game / "data.7z", "w") as archive:
                archive.write(root / "src.txt", "docs/readme.txt")
            rt = real_runtime(root)
            binding = rt.bindings["unarchive.7z"]
            self.assertTrue(binding.bound, binding.reasons)
            result = run_extract(rt, game, root / "ws")
            self.assertIn("txt/readme.txt", tree_hashes(root / "ws", skip_reserved=True))
            self.assertEqual(result.archives_extracted, 1)


@L5
class UnityPyRobustnessTest(unittest.TestCase):
    def test_corrupt_container_is_a_note_not_a_crash(self) -> None:
        try:
            import UnityPy  # noqa: F401
        except ImportError:
            self.skipTest("UnityPy not installed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            (game / "G_Data").mkdir(parents=True)
            (game / "UnityPlayer.dll").write_bytes(b"MZ")
            (game / "G_Data" / "globalgamemanagers").write_bytes(b"UnityFS\0garbage" * 8)
            result = run_extract(real_runtime(root, "[plugins]\nunity = on\n"), game, root / "ws")
            self.assertTrue(result.success)
            self.assertEqual(result.runs[0].backend, "unitypy")


@L5
class UnrarTest(unittest.TestCase):
    def test_rar_through_its_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            make_rar(game / "data.rar", {"docs/readme.txt": b"stored rar"})
            rt = real_runtime(root)
            if not rt.bindings["unarchive.rar"].bound:
                self.skipTest("unrar and 7-Zip both missing: run `viwo install unrar sevenzip`")
            result = run_extract(rt, game, root / "ws")
            self.assertIn(
                "txt/readme.txt", tree_hashes(root / "ws", skip_reserved=True), result.warnings
            )


def make_real_pck(case: unittest.TestCase, root: Path, pcktool: Path) -> Path:
    (root / "src").mkdir()
    (root / "src" / "icon.png").write_bytes(b"real-png")
    pck = root / "data.pck"
    argv = ["--pack", str(pck), "--action", "add", "--remove-prefix", str(root / "src")]
    proc = subprocess.run(
        [str(pcktool), *argv, str(root / "src" / "icon.png")], capture_output=True, text=True
    )
    case.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
    return pck


@L5
class RealGodotToolsTest(unittest.TestCase):
    def run_godot(self, root: Path, game: Path, ini: str):
        result = run_extract(real_runtime(root, ini), game, root / "ws")
        return result, tree_hashes(root / "ws", skip_reserved=True)

    def test_godotpcktool_standalone_and_embedded(self) -> None:
        (pcktool,) = need(self, "godotpcktool")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pck = make_real_pck(self, root, pcktool)
            game = root / "game"
            game.mkdir()
            data = pck.read_bytes()
            (game / "Game.exe").write_bytes(
                b"MZ" + b"\0" * 64 + data + struct.pack("<Q", len(data)) + b"GDPC"
            )
            ini = "[plugins]\ngodot = on\n[slots]\nunarchive.pck = godotpcktool\n"
            result, files = self.run_godot(root, game, ini)
            self.assertEqual(dict(result.by_backend), {"godotpcktool": 1}, result.warnings)
            self.assertIn("png/icon.png", files)

    def test_gdre_tools(self) -> None:
        pcktool, _gdre = need(self, "godotpcktool", "gdre")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            make_real_pck(self, root, pcktool).rename(game / "data.pck")
            ini = "[plugins]\ngodot = on\n[slots]\nunarchive.pck = gdre-tools\n"
            result, files = self.run_godot(root, game, ini)
            self.assertEqual(dict(result.by_backend), {"gdre-tools": 1}, result.warnings)
            self.assertIn("png/icon.png", files)


@L5
class AssetStudioModTest(unittest.TestCase):
    def test_spare_runs_without_crashing(self) -> None:
        if "assetstudiomod" not in thirdparty.found_tools(HOME) and not os.environ.get(
            "VIWO_ASSETSTUDIOMOD"
        ):
            self.skipTest("AssetStudioModCLI not installed: run `viwo install assetstudiomod`")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            (game / "G_Data").mkdir(parents=True)
            (game / "UnityPlayer.dll").write_bytes(b"MZ")
            (game / "G_Data" / "globalgamemanagers").write_bytes(b"UnityFS\0garbage" * 8)
            ini = "[plugins]\nunity = on\n[slots]\nexport.unity = assetstudiomod-cli\n"
            rt = real_runtime(root, ini)
            self.assertEqual(rt.bindings["export.unity"].main, "assetstudiomod-cli")
            self.assertTrue(run_extract(rt, game, root / "ws").success)


@L5
class RealUnrealToolsTest(unittest.TestCase):
    def test_repak_built_pak_through_the_pipeline(self) -> None:
        (repak,) = need(self, "repak")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src" / "Game" / "Content" / "UI"
            src.mkdir(parents=True)
            (src / "Logo.uasset").write_bytes(b"\xc1\x83\x2a\x9e real uasset bytes")
            paks = root / "game" / "Game" / "Content" / "Paks"
            paks.mkdir(parents=True)
            pak = paks / "pakchunk0-Windows.pak"
            proc = subprocess.run(
                [str(repak), "pack", str(root / "src"), str(pak)], capture_output=True, text=True
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            rt = real_runtime(root, "[plugins]\nunreal = on\n")
            result = run_extract(rt, root / "game", root / "ws")
            self.assertEqual(result.archives_extracted, 1, result.warnings)
            self.assertTrue((root / "ws" / "uasset" / "Logo.uasset").is_file())


@L5
class RealVgmstreamTest(unittest.TestCase):
    def test_wwise_pcm_wem_becomes_wav(self) -> None:
        need(self, "vgmstream")
        import wave

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "game").mkdir()
            with wave.open(str(root / "game" / "voice.wem"), "wb") as w:
                w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050)
                w.writeframes(b"\x00\x10" * 22050)
            run_extract(real_runtime(root), root / "game", root / "ws")
            outputs = list((root / "ws" / "wav").glob("voice.wem*.wav"))
            self.assertEqual(len(outputs), 1, list((root / "ws").rglob("*")))
            with wave.open(str(outputs[0])) as w:
                self.assertGreater(w.getnframes(), 20000)


@L5
class RealRoundTripTest(unittest.TestCase):
    """Extract -> edit -> repack with the real tools -> re-extract verification."""

    def edit_and_repack(self, root: Path, rt, rel: str, data: bytes) -> dict:
        from viwo.core.roundtrip import repack

        run_extract(rt, root / "game", root / "ws")
        (root / "ws" / rel).write_bytes(data)
        return repack(rt, root / "ws", root / "patched")

    def test_unreal_patch_pak(self) -> None:
        (repak,) = need(self, "repak")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "Game" / "Content").mkdir(parents=True)
            (root / "src" / "Game" / "Content" / "Logo.uasset").write_bytes(b"original")
            (root / "game" / "Paks").mkdir(parents=True)
            pak = root / "game" / "Paks" / "pakchunk0-Windows.pak"
            subprocess.run([str(repak), "pack", str(root / "src"), str(pak)], check=True)
            report = self.edit_and_repack(root, real_runtime(root), "uasset/Logo.uasset", b"modded")
            self.assertTrue(report["verified"], report)
            self.assertTrue((root / "patched" / "Paks" / "pakchunk0-Windows_P.pak").is_file())

    def test_godot_pck_rebuild(self) -> None:
        (pcktool,) = need(self, "godotpcktool")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pck = make_real_pck(self, root, pcktool)
            (root / "game").mkdir()
            pck.rename(root / "game" / "data.pck")
            rt = real_runtime(root, "[slots]\nunarchive.pck = godotpcktool\n")
            report = self.edit_and_repack(root, rt, "png/icon.png", b"modded-png")
            self.assertTrue(report["verified"], report)


if __name__ == "__main__":
    unittest.main()
