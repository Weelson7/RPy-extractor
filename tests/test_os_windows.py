"""L1: the Windows OS layer: file names it produces are always legal (or the fallback), long
paths take the extended-length form exactly past the limit, PowerShell lists quote any path,
Defender exclusions never touch what the user excluded and say why when skipped, and a dump
that fails leaves no file behind. The ctypes parts run on Windows only."""

from __future__ import annotations

import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.os import windows
from viwo.os.windows import LONG_PATH_LIMIT, WindowsFs, WindowsOS, WindowsShell

WIN = sys.platform == "win32"
BS = chr(92)  # a backslash


class FsTests(unittest.TestCase):
    def test_produced_names_are_always_legal(self) -> None:
        rng = random.Random(4)
        fs = WindowsFs()
        alphabet = 'abcXYZ09 ._-:*?"<>|/' + BS + "é"
        for _ in range(500):
            raw = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
            raw = rng.choice(["", "CON", "nul.txt", "com1", "aux.tar.gz"]) + raw
            name = fs.sanitize_filename(raw, "fallback")
            self.assertTrue(name == "fallback" or fs.is_valid_filename(name), (raw, name))
        self.assertFalse(fs.case_sensitive)
        self.assertEqual(fs.path_key(Path("A/b.TXT")), fs.path_key(Path("a/B.txt")))
        self.assertFalse(fs.is_valid_filename("x" * 256))

    def test_long_paths_switch_form_exactly_past_the_limit(self) -> None:
        rng = random.Random(9)
        fs = WindowsFs()
        for _ in range(100):
            depth = rng.randint(1, 40)
            path = Path("C:" + BS + BS.join("d" * rng.randint(1, 12) for _ in range(depth)))
            out = str(fs.long_path(path))
            if len(str(path)) < LONG_PATH_LIMIT:
                self.assertEqual(out, str(path))
            else:
                self.assertTrue(out.startswith(BS * 2 + "?" + BS), out)
                self.assertEqual(str(fs.long_path(Path(out))), out)  # already extended: kept
        unc = BS * 2 + "server" + BS + "share" + BS + ("x" * 10 + BS) * 30
        with mock.patch.object(windows.os.path, "abspath", lambda t: t):
            self.assertTrue(str(fs.long_path(Path(unc))).startswith(BS * 2 + "?" + BS + "UNC"))


class ShellAndRootsTests(unittest.TestCase):
    def test_open_folder_says_why_it_did_not(self) -> None:
        shell = WindowsShell()
        self.assertFalse(shell.open_folder(Path("Z:/no/such/folder"))[0])
        with tempfile.TemporaryDirectory() as tmp:
            for effect, ok in ((None, True), (OSError("no handler"), False)):
                with mock.patch.object(windows.os, "startfile", side_effect=effect, create=True):
                    got = shell.open_folder(Path(tmp))
                self.assertEqual(got[0], ok)
                self.assertEqual(bool(got[1]), not ok)

    def test_install_roots_follow_the_environment(self) -> None:
        rng = random.Random(1)
        keys = ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "ProgramData", "SCOOP")
        for _ in range(20):
            env = {k: f"C:/{k}" for k in keys if rng.random() < 0.5}
            with mock.patch.dict(windows.os.environ, {k: "" for k in keys}):
                with mock.patch.dict(windows.os.environ, env):
                    roots = windows._install_roots()
            for key in ("ProgramFiles", "ProgramData"):
                self.assertEqual(Path(f"C:/{key}") in roots, key in env)
            self.assertEqual(Path("C:/LOCALAPPDATA/Programs") in roots, "LOCALAPPDATA" in env)
            self.assertTrue(any(str(r).endswith("shims") for r in roots))

    def test_homes(self) -> None:
        host = WindowsOS()
        with mock.patch.dict(windows.os.environ, {"APPDATA": "C:/a", "LOCALAPPDATA": "C:/l"}):
            self.assertEqual((host.config_home(), host.data_home()), (Path("C:/a"), Path("C:/l")))
        with mock.patch.dict(windows.os.environ, {"APPDATA": "", "LOCALAPPDATA": ""}):
            self.assertEqual(host.config_home().name, "Roaming")
            self.assertEqual(host.data_home().name, "Local")
        self.assertEqual(host.is_supported_host(), WIN)
        self.assertEqual(windows._wrap(Path("x.cmd"))[:3], ("cmd", "/c", "call"))


