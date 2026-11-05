"""L3/L5: rung D4, profile.sample. A real busy child process is sampled through the OS layer
(Windows: thread contexts; Linux: perf when present); the checks are properties: the busy thread
spends most samples in the interpreter, shares add up, a pc inside a known export is named after
it, a pc outside every module stays a raw address, and `viwo profile` writes its report."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.test_emulate import pe64
from viwo.core.capture.profile import exports, place, report
from viwo.os import select_os

BUSY = "while True: sum(i * i for i in range(1000))"


class PlaceTests(unittest.TestCase):
    def test_a_pc_is_named_after_the_export_below_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dll = Path(tmp) / "game.dll"
            dll.write_bytes(pe64())
            self.assertEqual(exports(dll), [(0x1000, "xor_decode")])
            modules = [(0x140000000, 0x3000, str(dll))]
            for offset in (0, 3, 0x7F):  # inside the routine and past it: the nearest below
                self.assertEqual(
                    place(0x140001000 + offset, modules, {}), f"game.dll!xor_decode+{offset:#x}"
                )
            self.assertEqual(place(0x140000010, modules, {}), "game.dll+0x10")  # below exports
            self.assertEqual(place(0x10, modules, {}), "0x10")  # outside every module
            self.assertEqual(exports(Path(tmp) / "missing.dll"), [])

    def test_shares_add_up_and_follow_the_counts(self) -> None:
        samples = [(1, 0x140001000)] * 30 + [(2, 0x140001004)] * 10 + [(2, 0x5)] * 10
        with tempfile.TemporaryDirectory() as tmp:
            dll = Path(tmp) / "game.dll"
            dll.write_bytes(pe64())
            rep = report(samples, [(0x140000000, 0x3000, str(dll))])
        self.assertEqual(rep["samples"], 50)
        self.assertAlmostEqual(sum(t["percent"] for t in rep["threads"]), 100.0, places=1)
        self.assertEqual(rep["threads"][0], {"tid": 1, "percent": 60.0})
        self.assertEqual(rep["modules"][0], {"module": "game.dll", "percent": 80.0})


class LinuxProbeTests(unittest.TestCase):
    """The perf side, as data: what perf prints and what /proc/<pid>/maps holds."""

    MAPS = (
        "55d0c0000000-55d0c0001000 r--p 00000000 08:01 1 /usr/bin/game\n"
        "55d0c0001000-55d0c0009000 r-xp 00001000 08:01 1 /usr/bin/game\n"
        "7f00a0000000-7f00a0100000 r-xp 00000000 08:01 2 /usr/lib/libc.so.6\n"
        "7f00a0200000-7f00a0300000 rw-p 00000000 00:00 0 [heap]\n"
    )

    def test_maps_become_module_spans_and_perf_lines_samples(self) -> None:
        from unittest import mock

        from viwo.os import _linux_probe as probe

        with mock.patch.object(Path, "read_text", return_value=self.MAPS):
            spans = {path: (base, size) for base, size, path in probe.modules_of(42)}
        self.assertEqual(spans["/usr/bin/game"], (0x55D0C0000000, 0x9000))  # both mappings
        self.assertEqual(spans["/usr/lib/libc.so.6"], (0x7F00A0000000, 0x100000))
        self.assertNotIn("[heap]", spans)
        script = "   1234 55d0c0001234\nnoise line\n 99 7f00a0000010\n"
        self.assertEqual(probe.parse(script), [(1234, 0x55D0C0001234), (99, 0x7F00A0000010)])

    def test_without_perf_or_permission_it_says_why(self) -> None:
        from types import SimpleNamespace
        from unittest import mock

        from viwo.os import _linux_probe as probe

        with mock.patch.object(probe.shutil, "which", return_value=None):
            with self.assertRaisesRegex(OSError, "perf is not installed"):
                probe.sample_threads(1, 1)
        refused = SimpleNamespace(
            returncode=1, stderr="perf_event_paranoid setting is 4", stdout=""
        )
        with (
            mock.patch.object(probe.shutil, "which", return_value="/usr/bin/perf"),
            mock.patch.object(probe, "modules_of", return_value=[]),
            mock.patch.object(probe.subprocess, "run", return_value=refused),
        ):
            with self.assertRaisesRegex(OSError, "paranoid"):
                probe.sample_threads(1, 1)


@unittest.skipUnless(os.name == "nt", "the Windows sampler (Linux samples through perf)")
class SamplerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.busy = subprocess.Popen([sys._base_executable, "-c", BUSY])
        self.addCleanup(self.busy.kill)
        time.sleep(0.8)

    def test_a_busy_interpreter_is_found_hot_in_its_own_dll(self) -> None:
        samples, modules = select_os().sample_threads(self.busy.pid, 1.0)
        rep = report(samples, modules)
        busiest = rep["threads"][0]["tid"]
        hot = report([s for s in samples if s[0] == busiest], modules)["modules"][0]["module"]
        self.assertGreater(rep["samples"], 10)  # a loaded machine samples less; a dozen suffice
        self.assertRegex(hot.lower(), r"python3\d*\.dll")

    def test_viwo_profile_writes_its_report(self) -> None:
        from tests.test_cli import run

        with tempfile.TemporaryDirectory() as tmp:
            argv = ["--json", "--features", "extraction,capture", "profile"]
            argv += ["--pid", str(self.busy.pid), "--seconds", "1", "--workspace", tmp]
            code, out, err = run(argv)
            self.assertEqual(code, 0, out + err)
            data = json.loads(out)["data"]
            hotspots = json.loads((Path(data["outputDir"]) / "hotspots.json").read_text())
            self.assertEqual(hotspots["samples"], data["samples"])
            self.assertIn(hotspots["hotspots"][0]["where"].split(" ")[0], data["top"])


if __name__ == "__main__":
    unittest.main()
