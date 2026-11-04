"""L1/L3: edges of small core pieces, each as what the user is told: an unknown or foreign OS
layer is refused by name; a patch address outside every section, an asm patch without Keystone
or one it cannot assemble, and a file with no unique signature are named; a stale antivirus
journal is cleaned up, or said when it cannot be; a job that crashes is a failed job with the
cause; the capture routes name a bad delay and a run with no process given."""

from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.contracts import ViwoError


class OsSelectionTests(unittest.TestCase):
    def test_unknown_and_foreign_layers_are_refused(self) -> None:
        from viwo.os import select_os

        with self.assertRaises(ViwoError) as err:
            select_os("beos")
        self.assertEqual(err.exception.code, "invalid_request")
        foreign = "linux" if sys.platform == "win32" else "windows"
        with self.assertRaises(ViwoError) as err:
            select_os(foreign)
        self.assertEqual(err.exception.code, "refused")


class PatchToolTests(unittest.TestCase):
    def test_addresses_assembly_and_signatures_say_why_not(self) -> None:
        from tests.test_patchsets import make_pe
        from viwo.core import patch_tools

        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "g.exe"
            make_pe(exe)
            data = exe.read_bytes()
            with self.assertRaisesRegex(ViwoError, "in no section"):
                patch_tools.rva_to_offset(data, 0x7FFF0000)
            self.assertEqual(patch_tools.address_of(b"not a pe", 12), 12)  # raw files: the offset
            host = SimpleNamespace(tools=SimpleNamespace(locate=lambda spec: None))
            with self.assertRaises(ViwoError) as err:
                patch_tools.assemble(host, "nop", data, 0x400)
            self.assertEqual(err.exception.code, "unavailable")
            tool = SimpleNamespace(argv_prefix=("kstool",))
            garbage = SimpleNamespace(stdout="ERROR: invalid operand", stderr="")
            host = SimpleNamespace(
                tools=SimpleNamespace(locate=lambda spec: tool),
                process=SimpleNamespace(run=lambda argv, timeout: garbage),
            )
            with self.assertRaisesRegex(ViwoError, "could not assemble"):
                patch_tools.assemble(host, "frobnicate eax", data, 0x400)
            with mock.patch.dict(sys.modules, {"capstone": None}):
                self.assertEqual(patch_tools.disassemble(data, b"\x90", 0x400), [])
            rng = random.Random(1)
            unique = rng.randbytes(4096)
            pattern, back = patch_tools.signature(unique, 2000)
            self.assertEqual(unique.count(bytes.fromhex(pattern.replace(" ", ""))), 1)
            with self.assertRaisesRegex(ViwoError, "no unique signature"):
                patch_tools.signature(b"\xcc" * 4096, 2000)  # all the same: nothing is unique


class ScanJournalTests(unittest.TestCase):
    def test_stale_journals_are_cleaned_or_said(self) -> None:
        from viwo.core import scan_exclusions

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "1.json").write_text(json.dumps({"pid": 999999, "paths": ["C:/w"]}))
            (folder / "2.json").write_text("{damaged")
            said = []
            for removed in (False, True):
                rt = SimpleNamespace(os=SimpleNamespace(include_in_scan=lambda paths, r=removed: r))
                with (
                    mock.patch.object(scan_exclusions, "_journals", return_value=folder),
                    mock.patch.object(scan_exclusions, "pid_alive", return_value=False),
                ):
                    scan_exclusions.undo_leftovers(rt, said.append)
            self.assertTrue(any("not removed yet" in s for s in said))
            self.assertTrue(any("unreadable" in s for s in said))
            self.assertFalse((folder / "1.json").exists())  # removed once Defender agreed


class JobTests(unittest.TestCase):
    def test_a_crash_is_a_failed_job_with_its_cause(self) -> None:
        from viwo.core.jobs import JobRunner

        runner = JobRunner(None)
        job = runner.submit("x", lambda jid, sink, cancel: 1 / 0, background=True)
        done = runner.wait(job.job_id, timeout=10)
        self.assertEqual(done.state, "failed")
        self.assertEqual(done.error["code"], "internal")
        self.assertIn("ZeroDivisionError", done.error["message"])
        with self.assertRaises(ViwoError):
            runner.get("no-such-job")


class CaptureRouteTests(unittest.TestCase):
    def test_bad_delay_and_no_process_are_named(self) -> None:
        from tests.helpers import runtime
        from viwo.api.app import App
        from viwo.api.handlers import GET, POST

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = App(runtime(root, "[startup]\nfeatures = extraction, capture\n"))
            app.set_workspace(root / "ws")
            (root / "game").mkdir()
            exe = root / "game" / "g.exe"
            exe.write_bytes(b"MZ")
            body = {"gamePath": str(root / "game"), "exePath": str(exe), "captureAfter": "soon"}
            self.assertEqual(POST["/api/capture"](app, body)["code"], "invalid_request")
            self.assertEqual(POST["/api/runtime/dump"](app, {})["code"], "invalid_request")
            shell = mock.Mock()
            shell.pick_file.return_value = None
            with mock.patch.object(app.rt.os, "_shell", shell):
                GET["/api/browse-file"](app, {"initialPath": str(exe)})
            self.assertEqual(shell.pick_file.call_args[0][1], root / "game")  # starts in its folder


if __name__ == "__main__":
    unittest.main()
