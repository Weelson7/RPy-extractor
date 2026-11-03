"""Doc 2.9 conformance kit: every plugin (built-in and the example drop-in) passes the same
checks: manifest, detect purity on an empty probe and on every synthetic fixture, unique
option keys and dependency ids, slot/backend ownership, export sandbox, locate() never writes."""

from __future__ import annotations

import builtins
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import make_game, runtime, tree_hashes
from viwo.contracts import CancelToken, DependencySpec, ExtractionRequest
from viwo.contracts.pipeline import ExtractionMode, MixedPolicy
from viwo.contracts.plugin import OPTION_KINDS
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.core.wiring.registry import (
    BUILTIN_PLUGINS,
    SLUG,
    EmptyProbe,
    load_enabled,
    load_plugin,
    validate_plugin,
)
from viwo.os import select_os


def every_plugin():
    return {pid: load_plugin(entry) for pid, entry in BUILTIN_PLUGINS.items()}


class ManifestTests(unittest.TestCase):
    def test_every_builtin_passes_validate_plugin(self) -> None:
        for pid, plugin in every_plugin().items():
            with self.subTest(plugin=pid):
                self.assertEqual(validate_plugin(plugin, "windows"), [])
                self.assertEqual(validate_plugin(plugin, "linux"), [])
                m = plugin.manifest
                self.assertTrue(SLUG.fullmatch(m.plugin_id))
                self.assertEqual(m.plugin_id, pid)
                self.assertTrue(m.engine_type)
                keys = [o.key for o in m.options]
                self.assertEqual(len(set(keys)), len(keys))
                for option in m.options:
                    self.assertIn(option.kind, OPTION_KINDS)

    def test_slots_and_backends_belong_to_their_plugin(self) -> None:
        for pid, plugin in every_plugin().items():
            with self.subTest(plugin=pid):
                for slot in plugin.slot_definitions():
                    self.assertEqual(slot.owner, pid, slot.slot_id)
                    self.assertEqual(slot.slot_id, slot.slot_id.lower())
                    for suffix in slot.suffixes:
                        self.assertTrue(suffix.startswith(".") and suffix == suffix.lower(), suffix)
                for backend in plugin.backends():
                    self.assertEqual(backend.owner, pid, backend.backend_id)
                    self.assertIn(backend.network, ("none", "download", "any"))
                    if backend.license.startswith(("GPL", "AGPL")):
                        self.assertEqual(backend.isolation, "subprocess", backend.backend_id)

    def test_validate_plugin_rejects_bad_manifests(self) -> None:
        good = every_plugin()["doom"]
        self.assertEqual(validate_plugin(good), [])

        class Bad(type(good)):
            @property
            def manifest(self):  # noqa: D102
                m = good.manifest
                return type(m)(
                    "Doom!",
                    m.name,
                    m.version,
                    "",
                    contract="9.0",
                    options=(m.options + m.options) if m.options else m.options,
                    os_layers=("plan9",),
                )

        problems = validate_plugin(Bad(), "windows")
        text = " ".join(problems)
        for word in ("slug", "contract", "engine_type", "os_layers"):
            self.assertIn(word, text, problems)

        class Raises(type(good)):
            def detect(self, probe):
                raise RuntimeError("boom")

        self.assertTrue(any("raised" in p for p in validate_plugin(Raises())))
        plugins, problems = load_enabled({}, (), "plan9")
        self.assertIn("generic", plugins)  # os_layers empty = every OS layer


class DetectTests(unittest.TestCase):
    def test_detect_is_pure_on_empty_and_fixture_probes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = make_game(root)
            probes = [EmptyProbe(), FolderProbe(game)]
            for pid, plugin in every_plugin().items():
                for probe in probes:
                    with self.subTest(plugin=pid, probe=type(probe).__name__):
                        first = plugin.detect(probe)
                        second = plugin.detect(probe)
                        self.assertEqual(first, second)
                        self.assertEqual(first.plugin_id, pid)
                        self.assertTrue(0.0 <= first.confidence <= 1.0)


class SandboxTests(unittest.TestCase):
    def test_export_writes_only_inside_staging_and_scratch(self) -> None:
        """Doc 2.9: a run over every plugin changes nothing outside the job's work folder."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = make_game(root)
            outside = root / "outside"
            outside.mkdir()
            (outside / "keep.txt").write_text("x")
            rt = runtime(root, "[plugins]\n" + "".join(f"{p} = on\n" for p in BUILTIN_PLUGINS))
            before_game, before_out = tree_hashes(game), tree_hashes(outside)
            request = ExtractionRequest(
                str(game), str(root / "ws"), None, ExtractionMode.MIXED, (), MixedPolicy.ALL
            )
            extract(rt, request, "kit", lambda e: None, CancelToken())
            self.assertEqual(tree_hashes(game), before_game)
            self.assertEqual(tree_hashes(outside), before_out)
            for pid in BUILTIN_PLUGINS:
                stray = root / pid
                self.assertFalse(stray.exists(), f"{pid} wrote next to the root")


class LocatorTests(unittest.TestCase):
    def test_locate_never_installs_or_writes(self) -> None:
        """Doc 1.7: locate() is side-effect free; a recording fake catches any write."""
        layer = select_os()
        writes: list[str] = []
        real_open = builtins.open

        def spy_open(file, mode="r", *args, **kwargs):
            if any(flag in str(mode) for flag in ("w", "a", "x", "+")):
                writes.append(str(file))
            return real_open(file, mode, *args, **kwargs)

        with (
            mock.patch("builtins.open", spy_open),
            mock.patch("os.makedirs", side_effect=AssertionError("makedirs")),
            mock.patch("shutil.copy2", side_effect=AssertionError("copy")),
            mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")),
        ):
            for spec in (
                DependencySpec("nothing-here", "nothing", executables=("viwo-no-such-tool",)),
                DependencySpec("py-missing", "x", kind="python", import_name="viwo_no_module"),
                DependencySpec("per-os", "y", executables={"windows": ("no1",), "linux": ("no2",)}),
            ):
                self.assertIsNone(layer.tools.locate(spec))
        self.assertEqual(writes, [])
        self.assertFalse(os.environ.get("VIWO_INSTALLED_SOMETHING"))


if __name__ == "__main__":
    unittest.main()
