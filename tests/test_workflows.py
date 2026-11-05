"""L3: workflows (doc 19.3). Properties: an answer's expectation ignores what differs on every
run (ids, tokens, times, version stamps, the spelling of the game and workspace paths) and
catches any other change, naming it; paths become `{game}` and `{workspace}` only where a path
ends; a secret plugin option never reaches a saved file, the log or the recorder's view; a pid is
never recorded; a recording made through the real action routes saves a runbook that replays on
the same game without a stop (a cleanup apply sending its own replay's plan), and stops, naming
what changed, once the game changed; paused, failed, replayed or still-running actions are
handled as doc 19.3 says; every misuse of the recorder is said."""

from __future__ import annotations

import io
import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import make_game, runtime, write_ini
from viwo.api.handlers_jobs import KINDS
from viwo.core import runbooks, workflows

INI = "[plugins]\ngeneric = on\ngodot = on\n"
INI += "[server]\nworkspace = ws\nlogs = logs\ntemp = tmp\nmerged = m\n"
VOLATILE = ["fooId", "bar_id", "undoToken", "startTime", "durationSeconds", "made", "context"]
VOLATILE += ["elapsed", "runRecord", "time_stamp", "viwo", "logs"]


def _noise(rng: random.Random, tree):
    """The tree with volatile keys (by their name's pattern) added at random places."""
    if isinstance(tree, dict):
        out = {k: _noise(rng, v) for k, v in tree.items()}
        out.update({key: rng.random() for key in rng.sample(VOLATILE, 3)})
        return out
    return [_noise(rng, v) for v in tree] if isinstance(tree, list) else tree


def _rec() -> SimpleNamespace:
    return SimpleNamespace(inputs=[], answers=[])


class ExpectationTests(unittest.TestCase):
    def test_noise_and_path_spelling_are_ignored_any_other_change_is_named(self) -> None:
        rng = random.Random(193)
        game, ws = str(Path("C:/Games/Foo")), str(Path("C:/Games/Foo-ws"))
        values = {"game": game, "workspace": ws}
        for _ in range(150):
            answer = {
                "copied": rng.randint(0, 9),
                "runtime": "unity",  # not a time: kept
                "result": {"files": rng.randint(0, 9), "where": f"{ws}/x", "plugin": "generic"},
                "plugins": [{"id": "generic", "n": rng.randint(0, 3)} for _ in range(2)],
            }
            expect = workflows.expectation(answer, values)
            noisy = _noise(rng, answer)
            noisy["result"]["where"] = f"{Path(ws).as_posix()}/x"  # another spelling, same place
            self.assertEqual(workflows.compare(expect, noisy, values), [])
            for key, change in (("files", 1), ("plugin", "unity")):
                changed = json.loads(json.dumps(answer))
                changed["result"][key] = (
                    changed["result"][key] + change if key == "files" else change
                )
                differs = workflows.compare(expect, changed, values)
                self.assertTrue(any(d.startswith(f"result.{key}:") for d in differs), differs)
            for changed in ({**answer, "runtime": "godot"}, {**answer, "plugins": [{"id": "x"}]}):
                self.assertTrue(workflows.compare(expect, changed, values))  # kept, compared
        pairs = workflows.path_pairs(values)
        text = f"{ws}/a {game}/b {game}bar/c {game}"
        self.assertEqual(
            workflows.portable(text, pairs), f"{{workspace}}/a {{game}}/b {game}bar/c {{game}}"
        )

    def test_secrets_pids_and_earlier_answers_never_record_this_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, rec = runtime(Path(tmp), INI), _rec()
            options = {"godot": {"encryption_key": "S3CR3T"}, "Unreal": {"aes_key": "K3Y-2"}}
            params = {"gamePath": "C:/G", "pluginOptions": options}
            step = workflows.record_step(
                rt, "extract", params, {"success": True}, {"game": "C:/G"}, rec
            )
            self.assertNotIn("S3CR3T", json.dumps(step))
            self.assertNotIn("K3Y-2", json.dumps(step))  # an owner this runtime does not know
            self.assertEqual([i["secret"] for i in rec.inputs], [True, True])
            self.assertEqual(
                (step["with"]["gamePath"], step["with"]["onExisting"]), ("{game}", "new")
            )
            self.assertEqual(options["godot"]["encryption_key"], "S3CR3T")  # the caller's untouched
            book = {"id": "s", "title": "S", "summary": "S", "inputs": rec.inputs, "steps": [step]}
            self.assertNotIn("S3CR3T", runbooks.save(rt, KINDS, book).read_text(encoding="utf-8"))
            dump = workflows.record_step(rt, "dump", {"pid": 4242}, {"success": True}, {}, rec)
            self.assertEqual((dump["with"], "expect" in dump), ({"pid": "{pid}"}, False))
            named = workflows.record_step(rt, "dump", {"pid": 7, "name": "G.exe"}, {}, {}, rec)
            self.assertEqual(named["with"], {"name": "G.exe"})
            rec.answers = [{"planId": "plan-123456", "count": 3}, None]
            applied = workflows.record_step(
                rt, "cleanup", {"op": "apply", "planId": "plan-123456"}, {}, {}, rec
            )
            self.assertEqual(applied["with"]["planId"], "{step1_planid}")
            self.assertEqual(
                workflows.carried(0, rec.answers[0]),
                {"step1_planid": "plan-123456", "step1_count": "3"},
            )


