"""L5: core backends against real third-party tools (skipped unless VIWO_L5=1)."""

from __future__ import annotations

import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_rar, runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract


@unittest.skipUnless(os.environ.get("VIWO_L5"), "L5 real-tool test (set VIWO_L5=1)")
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
            rt = runtime(root)
            binding = rt.bindings["unarchive.7z"]
            self.assertTrue(binding.bound, binding.reasons)
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertIn("txt/readme.txt", tree_hashes(root / "ws", skip_reserved=True))
            self.assertEqual(result.archives_extracted, 1)


@unittest.skipUnless(os.environ.get("VIWO_L5"), "L5 real-tool test (set VIWO_L5=1)")
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
            rt = runtime(root, "[plugins]\nunity = on\n")
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertTrue(result.success)
            self.assertEqual(result.runs[0].backend, "unitypy")


def _tool(name: str) -> Path | None:
    value = os.environ.get(name, "")
    return Path(value) if value and Path(value).exists() else None


@unittest.skipUnless(os.environ.get("VIWO_L5"), "L5 real-tool test (set VIWO_L5=1)")
class UnrarTest(unittest.TestCase):
    def test_rar_through_its_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            make_rar(game / "data.rar", {"docs/readme.txt": b"stored rar"})
            rt = runtime(root)
            if not rt.bindings["unarchive.rar"].bound:
                self.skipTest("neither unrar nor 7-Zip is installed")
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertIn(
                "txt/readme.txt", tree_hashes(root / "ws", skip_reserved=True), result.warnings
            )


@unittest.skipUnless(os.environ.get("VIWO_L5"), "L5 real-tool test (set VIWO_L5=1)")
class RealGodotToolsTest(unittest.TestCase):
    def make_real_pck(self, root: Path, pcktool: Path) -> Path:
        (root / "src").mkdir()
        (root / "src" / "icon.png").write_bytes(b"real-png")
        pck = root / "data.pck"
        proc = subprocess.run(
            [
                str(pcktool),
                "--pack",
                str(pck),
                "--action",
                "add",
                "--remove-prefix",
                str(root / "src"),
                str(root / "src" / "icon.png"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return pck

    def run_godot(self, root: Path, game: Path, ini: str):
        rt = runtime(root, ini)
        result = extract(
            rt, ExtractionRequest(str(game), str(root / "ws")), "j", lambda e: None, CancelToken()
        )
        return result, tree_hashes(root / "ws", skip_reserved=True)

    def test_godotpcktool_standalone_and_embedded(self) -> None:
        pcktool = _tool("VIWO_GODOTPCKTOOL")
        if pcktool is None:
            self.skipTest("VIWO_GODOTPCKTOOL not set")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pck = self.make_real_pck(root, pcktool)
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
        pcktool, gdre = _tool("VIWO_GODOTPCKTOOL"), _tool("VIWO_GDRE")
        if pcktool is None or gdre is None:
            self.skipTest("VIWO_GODOTPCKTOOL and VIWO_GDRE are both needed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            self.make_real_pck(root, pcktool).rename(game / "data.pck")
            ini = "[plugins]\ngodot = on\n[slots]\nunarchive.pck = gdre-tools\n"
            result, files = self.run_godot(root, game, ini)
            self.assertEqual(dict(result.by_backend), {"gdre-tools": 1}, result.warnings)
            self.assertIn("png/icon.png", files)


@unittest.skipUnless(os.environ.get("VIWO_L5"), "L5 real-tool test (set VIWO_L5=1)")
class AssetStudioModTest(unittest.TestCase):
    def test_spare_runs_without_crashing(self) -> None:
        if _tool("VIWO_ASSETSTUDIOMOD") is None:
            self.skipTest("VIWO_ASSETSTUDIOMOD not set")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            (game / "G_Data").mkdir(parents=True)
            (game / "UnityPlayer.dll").write_bytes(b"MZ")
            (game / "G_Data" / "globalgamemanagers").write_bytes(b"UnityFS\0garbage" * 8)
            ini = "[plugins]\nunity = on\n[slots]\nexport.unity = assetstudiomod-cli\n"
            rt = runtime(root, ini)
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertTrue(result.success)
            self.assertEqual(rt.bindings["export.unity"].main, "assetstudiomod-cli")


if __name__ == "__main__":
    unittest.main()
