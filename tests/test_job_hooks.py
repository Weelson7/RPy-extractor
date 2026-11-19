"""L3: `[hooks]` (doc 9.5): the user's commands before and after every job, in the CLI and the
API; told the job in environment variables; a failing, missing or slow hook is a warning and the
job goes on exactly as it would without it."""

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime, write_ini
from tests.test_cli import run
from viwo.api import app as app_module
from viwo.api.handlers import POST
from viwo.contracts import ViwoError
from viwo.contracts.types import ProcessResult
from viwo.core.hooks import Hooks
from viwo.core.jobs import JobRunner
from viwo.core.wiring import distros
from viwo.core.wiring.ini import load_ini

HOOK = """import json, os, sys, time
with open(sys.argv[1], "a", encoding="utf-8") as fh:
    keys = ("VIWO_HOOK", "VIWO_JOB_KIND", "VIWO_JOB_STATE", "VIWO_JOB_ERROR", "VIWO_WORKSPACE",
            "VIWO_GAME", "VIWO_JOB_ID")
    fh.write(json.dumps({k: os.environ.get(k) for k in keys}) + "\\n")
print("hello from", os.environ["VIWO_HOOK"])
time.sleep(float(sys.argv[3]) if len(sys.argv) > 3 else 0)
sys.exit(int(sys.argv[2]))
"""


