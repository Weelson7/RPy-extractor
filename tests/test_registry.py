"""L1/L3: plugin discovery: built-ins by scan, drop-ins from custom_dirs, entry points."""

from __future__ import annotations

import json
import pkgutil
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import make_zip, runtime, tree_hashes
from viwo.api import plugin_assets
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts.plugin import CliCommand
from viwo.core.pipeline.runner import extract
from viwo.core.wiring import registry
from viwo.core.wiring.distros import enabled_for

ROOT = Path(__file__).resolve().parent.parent
HELLO = ROOT / "examples" / "plugins" / "hello"


def copy_hello(root: Path, **meta_changes) -> Path:
    custom = root / "user_plugins"
    shutil.copytree(HELLO, custom / "hello")
    if meta_changes:
        path = custom / "hello" / "plugin.json"
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta.update(meta_changes)
        path.write_text(json.dumps(meta), encoding="utf-8")
    return custom


class BuiltinDiscoveryTests(unittest.TestCase):
    def test_every_plugin_package_is_discovered_by_its_manifest_id(self) -> None:
        folders = sorted(
            p.name for p in (ROOT / "viwo" / "plugins").iterdir() if (p / "__init__.py").is_file()
        )
        self.assertEqual(sorted(registry.BUILTIN_PLUGINS), folders)
        self.assertEqual(registry.DISCOVERY_PROBLEMS, [])
        for plugin_id, entry in registry.BUILTIN_PLUGINS.items():
            self.assertEqual(registry.load_plugin(entry).manifest.plugin_id, plugin_id)

    def test_discovery_needs_no_folder_on_disk(self) -> None:
        """Frozen build: packages live in the PYZ archive; pkgutil lists them, no iterdir."""
        listed = [pkgutil.ModuleInfo(None, name, True) for name in ("generic", "doom", "nope")]
        with mock.patch.object(pkgutil, "iter_modules", return_value=listed):
            with mock.patch.object(registry, "DISCOVERY_PROBLEMS", []):
                found = registry._discover_builtins()
                self.assertEqual(
                    found,
                    {
                        "generic": "viwo.plugins.generic:GenericPlugin",
                        "doom": "viwo.plugins.doom:DoomPlugin",
                    },
                )
                self.assertTrue(any("nope" in p for p in registry.DISCOVERY_PROBLEMS))

    def test_custom_profile_is_derived_from_the_manifests(self) -> None:
        custom = enabled_for("custom")
        self.assertTrue(custom["generic"] and custom["doom"] and custom["quickbms"])
        self.assertFalse(custom["renpy"] or custom["unity"] or custom["unreal"] or custom["godot"])
        self.assertTrue(all(enabled_for("mixed").values()))

    def test_version_requirements(self) -> None:
        self.assertTrue(registry.version_ok(">=0.2", "1.0.0"))
        self.assertTrue(registry.version_ok("1.0", "1.0.3"))
        self.assertFalse(registry.version_ok(">=2", "1.9.9"))
        self.assertFalse(registry.version_ok("<1.0", "1.0.0"))
        self.assertFalse(registry.version_ok("banana", "1.0.0"))


class DropinTests(unittest.TestCase):
    def test_opt_in_override_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom = copy_hello(root)
            off, _ = registry.load_enabled({}, [custom])
            self.assertNotIn("hello", off)  # drop-ins are opt-in
            on, problems = registry.load_enabled({"hello": True}, [custom])
            self.assertIn("hello", on)
            self.assertFalse(on["hello"].manifest.builtin)
            self.assertEqual(problems, [])
            on, _ = registry.load_enabled({"custom.hello": True}, [custom])
            self.assertIn("hello", on)
            self.assertIn("hello", registry.known_ids([custom]))
            broken = custom / "broken"
            broken.mkdir()
            (broken / "plugin.json").write_text('{"id": "broken", "module": "x", "class": "Y"}')
            _, problems = registry.load_enabled({"broken": True}, [custom])
            self.assertTrue(any("broken" in p and "disabled" in p for p in problems), problems)

    def test_clash_with_a_builtin_needs_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom = copy_hello(root, id="doom", enabled=True)
            src = custom / "hello" / "__init__.py"
            src.write_text(
                src.read_text(encoding="utf-8").replace('"hello", "Hello', '"doom", "Hello')
            )
            plugins, problems = registry.load_enabled({"doom": True}, [custom])
            self.assertTrue(any("override" in p for p in problems), problems)
            self.assertEqual(
                plugins["doom"].manifest.name,
                "Doom engine (WAD)"[:4] and plugins["doom"].manifest.name,
            )
            custom2 = copy_hello(root / "two", id="doom", enabled=True, override=True)
            src2 = custom2 / "hello" / "__init__.py"
            src2.write_text(
                src2.read_text(encoding="utf-8").replace('"hello", "Hello', '"doom", "Hello')
            )
            plugins, problems = registry.load_enabled({"doom": True}, [custom2])
            self.assertEqual(plugins["doom"].manifest.name, "Hello (example)")

    def test_requirement_mismatch_disables_only_that_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            custom = copy_hello(Path(tmp), requires={"viwo": ">=99"}, enabled=True)
            plugins, problems = registry.load_enabled({}, [custom])
            self.assertNotIn("hello", plugins)
            self.assertTrue(any("needs viwo >=99" in p for p in problems), problems)

    def test_end_to_end_extraction_through_a_dropin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom = copy_hello(root)
            game = root / "game"
            make_zip(game / "data.hello", {"img/a.png": b"\x89PNG\r\n\x1a\n" + b"\0" * 32})
            ini = f"[plugins]\ncustom_dirs = {custom.as_posix()}\nhello = on\n"
            rt = runtime(root, ini)
            self.assertIn("hello", rt.plugins)
            self.assertTrue(rt.bindings["unarchive.hello"].bound)
            before = tree_hashes(game)
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertTrue(result.success)
            self.assertIn("hello", [r.plugin_id for r in result.runs])
            self.assertTrue((root / "ws" / "png" / "a.png").is_file())
            self.assertEqual(tree_hashes(game), before)


