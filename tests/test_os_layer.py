"""L1: OS layer conformance (doc 1.7). Both filesystem policies run on any host."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path

from viwo.contracts import CancelToken, DependencySpec
from viwo.os import select_os
from viwo.os.linux import PosixFs
from viwo.os.windows import WindowsFs

NASTY = (
    "",
    ".",
    "..",
    "CON",
    "nul.txt",
    "a/b",
    "a\\b",
    "x:y",
    "trail. ",
    "tab\tname",
    'q?*<>|"',
    "\x00zero",
    "é-ü-日本.png",
    "a" * 300,
)
POSIX = sys.platform != "win32"


class FileSystemPolicyTests(unittest.TestCase):
    def test_sanitize_always_yields_valid_names(self) -> None:
        for fs in (PosixFs(), WindowsFs()):
            for raw in NASTY:
                with self.subTest(fs=type(fs).__name__, raw=raw):
                    name = fs.sanitize_filename(raw, "fallback")
                    self.assertTrue(fs.is_valid_filename(name), name)
                    self.assertNotIn("/", name)

    def test_windows_rules(self) -> None:
        fs = WindowsFs()
        self.assertFalse(fs.is_valid_filename("CON.txt"))
        self.assertFalse(fs.is_valid_filename("name."))
        self.assertEqual(fs.path_key(Path("A/B.PNG")), fs.path_key(Path("a/b.png")))

    def test_posix_is_case_sensitive(self) -> None:
        fs = PosixFs()
        self.assertNotEqual(fs.path_key(Path("A.png")), fs.path_key(Path("a.png")))


class ToolLocatorTests(unittest.TestCase):
    def test_search_order(self) -> None:
        layer = select_os()
        with tempfile.TemporaryDirectory() as tmp:
            tool = Path(tmp) / ("faketool.exe" if not POSIX else "faketool")
            tool.write_text("#!/bin/sh\necho hi\n")
            tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
            spec = DependencySpec("faketool", "Fake", executables=("faketool",), env_var="VIWO_FT")
            self.assertIsNone(layer.tools.locate(spec))
            os.environ["VIWO_FT"] = str(tool)
            try:
                self.assertEqual(layer.tools.locate(spec).source, "env")
            finally:
                del os.environ["VIWO_FT"]
            overridden = select_os(tool_overrides={"faketool": str(tool)})
            self.assertEqual(overridden.tools.locate(spec).source, "config")

    def test_python_module(self) -> None:
        spec = DependencySpec("json", "json", kind="python", import_name="json")
        found = select_os().tools.locate(spec)
        self.assertEqual(found.argv_prefix[-2:], ("-m", "json"))


class ProcessRunnerTests(unittest.TestCase):
    def test_run_and_exit_code(self) -> None:
        runner = select_os().process
        result = runner.run([sys.executable, "-c", "import sys; print('ok'); sys.exit(3)"])
        self.assertEqual((result.returncode, result.stdout.strip()), (3, "ok"))
        self.assertGreater(runner.max_command_length, 1000)

    def test_timeout_kills_tree(self) -> None:
        code = (
            "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"
            "'import time; time.sleep(30)']); time.sleep(30)"
        )
        start = time.monotonic()
        result = select_os().process.run([sys.executable, "-c", code], timeout=1)
        self.assertTrue(result.timed_out)
        self.assertLess(time.monotonic() - start, 15)

    def test_cancel(self) -> None:
        token = CancelToken()
        token.cancel()
        result = select_os().process.run(
            [sys.executable, "-c", "import time; time.sleep(30)"], cancel=token
        )
        self.assertTrue(result.timed_out)

    def test_running_images_lists_this_interpreter(self) -> None:
        names = select_os().process.running_images()
        self.assertTrue(any(n.startswith("python") for n in names), sorted(names)[:8])


class BatchFileTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows batch files")
    def test_batch_file_in_a_folder_with_spaces_runs_with_its_arguments(self) -> None:
        """Doc 1.2: `.bat` tools run through cmd; a path with spaces must survive `cmd /c`."""
        from viwo.contracts import DependencySpec

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "tool home"
            folder.mkdir()
            bat = folder / "echoargs.bat"
            bat.write_text("@echo off" + os.linesep + "echo got %1 %2" + os.linesep)
            layer = select_os("windows", {"echoargs": str(bat)})
            tool = layer.tools.locate(DependencySpec("echoargs", "echo", executables=("echoargs",)))
            result = layer.process.run([*tool.argv_prefix, "one", "two"], timeout=20)
            self.assertEqual((result.returncode, result.stdout.strip()), (0, "got one two"))


class StreamingRunTests(unittest.TestCase):
    def test_lines_arrive_while_the_tool_runs_and_output_is_still_captured(self) -> None:
        code = "import sys,time\nfor i in range(3):\n print('line', i, flush=True)\n"
        code += " time.sleep(0.05)\nprint('err', file=sys.stderr)"
        seen = []
        result = select_os().process.run(
            [sys.executable, "-c", code], timeout=30, on_line=seen.append
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.stdout.splitlines(), ["line 0", "line 1", "line 2"])
        self.assertIn("err", result.stderr)
        self.assertEqual(sorted(seen), ["err", "line 0", "line 1", "line 2"])

    def test_streaming_respects_cancel(self) -> None:
        token = CancelToken()
        token.cancel()
        result = select_os().process.run(
            [sys.executable, "-c", "import time; time.sleep(20)"],
            timeout=30,
            cancel=token,
            on_line=lambda line: None,
        )
        self.assertTrue(result.timed_out)


if __name__ == "__main__":
    unittest.main()
