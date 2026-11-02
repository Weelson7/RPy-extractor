"""L3: third_party installer: verified download, safe unpack, discovery, checksum refusal,
needs/from/argv specs, strict preflight. L5 (VIWO_L5=1): real pinned downloads."""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.helpers import runtime
from viwo.contracts import ViwoError
from viwo.contracts.types import DependencySpec
from viwo.core import preflight, thirdparty
from viwo.os import select_os

WIN = thirdparty.PLATFORM == "windows"


def fake_manifest(archive: Path, digest: str) -> dict:
    spec = {
        "url": archive.as_uri(),
        "sha256": digest,
        "size": archive.stat().st_size,
        "kind": "zip",
        "find": "repak.exe" if WIN else "repak",
    }
    return {"python": {}, "tools": {"repak": {thirdparty.PLATFORM: spec}}}


def zip_bytes(members: dict[str, bytes]) -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        for name, blob in members.items():
            z.writestr(name, blob)
    return data.getvalue()


def pinned(root: Path, name: str, members: dict[str, bytes], **extra) -> dict:
    archive = root / name
    archive.write_bytes(zip_bytes(members))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    return {"url": archive.as_uri(), "sha256": digest, "size": archive.stat().st_size, **extra}


def prefixed_manifest(root: Path) -> dict:
    p = thirdparty.PLATFORM
    tools = {
        "dotnet": {
            "version": "10",
            "hidden": True,
            p: pinned(root, "dn.zip", {"dotnet": b"x"}, kind="zip", find="dotnet"),
        },
        "assetstudiomod": {
            "version": "0.20",
            p: pinned(
                root,
                "as.zip",
                {"AssetStudioModCLI.dll": b"x"},
                kind="zip",
                find="AssetStudioModCLI.dll",
                argv=["{dotnet}", "{path}"],
                needs=["dotnet"],
            ),
        },
        "renderdoccmd": {
            "version": "1.47",
            p: pinned(
                root,
                "rd.zip",
                {"RD/renderdoccmd": b"x", "RD/qrenderdoc": b"x"},
                kind="zip",
                find="renderdoccmd",
                mkdir=["scripts"],
            ),
        },
        "rdpython": {
            "version": "1.47",
            p: {
                "from": "renderdoccmd",
                "needs": ["renderdoccmd"],
                "find": "qrenderdoc",
                "argv": ["{path}", "--py"],
            },
        },
    }
    return {"python": {}, "tools": tools}