class RecordingTests(unittest.TestCase):
    def setUp(self) -> None:
        from viwo.api.app import App
        from viwo.api.handlers import GET, POST

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.rt = runtime(self.root, INI)
        self.app, self.get, self.post = App(self.rt), GET, POST
        self.game = make_game(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def rec(self, action: str, **extra) -> dict:
        return self.post["/api/recording"](self.app, {"action": action, **extra})

    def test_misuse_is_said(self) -> None:
        from viwo.api.recording import wrap

        for action, extra, code in (
            ("fly", {}, "invalid_request"),
            ("pause", {}, "invalid_request"),  # nothing runs
            ("start", {"title": " ", "game": "G"}, "invalid_request"),
            ("start", {"title": "No game"}, "invalid_request"),  # nothing could become {game}
        ):
            self.assertEqual(self.rec(action, **extra)["code"], code, (action, extra))
        self.assertTrue(self.rec("start", title="One", game=str(self.game))["success"])
        self.assertEqual(self.rec("start", title="Two", game="G")["code"], "refused")
        self.assertEqual(self.rec("note", title="x")["code"], "invalid_request")  # no text
        self.assertEqual(self.rec("stop")["code"], "invalid_request")  # nothing recorded
        wrap(self.post)  # wrapping twice records once
        self.post["/api/survey"](self.app, {"folder": str(self.game)})
        self.app.recording.running = 1  # an action still answering: its step would be lost
        self.assertEqual(self.rec("stop")["code"], "busy")
        self.app.recording.running = 0
        self.assertEqual(len(self.get["/api/recording"](self.app, {})["recording"]["steps"]), 1)
        self.post["/api/survey"](self.app, {"folder": str(self.root / "build")})  # another game
        self.assertIn(
            "names another game",
            self.get["/api/recording"](self.app, {})["recording"]["warnings"][0],
        )
        self.assertTrue(self.rec("discard")["success"])
        self.assertIsNone(self.get["/api/recording"](self.app, {})["recording"])

    def test_record_replay_the_same_game_then_a_changed_one(self) -> None:
        from viwo.api.handlers_runbooks import run_step

        game, secret = str(self.game), "AB" * 32
        self.rec("start", title="Pull it", game=game)
        self.assertTrue(self.post["/api/survey"](self.app, {"folder": game})["success"])
        self.assertFalse(self.post["/api/survey"](self.app, {"folder": game + "-gone"})["success"])
        self.rec("pause")
        self.post["/api/survey"](self.app, {"folder": game})  # paused: not recorded
        self.rec("continue")
        body = {"gamePath": game, "pluginOptions": {"godot": {"encryption_key": secret}}}
        self.assertTrue(self.post["/api/extract"](self.app, body)["success"])
        plan = self.post["/api/sanitizer/plan"](self.app, {})
        self.assertTrue(
            self.post["/api/sanitizer/apply"](self.app, {"planId": plan["planId"]})["success"]
        )
        self.rec("note", title="Look", text="Open WORKSPACE.")
        book_so_far = self.get["/api/recording"](self.app, {})["recording"]
        self.assertEqual(
            [s["do"] for s in book_so_far["steps"]], ["survey", "extract", "cleanup", "cleanup", ""]
        )
        saved = self.rec("stop")
        text = Path(saved["path"]).read_text(encoding="utf-8")
        for leaked in (json.dumps(game)[1:-1], secret, plan["planId"]):
            self.assertNotIn(leaked, text)  # portable, no secret, no recorded plan id
        self.assertFalse(any(secret in line for line in self.app.logs()))
        book = next(b for b in runbooks.load(self.rt, KINDS)[0] if b["id"] == "pull-it")
        carry = {"game": game, "secret_1": secret}
        for index in range(4):  # the same game: every answer as recorded, the apply its own plan
            answer = run_step(self.app, book, index, carry)
            self.assertEqual((answer["success"], answer["differs"]), (True, []), index)
            carry.update(workflows.carried(index, answer))
        self.rec("start", title="Replays are not recorded", game=game)
        run_step(self.app, book, 0, {"game": game})
        self.assertEqual(self.get["/api/recording"](self.app, {})["recording"]["steps"], [])
        self.rec("discard")
        (self.game / "data" / "new.png").write_bytes(b"png-2")  # the game changed
        for index in (0, 1):
            self.assertTrue(run_step(self.app, book, index, carry)["differs"], index)

    def test_the_cli_stops_where_a_replay_differs(self) -> None:
        from tests.test_cli import run
        from viwo import cli_guides

        self.rec("start", title="Survey it", game=str(self.game))
        self.post["/api/survey"](self.app, {"folder": str(self.game)})
        self.post["/api/survey"](self.app, {"folder": str(self.game)})
        self.rec("stop")
        (self.game / "more.txt").write_text("more")
        ini = str(write_ini(self.root, INI))
        argv = ["--ini", ini, "--json", "runbook", "survey-it", "--run"]
        argv += ["--workspace", str(self.root / "w"), "--set", f"game={self.game}"]
        with mock.patch.object(cli_guides.sys, "stdin", io.StringIO()):
            code, out, _ = run(argv)
        ran = json.loads(out)
        self.assertEqual((code, ran["data"]["stoppedAt"]), (0, 1))
        self.assertIn("differs from the recording", ran["warnings"][-1])
        self.assertIn("--from 2", ran["warnings"][-1])
        self.assertTrue(ran["data"]["done"][0]["differs"])


if __name__ == "__main__":
    unittest.main()
