"""L1: defaults and small invariants. An OS layer without a capability says it cannot, never
pretends; the zip packer replaces exactly the edited members, adds the new ones, keeps the rest
byte for byte and leaves the container untouched when it fails; one plugin's verify crash stays
on that plugin; provenance survives damaged lines and files that left the workspace."""

from __future__ import annotations

import json
import random
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from viwo.backends.packers import ZipPacker
from viwo.contracts.os import OS, ProcessRunner
from viwo.contracts.types import OutcomeKind
from viwo.contracts.workspace import PROVENANCE_FILE
from viwo.core import provenance
from viwo.core.pipeline import checks


class BareRunner(ProcessRunner):
    max_command_length = 1000
    python_executable = "python"

    def run(self, argv, cwd=None, timeout=None, cancel=None, env=None, on_line=None):
        raise AssertionError("never called here")


class BareOS(OS):
    """An OS layer with only what the contract requires."""

    os_id = "bare"
    is_supported_host = lambda self: True  # noqa: E731
    process, tools, fs, shell = BareRunner(), None, None, None
    config_home = data_home = lambda self: Path(".")  # noqa: E731


class DefaultTests(unittest.TestCase):
    def test_a_missing_capability_says_it_cannot(self) -> None:
        host = BareOS()
        self.assertEqual(host.process.running_images(), set())
        with self.assertRaisesRegex(NotImplementedError, "cannot launch"):
            host.process.launch(["x"])
        self.assertEqual(host.exclude_from_scan([Path("x")]), ([], ""))  # nothing excluded
        self.assertTrue(host.include_in_scan([]))
        self.assertEqual(host.pids_of("Game.exe"), [])
        self.assertIsNone(host.load_native(Path("oo2ext.dll")))
        with self.assertRaisesRegex(OSError, "cannot sample"):
            host.sample_threads(1, 1.0)
        with self.assertRaisesRegex(NotImplementedError, "cannot dump"):
            host.dump_process(1, Path("."))
        from viwo.os.linux import PosixFs

        self.assertEqual(PosixFs().long_path(Path("a/b")), Path("a/b"))  # the contract default


class ZipPackerTests(unittest.TestCase):
    def test_exactly_the_edits_change(self) -> None:
        rng = random.Random(7)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(15):
                container = root / f"c{case}.zip"
                original = {f"d/f{i}.bin": rng.randbytes(rng.randint(0, 60)) for i in range(6)}
                with zipfile.ZipFile(container, "w") as z:
                    for name, data in original.items():
                        kind = rng.choice([zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
                        z.writestr(name, data, compress_type=kind)
                kinds = {i.filename: i.compress_type for i in zipfile.ZipFile(container).infolist()}
                edits = {}
                for name in rng.sample(sorted(original), rng.randint(0, 3)) + ["new/added.txt"] * (
                    rng.random() < 0.5
                ):
                    src = root / f"e{case}-{len(edits)}"
                    src.write_bytes(rng.randbytes(10))
                    edits[name] = src
                out = ZipPacker().pack(container, edits, None)
                self.assertEqual((out.kind, out.files), (OutcomeKind.OK, len(edits)))
                with zipfile.ZipFile(container) as z:
                    for name, data in original.items():
                        want = edits[name].read_bytes() if name in edits else data
                        self.assertEqual(z.read(name), want)
                        self.assertEqual(z.getinfo(name).compress_type, kinds[name])
                    for name in set(edits) - set(original):
                        self.assertEqual(z.read(name), edits[name].read_bytes())
            broken = root / "broken.zip"
            broken.write_bytes(b"not a zip at all")
            out = ZipPacker().pack(broken, {}, None)
            self.assertEqual(out.kind, OutcomeKind.FAILED)
            self.assertEqual(broken.read_bytes(), b"not a zip at all")
            self.assertFalse(list(root.glob("*.viwo-tmp")))  # no half-written copy left


class VerifyIsolationTests(unittest.TestCase):
    def test_one_plugins_verify_crash_stays_on_its_own_entry(self) -> None:
        from viwo.contracts.pipeline import PluginRun

        empty = SimpleNamespace(found=0, extracted=0)
        none = SimpleNamespace(scanned=0, collected=0, unreadable=[], warnings=[])
        said = checks._verify(empty, none)
        self.assertIn("No files were scanned from source roots.", said)
        self.assertIn("No files were copied into the output folder.", said)

        def plugin(report=None, crash=False):
            def verify_report(ctx, inventory, _, collected):
                if crash:
                    raise RuntimeError("verify blew up")
                return report

            return SimpleNamespace(
                inventory=lambda ctx: [],
                verify_report=verify_report,
                manifest=SimpleNamespace(name="Quiet"),
            )

        failing = SimpleNamespace(ok=False, warnings=(), expected=3, found=1)
        plugins = {"a": plugin(crash=True), "b": plugin(failing)}
        run = SimpleNamespace(rt=SimpleNamespace(plugins=plugins), ctx=lambda pid: None)
        runs = [PluginRun(p, None) for p in ("a", "b")]
        a, b = checks.verified(run, runs, 10)
        self.assertIn("verify blew up", a.warnings[0])
        self.assertFalse(a.verify_passed)
        self.assertEqual(b.warnings, ("verify: Quiet: verification failed",))  # never silent
        self.assertEqual((b.inventory_items, b.inventory_found), (3, 1))


class ProvenanceTests(unittest.TestCase):
    def test_damaged_lines_and_outside_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            (ws / PROVENANCE_FILE).parent.mkdir(parents=True)
            lines = [json.dumps({"path": "a/x.png", "sha256": "1"}), "{damaged", json.dumps([1])]
            (ws / PROVENANCE_FILE).write_text("\n".join(lines) + "\n")
            self.assertEqual([e["path"] for e in provenance.entries(ws)], ["a/x.png"])
            self.assertIsNone(provenance.relative(ws, Path(tmp) / "elsewhere.png"))
            self.assertEqual(provenance.rewrite(ws, {"a/x.png": "b/x.png"}), 1)
            kept = (ws / PROVENANCE_FILE).read_text().splitlines()
            self.assertIn("{damaged", kept)  # a damaged line is kept as it was, not dropped
            self.assertEqual(provenance.entries(ws)[0]["path"], "b/x.png")
            self.assertEqual(provenance.rewrite(ws, {}), 0)


if __name__ == "__main__":
    unittest.main()