class DefenderTests(unittest.TestCase):
    def test_ps_lists_quote_any_path(self) -> None:
        rng = random.Random(3)
        for _ in range(100):
            paths = [
                "".join(rng.choice("ab'c d") for _ in range(rng.randint(1, 8))) for _ in range(3)
            ]
            listed = windows._ps_list(paths)
            parsed = [p[1:-1].replace("''", "'") for p in _split(listed)]
            self.assertEqual(parsed, paths)

    def test_exclusions_never_touch_the_users_own_and_say_why_when_skipped(self) -> None:
        host = WindowsOS()
        with mock.patch.object(windows, "_is_admin", return_value=False):
            done, why = host.exclude_from_scan([Path("C:/w")])
        self.assertEqual(done, [])
        self.assertIn("elevated", why)
        calls = []

        def ps(command):
            calls.append(command)
            if command.startswith("(Get-MpPreference)"):
                return SimpleNamespace(ok=True, stdout="C:" + BS + "Mine\nc:/w2\n")
            return SimpleNamespace(ok=not command.startswith("Add") or ok, stdout="")

        with mock.patch.object(windows, "_is_admin", return_value=True):
            with mock.patch.object(host, "_ps", ps):
                ok = True
                done, why = host.exclude_from_scan([Path("C:/w"), "c:/w2"])
                self.assertEqual((done, why), ([Path("C:/w")], ""))  # the user's own stays out
                ok = False
                done, why = host.exclude_from_scan([Path("C:/new")])
                self.assertEqual(done, [])
                self.assertIn("refused", why)
                self.assertTrue(host.include_in_scan([]))  # nothing to remove: no call
                self.assertTrue(host.include_in_scan([Path("C:/w")]))
        self.assertTrue(calls[-1].startswith("Remove-MpPreference"))
        fake = SimpleNamespace(windll=SimpleNamespace())  # no shell32: not an admin
        with mock.patch.dict(sys.modules, {"ctypes": fake}):
            self.assertFalse(windows._is_admin())


def _split(listed: str) -> list[str]:
    """Split a PowerShell list of single-quoted strings ('' is a quote inside)."""
    out, cur, inside, i = [], "", False, 0
    while i < len(listed):
        ch = listed[i]
        if ch == "'" and inside and listed[i + 1 : i + 2] == "'":
            cur += "''"
            i += 2
            continue
        if ch == "'":
            inside = not inside
            cur += ch
        elif ch == "," and not inside:
            out.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    return out + [cur]


@unittest.skipUnless(WIN, "Windows process APIs")
class NativeTests(unittest.TestCase):
    def test_liveness_and_a_failed_dump_leaves_nothing(self) -> None:
        import os
        import subprocess

        self.assertTrue(WindowsOS.pid_alive(os.getpid()))
        self.assertFalse(WindowsOS.pid_alive(0x7FFFFFF0))  # no such process
        self.assertTrue(WindowsOS()._ps("$PSVersionTable.PSVersion.Major").stdout.strip().isdigit())
        system = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / "kernel32.dll"
        self.assertTrue(hasattr(windows._load_native(system), "GetTickCount"))
        done = subprocess.run([sys.executable, "-c", "pass"])
        self.assertEqual(done.returncode, 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with self.assertRaises(OSError):
                windows._minidump(0, out)  # the idle process cannot be opened
            with mock.patch("msvcrt.get_osfhandle", return_value=0):
                with self.assertRaises(OSError):
                    windows._minidump(os.getpid(), out)  # dbghelp refuses a bad handle
            self.assertEqual(list(out.iterdir()), [])  # never a partial dump that looks whole
        with mock.patch("viwo.os._win_probe.sample_threads", return_value=([1], [2])) as sample:
            self.assertEqual(windows._sample(5, 1.0), ([1], [2]))
        sample.assert_called_once_with(5, 1.0, None)


if __name__ == "__main__":
    unittest.main()