class FakeHandler:
    """Records what the server would have sent for a plugin asset."""

    def __init__(self, rt) -> None:
        self.app = mock.Mock(rt=rt)
        self.sent: list = []

    def send_error(self, status: int) -> None:
        self.sent.append(("error", status))

    def send_file(self, path: Path) -> None:
        self.sent.append(("file", path))


class AddonTests(unittest.TestCase):
    def test_cli_commands_registry_and_clash_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            custom = copy_hello(Path(tmp))
            plugins, _ = registry.load_enabled({"hello": True}, [custom])
            found, problems = registry.cli_commands(plugins, {"detect"})
            self.assertEqual((list(found), problems), (["hello-list"], []))
            self.assertEqual(found["hello-list"][0], "hello")
            clash = mock.Mock(cli_enabled=True)
            clash.cli_commands.return_value = (
                CliCommand("detect", "x", lambda p: None, lambda rt, a: {}),
            )
            found, problems = registry.cli_commands({"c": clash}, {"detect"})
            self.assertEqual(found, {})
            self.assertTrue(any("override" in p for p in problems), problems)
            clash.cli_commands.return_value = (
                CliCommand("detect", "x", lambda p: None, lambda rt, a: {}, override=True),
            )
            found, problems = registry.cli_commands({"c": clash}, {"detect"})
            self.assertEqual((list(found), problems), (["detect"], []))
            quiet = copy_hello(Path(tmp) / "two", cli=False)
            plugins, _ = registry.load_enabled({"hello": True}, [quiet])
            found, problems = registry.cli_commands(plugins, set())
            self.assertEqual(found, {})
            self.assertTrue(any('"cli": true' in p for p in problems), problems)

    def test_ui_modules_and_asset_containment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom = copy_hello(root)
            ini = f"[plugins]\ncustom_dirs = {custom.as_posix()}\nhello = on\n"
            rt = runtime(root, ini)
            self.assertEqual(
                plugin_assets.ui_modules(rt), [{"plugin": "hello", "url": "/plugins/hello/ui.js"}]
            )
            hello = custom / "hello"
            self.assertEqual(plugin_assets.resolve(rt, "/plugins/hello/ui.js"), hello / "ui.js")
            self.assertEqual(
                plugin_assets.resolve(rt, "/plugins/hello/ui/hello.css"), hello / "ui" / "hello.css"
            )
            for bad in (
                "/plugins/hello/../plugin.json",
                "/plugins/hello/__init__.py",
                "/plugins/hello/plugin.json",
                "/plugins/hello/ui/../__init__.py",
                "/plugins/hello/ui",
                "/plugins/doom/ui.js",
                "/plugins/hello/",
            ):
                self.assertIsNone(plugin_assets.resolve(rt, bad), bad)
            handler = FakeHandler(rt)
            self.assertFalse(plugin_assets.serve(handler, "/js/main.js"))
            self.assertTrue(plugin_assets.serve(handler, "/plugins/hello/ui.js"))
            self.assertTrue(plugin_assets.serve(handler, "/plugins/hello/__init__.py"))
            self.assertEqual(handler.sent, [("file", hello / "ui.js"), ("error", 404)])
            meta = json.loads((hello / "plugin.json").read_text(encoding="utf-8"))
            meta["ui"] = "../evil.js"
            (hello / "plugin.json").write_text(json.dumps(meta), encoding="utf-8")
            _, problems = registry.load_enabled({"hello": True}, [custom])
            self.assertTrue(any("'ui'" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
