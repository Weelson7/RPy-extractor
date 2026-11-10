"""L3: `hook.inject` (doc 11.7, rung D4): the user's own script through the pinned Frida's own
command line, a tracked child. Properties: the launch is Frida's quiet attach to the given pid
with the user's script and time, from the pinned folder, and never spawns or elevates anything;
every line Frida prints reaches the console in order and the workspace log, in a new folder per
run; a refused attach ends the run at once and fails with what Frida said; the stop ViWo puts
to Frida's idle process after its time is not a failure; a missing tool, script or time and the
switched-off arm are named; the CLI, the API route and the job kind reach the same run; the
pin and its hash locks agree."""

import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import runtime
from viwo.contracts.errors import ViwoError
from viwo.contracts.types import ProcessResult
from viwo.core import thirdparty
from viwo.core.capture import hook as hooks
from viwo.core.capture.runtime import FRIDA, RuntimeRequest, run

FAKE = """import sys, time
args = sys.argv[1:]
print("argv " + " ".join(args[:6]), flush=True)
print(open(args[args.index("-l") + 1]).read().strip(), flush=True)
print("late", file=sys.stderr, flush=True)
time.sleep(float(args[args.index("-t") + 1]))
"""


class HookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.rt = runtime(self.root, "[startup]\nfeatures = extraction, capture\n")
        self.script = self.root / "my hook.js"
        self.script.write_text("console.log('mine');", encoding="utf-8")
        found = mock.patch.object(self.rt.os.tools, "locate", return_value=SimpleNamespace())
        found.start()
        self.addCleanup(found.stop)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "off").mkdir()  # a second runtime with the dynamic arm off

    def req(self, **given) -> RuntimeRequest:
        return RuntimeRequest(self.root / "ws", **{"pid": 42, "script": self.script, **given})

    def fake(self, said: list[str], result: ProcessResult, seen: list):
        def process_run(argv, cwd=None, timeout=None, cancel=None, env=None, on_line=None):
            seen.append(SimpleNamespace(argv=argv, cwd=cwd, timeout=timeout, env=env))
            for line in said:
                on_line(line)
                if cancel.cancelled:  # the runner stops the tree on the next look
                    return ProcessResult(-9, "", "", timed_out=True)
            return result

        return mock.patch.object(self.rt.os.process, "run", process_run)

    def test_the_launch_is_a_quiet_attach_and_every_line_is_relayed_and_kept(self) -> None:
        rng = random.Random(11)
        for case in range(12):
            pid, seconds = rng.randint(1, 99999), rng.choice([0.5, 3, 10, 600])
            said = [f"line {rng.random()}" for _ in range(rng.randint(0, 9))]
            ended = ProcessResult(*rng.choice([(0, "", "", False), (-9, "", "", True)]))
            seen, events = [], []
            with self.fake(said, ended, seen):
                done = run(self.rt, "hook", self.req(pid=pid, seconds=seconds), events.append)
            argv = seen[0].argv
            head = [sys.executable, "-m", "frida_tools.repl", "-q", "-t", f"{seconds:g}"]
            self.assertEqual(argv, [*head, "-p", str(pid), "-l", str(self.script.resolve())])
            self.assertFalse({"-f", "--file", "runas", "sudo", "-H", "-U"} & set(argv), case)
            self.assertIn(str(self.root / "third_party" / "python"), seen[0].env["PYTHONPATH"])
            self.assertEqual(seen[0].timeout, seconds + hooks.GRACE)
            told = [e.message for e in events]
            self.assertEqual([m for m in told if m in said], said)  # in order, none dropped
            self.assertIn(str(pid), told[0])  # what, where and how long, said before it runs
            log = Path(done["log"])
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), said)
            self.assertEqual((done["lines"], done["stopped"]), (len(said), False))
            self.assertEqual(seen[0].cwd, log.parent)
        runs = list((self.root / "ws" / ".runtime" / "hook").iterdir())
        self.assertEqual(len(runs), 12)  # a new folder per run, never an earlier run's log

    def test_a_running_anti_cheat_service_is_a_warning_never_a_gate(self) -> None:
        from viwo.core.capture.policy import load_policy

        image, name = next(iter(load_policy()["anti_cheat_services"].items()))
        for images, warned in ((set(), False), ({"explorer.exe"}, False), ({image}, True)):
            events, seen = [], []
            running = mock.patch.object(self.rt.os.process, "running_images", lambda i=images: i)
            with running, self.fake(["ran"], ProcessResult(0, "", ""), seen):
                run(self.rt, "hook", self.req(seconds=1), events.append)
            self.assertEqual(len(seen), 1)  # it ran either way
            warns = [e.message for e in events if e.level == "warn"]
            self.assertEqual(bool(warns), warned)
            if warned:
                self.assertIn(name, warns[0])
                self.assertIn("does not evade", warns[0])

    def test_a_refused_attach_stops_at_once_and_other_ends_are_named(self) -> None:
        refused = ["Failed to attach: unable to find process with pid 42", "never reached"]
        with self.fake(refused, ProcessResult(0, "", ""), []):
            with self.assertRaises(ViwoError) as err:
                hooks.hook(self.rt, self.req())
        self.assertEqual(err.exception.code, "failed")
        self.assertEqual(err.exception.hint, refused[0])  # Frida's own words, nothing after
        with self.fake(["Error: boom"], ProcessResult(1, "", "Error: boom"), []):
            with self.assertRaisesRegex(ViwoError, "could not run my hook.js"):
                hooks.hook(self.rt, self.req())
        # a script that itself prints "Failed to ..." later is not a refused attach
        with self.fake(["ok", "Failed to open save"], ProcessResult(-9, "", "", True), []):
            self.assertEqual(hooks.hook(self.rt, self.req())["lines"], 2)
        cancel = SimpleNamespace(cancelled=True)
        with self.fake(["one"], ProcessResult(0, "", ""), []):
            self.assertTrue(hooks.hook(self.rt, self.req(), cancel=cancel)["stopped"])

    def test_what_is_missing_is_named_before_anything_starts(self) -> None:
        ran = mock.Mock()
        with mock.patch.object(self.rt.os.process, "run", ran):
            for given, code in (
                ({"script": self.root / "none.js"}, "invalid_request"),
                ({"script": self.root}, "invalid_request"),
                ({"seconds": 0}, "invalid_request"),
                ({"pid": 0, "name": "no-such-image.exe"}, "not_found"),
            ):
                with self.assertRaises(ViwoError) as err:
                    hooks.hook(self.rt, self.req(**given))
                self.assertEqual(err.exception.code, code, given)
            with mock.patch.object(self.rt.os.tools, "locate", return_value=None):
                with self.assertRaises(ViwoError) as err:
                    hooks.hook(self.rt, self.req())
            self.assertEqual((err.exception.code, err.exception.hint), ("unavailable", FRIDA.hint))
            off = runtime(self.root / "off")
            with self.assertRaises(ViwoError) as err:
                hooks.hook(off, self.req())
            self.assertEqual(err.exception.code, "refused")
        ran.assert_not_called()
        self.assertFalse((self.root / "ws").exists())  # nothing written either

    def test_a_real_child_is_relayed_live_and_stopped_after_its_time(self) -> None:
        """The real process runner on a stand-in `frida_tools.repl` in the pinned folder."""
        package = self.root / "third_party" / "python" / "frida_tools"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "repl.py").write_text(FAKE, encoding="utf-8")
        events = []
        with mock.patch.object(hooks, "GRACE", -0.5):  # the child outlives its time: stopped
            done = hooks.hook(self.rt, self.req(seconds=1.5), events.append)
        told = [e.message for e in events]
        self.assertIn("console.log('mine');", told)
        self.assertIn("late", told)  # its error stream too
        self.assertTrue(any(m.startswith("argv -q -t 1.5 -p 42 -l") for m in told), told)
        self.assertEqual(done["lines"], 3)
        self.assertTrue(told[-1].endswith(done["log"]))

    def test_every_entry_point_and_the_pin_agree(self) -> None:
        from viwo.api.app import App
        from viwo.api.handlers import POST
        from viwo.api.recording import ROUTES
        from viwo.cli import main
        from viwo.cli_arms import ARMS
        from viwo.core.workflows import UNEXPECTED

        self.assertIn("hook", ARMS["dynamic"][1])
        self.assertEqual(ROUTES["/api/runtime/hook"], ("hook", {}))
        self.assertIn("hook", UNEXPECTED)  # a running game: a replay expects no fixed answer
        seen = []
        ini = ["--quiet", "--ini", str(self.root / "test.ini")]
        argv = ["hook", "--pid", "7", "--script", str(self.script), "--seconds", "2"]
        with mock.patch("viwo.core.capture.runtime.run", lambda *a: seen.append(a[1:3]) or {}):
            with mock.patch("sys.stdout"):
                self.assertEqual(main([*ini, *argv, "--workspace", str(self.root / "w")]), 0)
        kind, req = seen[0]
        self.assertEqual((kind, req.pid, req.script, req.seconds), ("hook", 7, self.script, 2))
        app = App(runtime(self.root / "off"))
        app.set_workspace(self.root / "off" / "ws")
        body = {"pid": 7, "scriptPath": str(self.script)}
        for answer in (
            POST["/api/runtime/hook"](app, body),
            POST["/api/jobs"](app, {"kind": "hook", "params": body}),
        ):
            self.assertEqual((answer["success"], answer["code"]), (False, "refused"))
        self.assertEqual(POST["/api/runtime/hook"](app, {})["code"], "invalid_request")
        pin = thirdparty.manifest()["python"]["frida-tools"].split()
        self.assertTrue(all("==" in p for p in pin) and len(pin) == 2, pin)
        lock = thirdparty.lock_file("frida-tools").read_text(encoding="utf-8")
        for package in pin:  # installed only from the hash lock
            self.assertRegex(lock, rf"(?m)^{package} --hash=sha256:[0-9a-f]{{64}}")
        self.assertIn(FRIDA, self.rt.backends["frida-trace"].requires)


if __name__ == "__main__":
    unittest.main()