class Setup(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.script = self.root / "hook.py"
        self.script.write_text(HOOK)
        self.log = self.root / "hooks.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def command(self, code: int = 0, sleep: float = 0) -> str:
        return f'"{sys.executable}" "{self.script}" "{self.log}" {code} {sleep}'

    def seen(self) -> list[dict]:
        text = self.log.read_text(encoding="utf-8") if self.log.is_file() else ""
        return [json.loads(line) for line in text.splitlines()]

    def hooks_ini(self, **keys) -> str:
        return "[hooks]\n" + "".join(f"{k} = {v}\n" for k, v in keys.items())


class IniTests(Setup):
    def test_keys_timeout_and_problems(self) -> None:
        body = self.hooks_ini(
            timeout="5",
            before_extract="echo %VIWO_JOB_KIND%",
            after_any="x",
            before_nothing="y",
            during_extract="z",
        )
        config = load_ini(write_ini(self.root, body))
        self.assertEqual(config.hooks["before_extract"], "echo %VIWO_JOB_KIND%")  # raw, as written
        self.assertEqual(
            (config.hook_timeout, sorted(config.hooks)), (5.0, ["after_any", "before_extract"])
        )
        self.assertEqual(sum("[hooks]" in p for p in config.problems), 2)
        bad = load_ini(write_ini(self.root, self.hooks_ini(timeout="soon")))
        self.assertEqual(bad.hook_timeout, 60.0)
        self.assertTrue(any("timeout" in p for p in bad.problems))
        good = self.root / "startup.ini"  # the strict check: a known section, no problem
        good.write_text(self.hooks_ini(after_cleanup="x", timeout="0"), encoding="utf-8")
        self.assertEqual(distros.check(good), [])


class RunnerTests(Setup):
    def runner(self, timeout: float = 30, **keys) -> JobRunner:
        rt = runtime(self.root, self.hooks_ini(timeout=timeout, **keys))
        return JobRunner(hooks=Hooks.of(rt))

    def test_order_environment_and_lines(self) -> None:
        runner = self.runner(
            before_any=self.command(),
            before_cleanup=self.command(),
            after_cleanup=self.command(),
            after_any=self.command(),
            before_extract=self.command(),
        )
        where = {"workspace": self.root / "ws", "game": self.root / "game"}
        job = runner.submit("cleanup", lambda j, s, c: {"ok": 1}, False, where)
        self.assertEqual(job.state, "succeeded")
        seen = self.seen()
        order = [e["VIWO_HOOK"] for e in seen]
        self.assertEqual(order, ["before_any", "before_cleanup", "after_cleanup", "after_any"])
        self.assertEqual([e["VIWO_JOB_STATE"] for e in seen], ["running"] * 2 + ["succeeded"] * 2)
        self.assertEqual(seen[0]["VIWO_WORKSPACE"], str(self.root / "ws"))
        self.assertEqual(
            (seen[0]["VIWO_GAME"], seen[0]["VIWO_JOB_ID"]), (str(self.root / "game"), job.job_id)
        )
        lines = [e.legacy_line() for e in job.events]
        self.assertIn("[HOOKS:BEFORE_ANY] hello from before_any", lines)

    def test_a_failed_job_is_told_and_unchanged(self) -> None:
        runner = self.runner(after_any=self.command())

        def boom(j, s, c):
            raise ViwoError("refused", "no")

        job = runner.submit("repack", boom, False)
        self.assertEqual((job.state, job.error["code"]), ("failed", "refused"))
        self.assertEqual(self.seen()[0]["VIWO_JOB_ERROR"], "refused")
        self.assertEqual(self.seen()[0]["VIWO_JOB_STATE"], "failed")

    def test_property_failing_missing_and_slow_hooks_never_change_the_job(self) -> None:
        rng = random.Random(9)
        bad = [self.command(3), "viwo-no-such-command-anywhere", self.command(0, 20)]
        for case in range(3):
            keys = {
                k: rng.choice(bad)
                for k in rng.sample(["before_any", "after_any", "before_mod", "after_mod"], 2)
            }
            runner = self.runner(timeout=1, **keys)
            job = runner.submit("mod", lambda j, s, c: {"value": case}, False)
            self.assertEqual((job.state, job.result), ("succeeded", {"value": case}), keys)
            warns = [e.message for e in job.events if e.level == "warn"]
            self.assertEqual(len(warns), 2, (keys, warns))
            self.assertTrue(all("the job goes on" in w for w in warns), warns)
        slow = self.runner(timeout=1, before_any=self.command(0, 20))
        job = slow.submit("mod", lambda j, s, c: 1, False)
        self.assertLess(job.finished - job.started, 15)  # killed at the timeout, said
        self.assertTrue(any("stopped after 1 s" in e.message for e in job.events))


class ClientTests(Setup):
    def test_cli_commands_fire_and_queries_do_not(self) -> None:
        ws = self.root / "ws"
        ws.mkdir()
        (ws / ".viwo-workspace").write_text("")
        ini = write_ini(self.root, self.hooks_ini(after_any=self.command()))
        code, _, err = run(["--ini", str(ini), "sanitize", str(ws)])
        self.assertEqual(code, 0, err)
        self.assertEqual(
            [(e["VIWO_JOB_KIND"], e["VIWO_WORKSPACE"]) for e in self.seen()], [("cleanup", str(ws))]
        )
        self.assertIn("[HOOKS:AFTER_ANY] hello from after_any", err)
        run(["--ini", str(ini), "info"])
        self.assertEqual(len(self.seen()), 1)  # not a job: no hook

    def test_api_jobs_fire(self) -> None:
        ws = self.root / "ws"
        ws.mkdir()
        (ws / ".viwo-workspace").write_text("")
        body = self.hooks_ini(before_cleanup=self.command(1))
        app = app_module.App(runtime(self.root, body), write_ini(self.root, body))
        app.set_workspace(ws)
        plan = POST["/api/sanitizer/plan"](app, {})
        self.assertTrue(plan["success"], plan)  # the hook failed: a warning only
        self.assertEqual(self.seen()[0]["VIWO_JOB_KIND"], "cleanup")
        self.assertTrue(any("exited with 1" in line for line in app.logs()))
        app.jobs.hooks = None
        app.reload()  # the ini's hooks again after a reload
        self.assertEqual(sorted(app.jobs.hooks.commands), ["before_cleanup"])


class DirectHookTests(unittest.TestCase):
    """core/hooks.py leaf paths with a fake runner: an unexpected error, a cancelled timeout and
    a command the shell cannot find are each a quiet warning; a run with no sink raises nothing."""

    def _hooks(self, result=None, raises=None) -> Hooks:
        def run(argv, cwd=None, timeout=None, cancel=None, env=None, on_line=None):
            if raises is not None:
                raise raises
            return result

        proc = SimpleNamespace(run=run, shell_command=lambda command: ["sh", "-c", command])
        return Hooks(commands={"before_any": "echo hi"}, timeout=1, cwd=None, process=proc)

    @staticmethod
    def _job() -> SimpleNamespace:
        return SimpleNamespace(kind="extract", job_id="j1", state="running", error=None, where={})

    def _fire(self, hooks: Hooks, cancel=None, with_sink: bool = True) -> list:
        events: list = []
        hooks.fire("before", self._job(), events.append if with_sink else None, cancel)
        return events

    def test_an_unexpected_error_in_a_hook_is_a_warning_not_a_raise(self) -> None:
        warns = [
            e for e in self._fire(self._hooks(raises=RuntimeError("boom"))) if e.level == "warn"
        ]
        self.assertTrue(warns and "hook not run" in warns[-1].message, warns)
        self.assertIn("RuntimeError", warns[-1].message)

    def test_a_cancelled_timeout_and_a_missing_command_are_named(self) -> None:
        cancel = SimpleNamespace(cancelled=True)
        events = self._fire(self._hooks(ProcessResult(-9, "", "", timed_out=True)), cancel)
        self.assertTrue(any("the job was cancelled" in e.message for e in events), events)
        for code in (9009, 127):  # the shell's own "command not found" codes (cmd, sh)
            events = self._fire(self._hooks(ProcessResult(code, "", "")))
            self.assertTrue(any(f"command not found ({code})" in e.message for e in events), code)

    def test_a_run_without_a_sink_raises_nothing(self) -> None:
        self.assertEqual(self._fire(self._hooks(ProcessResult(0, "", "")), with_sink=False), [])


if __name__ == "__main__":
    unittest.main()