class InstallerTests(unittest.TestCase):
    def test_install_verify_and_find(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = "repak.exe" if WIN else "repak"
            archive = root / "repak.zip"
            archive.write_bytes(zip_bytes({f"repak_cli/{name}": b"binary", "../evil.txt": b"no"}))
            good = hashlib.sha256(archive.read_bytes()).hexdigest()
            home = root / "home"
            with mock.patch.object(thirdparty, "manifest", lambda: fake_manifest(archive, good)):
                path = thirdparty.install_tool("repak", home, None)
                self.assertEqual(Path(path), home / "third_party" / "repak" / "repak_cli" / name)
                self.assertEqual(thirdparty.found_tools(home), {"repak": path})
                self.assertFalse(list(root.rglob("evil.txt")))
                cache = home / "third_party" / "repak" / thirdparty.CACHE
                self.assertTrue(cache.is_file())  # boot reads the hit, never rglobs again
                cache.write_text("{broken", encoding="utf-8")  # a bad cache self-heals
                self.assertEqual(thirdparty.found_tools(home), {"repak": path})
                self.assertIn("repak", cache.read_text(encoding="utf-8"))
                self.assertEqual(thirdparty.installed_version("repak", home), "")
            with mock.patch.object(
                thirdparty, "manifest", lambda: fake_manifest(archive, "0" * 64)
            ):
                with self.assertRaises(ViwoError) as err:
                    thirdparty.install_tool("repak", root / "other", None)
                self.assertEqual(err.exception.code, "refused")
                self.assertFalse((root / "other" / "third_party" / "repak").exists())

    def test_needs_from_and_argv_prefix(self) -> None:
        """A dll run through the runtime it needs; an alias tool borrowing another folder."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            with mock.patch.object(thirdparty, "manifest", lambda: prefixed_manifest(root)):
                thirdparty.install_tool("assetstudiomod", home, None)  # pulls dotnet first
                thirdparty.install_tool("rdpython", home, None)  # pulls renderdoccmd, no download
                found = thirdparty.found_tools(home)
                tp = home / "third_party"
                self.assertEqual(
                    found["assetstudiomod"],
                    (
                        str(tp / "dotnet" / "dotnet"),
                        str(tp / "assetstudiomod" / "AssetStudioModCLI.dll"),
                    ),
                )
                self.assertEqual(
                    found["rdpython"], (str(tp / "renderdoccmd" / "RD" / "qrenderdoc"), "--py")
                )
                self.assertEqual(
                    found["renderdoccmd"], str(tp / "renderdoccmd" / "RD" / "renderdoccmd")
                )
                self.assertNotIn("dotnet", found)  # hidden: not a dependency of its own
                self.assertTrue((tp / "renderdoccmd" / "scripts").is_dir())
                self.assertEqual(thirdparty.installed_version("rdpython", home), "1.47")

    def test_locator_accepts_argv_prefixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            with mock.patch.object(thirdparty, "manifest", lambda: prefixed_manifest(root)):
                thirdparty.install_tool("assetstudiomod", home, None)
                found = thirdparty.found_tools(home)
            layer = select_os(tool_overrides=found)
            spec = mock.Mock(dep_id="assetstudiomod", env_var="", kind="executable", executables=())
            location = layer.tools.locate(spec)
            self.assertEqual(location.argv_prefix, found["assetstudiomod"])
            self.assertEqual(location.path, found["assetstudiomod"][1])
            self.assertIsNone(layer.tools.locate(DependencySpec("nothing", "nothing")))

    def test_http_download_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "url": "http://example.invalid/x.zip",
                "sha256": "0" * 64,
                "size": 1,
                "kind": "zip",
                "find": "x",
            }
            with mock.patch.object(
                thirdparty,
                "manifest",
                lambda: {"python": {}, "tools": {"x": {thirdparty.PLATFORM: spec}}},
            ):
                with self.assertRaises(ViwoError) as err:
                    thirdparty.install_tool("x", Path(tmp), None)
                self.assertEqual(err.exception.code, "refused")

    def test_manifest_pins_match_pyproject(self) -> None:
        text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
        for pin in thirdparty.manifest()["python"].values():
            self.assertIn(f'"{pin}"', text)

    def test_manifest_is_complete_and_https(self) -> None:
        tools = thirdparty.manifest()["tools"]
        for dep in (
            "repak",
            "retoc",
            "vgmstream",
            "gdre",
            "godotpcktool",
            "assetstudiomod",
            "sevenzip",
            "ffmpeg",
            "ffprobe",
            "unrar",
            "quickbms",
            "datatool",
            "renderdoccmd",
            "rdpython",
            "dotnet",
        ):
            self.assertIn(dep, tools)
        for dep, entry in tools.items():
            for plat in ("windows", "linux"):
                spec = entry.get(plat)
                if spec is None or "url" not in spec:
                    continue
                self.assertTrue(spec["url"].startswith("https://"), dep)
                self.assertRegex(spec["sha256"], r"^[0-9a-f]{64}$", dep)
                self.assertGreater(spec["size"], 1000, dep)
                self.assertIn(spec["kind"], ("zip", "tar", "gz", "raw", "msi", "sfx"), dep)

    def test_strict_problems_name_unbound_plugin_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime(
                Path(tmp), "[plugins]\nquickbms = on\n[tools]\nquickbms = /nowhere/quickbms\n"
            )
            problems = preflight.strict_problems(rt)
            self.assertTrue(any("unarchive.bms" in p for p in problems), problems)


@unittest.skipUnless(os.environ.get("VIWO_L5"), "L5 real downloads (set VIWO_L5=1)")
class RealInstallTests(unittest.TestCase):
    def test_install_pinned_tools_into_a_temp_home(self) -> None:
        """Real pinned downloads: an sfx (needs 7-Zip), a dll on the .NET runtime, an alias."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            runner = select_os().process
            for dep in ("unrar", "assetstudiomod", "quickbms"):
                thirdparty.install_tool(dep, home, runner)
            found = thirdparty.found_tools(home)
            for dep in ("unrar", "sevenzip", "assetstudiomod", "quickbms"):
                self.assertIn(dep, found)
            self.assertTrue((home / "third_party" / "quickbms" / "scripts").is_dir())
            result = runner.run([*found["assetstudiomod"], "--help"], timeout=60)
            self.assertIn("AssetStudio", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
