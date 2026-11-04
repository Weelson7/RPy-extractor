"""L3: a sweep of small properties. A settings change that would break the ini is refused and
the ini stays as it was; a patch set that is not one is named, and an export that finds no
unique signature says so per patch; TaleWorlds LZ4 segments inflate, or are skipped without the
module or on bad data; DataTool names a missing tool and failed modes; the protector check names
output it cannot read; a damaged export map is ignored; a capture names anti-cheat services
running now and an offline network."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.contracts import ViwoError
from viwo.contracts.types import OutcomeKind


class SettingsTests(unittest.TestCase):
    def test_a_change_that_breaks_the_ini_leaves_it_untouched(self) -> None:
        from viwo.core.wiring import settings

        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "windows-default.ini"
            ini.write_text("[startup]\nfeatures = extraction\n\n[plugins]\ngeneric = on\n")
            before = ini.read_bytes()
            boom = ViwoError("invalid_request", "bad section")
            with mock.patch.object(settings, "load_ini", side_effect=boom):
                with self.assertRaises(ViwoError):
                    settings.write_settings(ini, {"features": "extraction, capture"})
            self.assertEqual(ini.read_bytes(), before)  # untouched
            self.assertFalse(list(Path(tmp).glob("*.draft")))  # no draft left behind
            settings.write_settings(ini, {"plugins": {"unity": "on"}})  # a new key in a section
            self.assertIn("unity = on", ini.read_text())


class PatchSetFileTests(unittest.TestCase):
    def test_bad_files_and_unsigned_exports_are_named(self) -> None:
        from viwo.core import patchsets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for body in (
                "{not json",
                json.dumps({"schema": 2, "patches": [1]}),
                json.dumps({"schema": 1, "patches": []}),
            ):
                (root / "p.json").write_text(body)
                with self.assertRaises(ViwoError) as err:
                    patchsets.load(root / "p.json")
                self.assertEqual(err.exception.code, "invalid_request")
            game = root / "game"
            game.mkdir()
            (game / "same.bin").write_bytes(b"\xcc" * 4096)  # nothing in it is unique
            patch_set = {"patches": [{"file": "same.bin", "offset": "0x10", "patched": "90"}]}
            report = {"results": [{"file": "same.bin", "offset": 0x10, "old": "cc", "new": "90"}]}
            (root / "out").mkdir()  # the caller's folder
            patchsets.export(game, patch_set, report, root / "out", "p")
            diff = next((root / "out").glob("*.txt")).read_text()
            self.assertIn("no AOB", diff)


class TaleWorldsSegmentTests(unittest.TestCase):
    def test_lz4_segments_inflate_or_are_skipped(self) -> None:
        import lz4.block

        from viwo.plugins.taleworlds import _inflate

        data = b"texture rows " * 50
        packed = lz4.block.compress(data, store_size=False)
        self.assertEqual(_inflate(packed, len(data), 1), data)
        self.assertIsNone(_inflate(b"\xff" * 20, len(data), 1))  # bad data: skipped, counted
        self.assertIsNone(_inflate(packed, len(data), 7))  # an unknown format
        with mock.patch.dict(sys.modules, {"lz4": None, "lz4.block": None}):
            self.assertIsNone(_inflate(packed, len(data), 1))


class DataToolTests(unittest.TestCase):
    def test_a_missing_tool_and_failed_modes_are_named(self) -> None:
        from viwo.plugins.overwatch import DataToolExporter

        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            tool = SimpleNamespace(argv_prefix=("DataTool",))

            def ctx(located, ok_modes):
                def run(argv, timeout, cancel):
                    ok = argv[-2] in ok_modes
                    if ok:
                        (Path(argv[-1])).mkdir(parents=True, exist_ok=True)
                        (Path(argv[-1]) / "x.png").write_bytes(b"x")
                    return SimpleNamespace(ok=ok)

                return SimpleNamespace(
                    os=SimpleNamespace(
                        tools=SimpleNamespace(locate=lambda s: tool if located else None),
                        process=SimpleNamespace(run=run),
                    ),
                    options={"modes": "extract-unlocks, extract-maps"},
                    staging=staging,
                    game_root=staging,
                    cancel=None,
                    log=lambda *a, **k: None,
                )

            self.assertEqual(
                DataToolExporter().export(ctx(False, ())).kind, OutcomeKind.UNAVAILABLE
            )
            self.assertIn("DataTool failed", DataToolExporter().export(ctx(True, ())).error)
            partial = DataToolExporter().export(ctx(True, ("extract-unlocks",)))
            self.assertEqual(partial.kind, OutcomeKind.OK)
            self.assertTrue(any("failed modes" in n for n in partial.notes))


class SmallEdgeTests(unittest.TestCase):
    def test_protector_output_export_maps_and_capture_warnings(self) -> None:
        from viwo.contracts import workspace as ws
        from viwo.contracts.analysis import AnalysisTarget
        from viwo.core.analysis.identify import DetectItEasy
        from viwo.core.capture import policy
        from viwo.core.pipeline.sources import _export_map

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "g.exe"
            exe.write_bytes(b"MZ")
            out = SimpleNamespace(ok=True, timed_out=False, stdout="not json at all", stderr="")
            ctx = SimpleNamespace(
                os=SimpleNamespace(
                    tools=SimpleNamespace(locate=lambda s: SimpleNamespace(argv_prefix=("diec",))),
                    process=SimpleNamespace(run=lambda argv, **k: out),
                ),
                options={},
                staging=root,
                cancel=None,
                log=lambda *a, **k: None,
            )
            found = DetectItEasy().analyze(
                AnalysisTarget("g", "native_binary", (exe,), "user"), ctx
            )
            self.assertEqual(found.kind, OutcomeKind.FAILED)  # unreadable output: nothing found
            (root / ws.EXPORT_MAP).write_text("{damaged")
            self.assertEqual(_export_map(root, "unity"), {})
            rt = SimpleNamespace(
                os=SimpleNamespace(
                    process=SimpleNamespace(running_images=lambda: {"easyanticheat.exe"})
                )
            )
            with mock.patch.object(policy, "network_reachable", return_value=False):
                said = policy.warnings_for(root, [], rt)
            self.assertTrue(any("anti-cheat service running now" in w for w in said))
            with mock.patch.object(
                policy.socket, "create_connection", side_effect=OSError("offline")
            ):
                self.assertFalse(policy.network_reachable())


if __name__ == "__main__":
    unittest.main()
