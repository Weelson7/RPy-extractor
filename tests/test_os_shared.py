"""L1: what both OS layers share. A tool's output reaches the line callback and the result in
order even when the callback crashes; a timeout or a cancel kills the tree and is reported as
such; GUI children are tracked and reaped; the locator's search order is config override, env
var, python module, PATH, known folders; a broken process list or a missing display is advice,
never a crash."""

from __future__ import annotations

import os
import random
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.contracts.types import DependencySpec
from viwo.os import _shared, select_os
from viwo.os._shared import CHILDREN, Locator, TkShell, _module_present, _tk_ask, open_with

assert issubclass(type(select_os().shell), TkShell)


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


class RunnerTests(unittest.TestCase):
    def test_lines_arrive_in_order_whatever_the_callback_does(self) -> None:
        rng = random.Random(5)
        runner = select_os().process
        for _ in range(5):
            lines = [f"line {i} {rng.randrange(1000)}" for i in range(rng.randint(1, 30))]
            code = "import sys\n" + "".join(f"print({line!r}, flush=True)\n" for line in lines)
            code += "print('err', file=sys.stderr)\nsys.exit(3)\n"
            seen = []

            def relay(line, seen=seen):
                seen.append(line)
                if rng.random() < 0.3:
                    raise RuntimeError("a broken progress relay")

            result = runner.run(_py(code), timeout=60, on_line=relay)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(result.stdout.splitlines(), lines)
            self.assertEqual([s for s in seen if s != "err"], lines)  # every line, in order
            self.assertIn("err", result.stderr)

    def test_timeout_and_cancel_kill_and_say_so(self) -> None:
        runner = select_os().process
        slow = _py("import time; time.sleep(60)")
        started = time.monotonic()
        result = runner.run(slow, timeout=0.5)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, -9)
        cancel = SimpleNamespace(cancelled=True)
        self.assertTrue(runner.run(slow, timeout=60, cancel=cancel).timed_out)
        self.assertLess(time.monotonic() - started, 30)
        env = runner.run(_py("import os; print(os.environ['VIWO_X'])"), env={"VIWO_X": "y"})
        self.assertEqual(env.stdout.strip(), "y")
        self.assertEqual(runner.python_executable, sys.executable)

    def test_children_are_tracked_and_reaped(self) -> None:
        runner = select_os().process
        with tempfile.TemporaryDirectory() as tmp:
            child = runner.launch(_py("import time; time.sleep(60)"), cwd=tmp, env={"A": "1"})
            self.assertIn(child, CHILDREN)
            self.assertTrue(child.alive())
            _shared._reap_children()  # what atexit runs
            for _ in range(50):
                if not child.alive():
                    break
                time.sleep(0.1)
            self.assertFalse(child.alive())
            _shared._reap_children()  # a dead child is left alone

    def test_a_broken_process_list_is_no_list(self) -> None:
        runner = _shared.SubprocessRunner(100, {}, lambda p: None, lambda: 1 / 0)
        self.assertEqual(runner.running_images(), set())


class LocatorTests(unittest.TestCase):
    def test_search_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mine = root / "mine.exe"
            mine.write_bytes(b"")
            env_tool = root / "env.exe"
            env_tool.write_bytes(b"")
            (root / "Tool" / "bin").mkdir(parents=True)
            known = root / "Tool" / "bin" / "toolx.exe"
            known.write_bytes(b"")
            spec = DependencySpec(
                "toolx",
                "Tool X",
                env_var="VIWO_TOOLX",
                executables=("toolx",),
                install_dirs=("Tool",),
            )
            wrap = lambda p: (str(p),)  # noqa: E731

            def find(overrides, env):
                locator = Locator(overrides, [root], [".exe", ""], wrap, "windows")
                with mock.patch.dict(os.environ, {"VIWO_TOOLX": env}):
                    with mock.patch.object(_shared.shutil, "which", return_value=None):
                        return locator.locate(spec)

            self.assertEqual(find({"toolx": str(mine)}, str(env_tool)).source, "config")
            self.assertEqual(find({}, str(env_tool)).source, "env")
            self.assertEqual(find({"toolx": str(root / "gone")}, "").path, str(known))
            prefix = find({"toolx": [str(mine), "-jar", str(env_tool)]}, "")
            self.assertEqual((prefix.source, prefix.path), ("config", str(env_tool)))
            gone = find({"toolx": [str(root / "gone.exe")]}, "")  # a stale override: keep looking
            self.assertEqual((gone.source, gone.path), ("known_dir", str(known)))
            on_path = Locator({}, [], [""], wrap, "windows")
            with mock.patch.object(_shared.shutil, "which", return_value=str(mine)):
                self.assertEqual(on_path.locate(spec).source, "path")
            module = DependencySpec("json", "json", kind="python")
            self.assertEqual(on_path.locate(module).argv_prefix[-1], "json")
            missing = DependencySpec("no_such_module_viwo", "x", kind="python")
            self.assertIsNone(on_path.locate(missing))

    def test_module_present_never_raises(self) -> None:
        self.assertTrue(_module_present("os"))
        with mock.patch.dict(sys.modules, {"blocked_viwo": None}):
            self.assertFalse(_module_present("blocked_viwo"))
        with mock.patch.object(_shared.importlib.util, "find_spec", side_effect=ImportError):
            self.assertFalse(_module_present("broken_parent_viwo.child"))


class ShellTests(unittest.TestCase):
    def test_pickers_and_open_with_say_none_or_why(self) -> None:
        ok, why = open_with(["no-such-program-viwo"])
        self.assertFalse(ok)
        self.assertTrue(why)
        with mock.patch.object(_shared.subprocess, "Popen"):
            self.assertEqual(open_with(["x"]), (True, ""))
        with mock.patch.dict(sys.modules, {"tkinter": None}):
            self.assertIsNone(_tk_ask("askdirectory"))  # no display: None, never a crash
        for chosen, want in (("C:/picked", Path("C:/picked")), ("", None)):  # picked, cancelled
            tk = SimpleNamespace(Tk=lambda: mock.Mock())
            dialog = SimpleNamespace(askdirectory=lambda **o: chosen)
            tk.filedialog = dialog
            with mock.patch.dict(sys.modules, {"tkinter": tk, "tkinter.filedialog": dialog}):
                self.assertEqual(_tk_ask("askdirectory", title="x"), want)
        asked = []

        def ask(kind, **options):
            asked.append((kind, options))
            return None

        shell = select_os().shell  # a TkShell with its OS's open_folder
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(_shared, "_tk_ask", ask):
            file = Path(tmp) / "a.txt"
            file.write_text("x")
            shell.pick_folder("Pick", Path(tmp))
            shell.pick_file("Pick", file, ("*.rdc",))
            shell.pick_file("Pick")
        self.assertEqual(asked[0][1]["initialdir"], tmp)
        self.assertEqual(asked[1][1]["initialdir"], tmp)  # a file starts in its folder
        self.assertEqual(asked[1][1]["filetypes"][0], ("Supported files", "*.rdc"))
        self.assertEqual(asked[2][1]["filetypes"], [("All files", "*.*")])

    def test_the_host_answers_through_its_services(self) -> None:
        host = select_os()
        self.assertIs(host.fs, host._fs)
        self.assertIs(host.shell, host._shell)
        me = Path(sys.executable).name
        self.assertIn(os.getpid(), host.pids_of(me))


if __name__ == "__main__":
    unittest.main()
