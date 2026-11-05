"""L3: runbooks (doc 19.2). Properties: every shipped runbook loads with real job kinds, declared
values and existing workbooks; any broken file is skipped and named and hides nothing else; a
`{name}` is replaced wherever it sits in a parameter tree and an empty one is refused, named,
before anything runs; saving validates first and writes only the user's folder, a saved copy
replaces the shipped one until it is deleted; a shipped runbook runs end to end on a game
through the API handlers, and the CLI runs the same steps, stops at a step you do (no
terminal) and resumes with --from."""

from __future__ import annotations

import copy
import io
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import make_game, runtime, tree_hashes, write_ini
from viwo.api.handlers_jobs import KINDS
from viwo.contracts import ViwoError
from viwo.core import guides, runbooks

GOOD = {
    "id": "mine",
    "title": "Mine",
    "summary": "Does things.",
    "inputs": [{"name": "target", "label": "Target"}],
    "steps": [
        {"title": "Survey", "do": "survey", "with": {"folder": "{game}", "n": ["{target}", 3]}},
        {"title": "Look", "text": "Look at it.", "workbook": "x64dbg-patch-a-byte"},
    ],
}
INI = "[plugins]\ngeneric = on\n[server]\nworkspace = ws\nlogs = logs\ntemp = tmp\nmerged = m\n"


def _breakages() -> list:
    return [
        lambda b: b.pop("id"),
        lambda b: b.update(id="No/Good"),
        lambda b: b.update(summary=""),
        lambda b: b.update(inputs="target"),
        lambda b: b["inputs"].append({"name": "game"}),  # reserved
        lambda b: b["inputs"].append({"name": "Bad Name"}),
        lambda b: b["inputs"].append({"name": "x", "default": 5}),
        lambda b: b.update(steps=[]),
        lambda b: b["steps"].append({"title": "x", "do": "format-disk"}),
        lambda b: b["steps"].append({"title": "x", "do": "survey", "with": "folder"}),
        lambda b: b["steps"].append({"title": "x", "do": "survey", "with": {"f": "{nobody}"}}),
        lambda b: b["steps"].append({"title": "x", "text": "y", "workbook": "no-such-book"}),
        lambda b: b["steps"].append({"title": "x"}),
        lambda b: b["steps"].append({"text": "no title"}),
        lambda b: b["steps"].append({"title": "x", "do": ["survey"]}),  # wrong types: named,
        lambda b: b["steps"].append({"title": "x", "do": {"k": 1}}),  # never a crash that
        lambda b: b["steps"].append({"title": "x", "text": "y", "workbook": ["a"]}),  # hides all
        lambda b: b["inputs"].append(["target"]),
    ]


class RunbookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.rt = runtime(self.root, INI)
        self.mine = guides.user_dir(self.rt, runbooks.KIND)
        self.mine.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_shipped_runbooks_use_real_kinds_values_and_workbooks(self) -> None:
        books, problems = runbooks.load(self.rt, KINDS)
        self.assertEqual(problems, [])
        self.assertEqual(len(books), len(list((guides.DATA / runbooks.KIND).glob("*.json"))))
        for b in books:
            names = {*runbooks.RESERVED, *(i["name"] for i in b["inputs"])}
            for step in b["steps"]:
                if "do" in step:
                    self.assertIn(step["do"], KINDS, b["id"])
                    self.assertLessEqual(runbooks.names_in(step["with"]), names, b["id"])

    def test_every_broken_file_is_named_and_hides_nothing_else(self) -> None:
        rng, shipped = random.Random(192), {b["id"] for b in runbooks.load(self.rt, KINDS)[0]}
        for case in range(50):
            broken = copy.deepcopy(GOOD)
            rng.choice(_breakages())(broken)
            bad = self.mine / f"bad{case}.json"
            bad.write_text(json.dumps(broken), encoding="utf-8")
            (self.mine / "ok.json").write_text(json.dumps({**GOOD, "id": f"ok-{case}"}))
            books, problems = runbooks.load(self.rt, KINDS)
            self.assertEqual({b["id"] for b in books}, shipped | {f"ok-{case}"}, case)
            self.assertEqual(len(problems), 1, (case, problems))
            self.assertIn(bad.name, problems[0])
            bad.unlink()

    def test_values_replace_every_name_and_an_empty_one_is_refused(self) -> None:
        rng = random.Random(7)
        for _ in range(200):
            names = rng.sample(["game", "workspace", "a", "b_2"], rng.randint(1, 4))
            values = {n: f"V{n}" for n in names}

            def tree(depth: int):
                pick = rng.random()
                if depth > 2 or pick < 0.4:
                    return rng.choice([3, True, None, f"x{{{rng.choice(names)}}}y", "plain"])
                if pick < 0.7:
                    return [tree(depth + 1) for _ in range(rng.randint(0, 3))]
                return {f"k{i}": tree(depth + 1) for i in range(rng.randint(0, 3))}

            params = tree(0)
            oracle = json.dumps(params)  # names and values hold nothing JSON escapes
            for name, value in values.items():
                oracle = oracle.replace(f"{{{name}}}", value)
            self.assertEqual(runbooks.resolve(params, values), json.loads(oracle))
            used = runbooks.names_in(params)
            if used:
                gone = rng.choice(sorted(used))
                with self.assertRaises(ViwoError) as err:
                    runbooks.resolve(params, {**values, gone: ""})
                self.assertEqual(err.exception.code, "invalid_request")
                self.assertIn(gone, err.exception.message)

    def test_save_validates_writes_only_yours_and_delete_brings_the_shipped_back(self) -> None:
        shipped = runbooks.load(self.rt, KINDS)[0][0]
        before = tree_hashes(guides.DATA)
        for bad in ({**GOOD, "id": "../escape"}, {**GOOD, "steps": []}, "text"):
            with self.assertRaises(ViwoError) as err:
                runbooks.save(self.rt, KINDS, bad)
            self.assertEqual(err.exception.code, "invalid_request")
        self.assertEqual(list(self.mine.iterdir()), [])  # nothing written for a refusal
        tweaked = {**{k: shipped[k] for k in ("id", "summary", "inputs", "steps")}, "title": "T"}
        path = runbooks.save(self.rt, KINDS, tweaked)
        self.assertEqual(path.parent, self.mine)
        by_id = {b["id"]: b for b in runbooks.load(self.rt, KINDS)[0]}
        self.assertEqual(
            (by_id[shipped["id"]]["title"], by_id[shipped["id"]]["source"]), ("T", "yours")
        )
        guides.delete(self.rt, runbooks.KIND, shipped["id"])
        self.assertEqual(runbooks.load(self.rt, KINDS)[0][0], shipped)  # the shipped one is back
        for gone in (shipped["id"], "../tools"):
            with self.assertRaises(ViwoError):
                guides.delete(self.rt, runbooks.KIND, gone)
        self.assertEqual(tree_hashes(guides.DATA), before)  # shipped files never written
        hand = self.mine / "custom.json"  # a hand-named file: saved and deleted where it is
        hand.write_text(json.dumps({**GOOD, "id": "x"}), encoding="utf-8")
        self.assertEqual(runbooks.save(self.rt, KINDS, {**GOOD, "id": "x", "title": "New"}), hand)
        by_id = {b["id"]: b for b in runbooks.load(self.rt, KINDS)[0]}
        self.assertEqual(
            (by_id["x"]["title"], sorted(p.name for p in self.mine.iterdir())),
            ("New", ["custom.json"]),
        )
        guides.delete(self.rt, runbooks.KIND, "x")
        self.assertEqual(list(self.mine.iterdir()), [])

    def test_a_shipped_runbook_runs_through_the_api(self) -> None:
        from viwo.api.app import App
        from viwo.api.handlers_runbooks import RUNBOOKS_POST, run_step

        game = make_game(self.root)
        app = App(self.rt)
        book = next(b for b in runbooks.load(self.rt, KINDS)[0] if b["id"] == "extract-and-clean")
        for index in range(3):  # survey, extract, cleanup plan
            answer = run_step(app, book, index, {"game": str(game)})
            self.assertTrue(answer["success"] and answer["jobId"], (index, answer))
        self.assertTrue(any(app.workspace.iterdir()))  # extracted into the active workspace
        with self.assertRaises(ViwoError):
            run_step(app, book, 3, {})  # a step you do is not run by ViWo
        refused = RUNBOOKS_POST["/api/runbooks/step"](app, {"id": "find-and-patch-live", "step": 0})
        self.assertEqual(refused["code"], "invalid_request")  # {target} empty: nothing ran

    def test_the_cli_runs_stops_resumes_and_says_what_it_ignored(self) -> None:
        from tests.test_cli import run
        from viwo import cli_guides

        game, ini, ws = make_game(self.root), str(write_ini(self.root, INI)), self.root / "cli-ws"
        argv = ["--ini", ini, "runbook", "extract-and-clean", "--run", "--workspace", str(ws)]
        argv += ["--set", f"game={game}"]
        with mock.patch.object(cli_guides.sys, "stdin", io.StringIO()):  # no terminal
            code, out, err = run(["--json", *argv, "--set", "nobody=1"])
            self.assertEqual(code, 0, err)
            ran = json.loads(out)
            self.assertEqual((ran["data"]["stoppedAt"], len(ran["data"]["done"])), (4, 3))
            self.assertIn("games", ran["data"]["done"][0]["answer"])  # the survey's answer kept
            self.assertIn("it is the last step", ran["warnings"][-1])  # no useless --from 5
            self.assertTrue(any("--set nobody" in w for w in ran["warnings"]))
            code, out, _ = run(argv)  # text mode, an extract beside the now-used workspace
            self.assertIn("Runbook extract-and-clean: 3 action(s) run; stopped at step 4", out)
            self.assertEqual(run([*argv, "--from", "5"])[0], 2)  # outside the steps: refused
            extract = {"gamePath": "{game}", "onExisting": "new"}
            steps = [{"title": "e", "do": "extract", "with": extract}, {"title": "y", "text": "y"}]
            steps.append({"title": "c", "do": "cleanup", "with": {}})
            runbooks.save(
                self.rt, KINDS, {"id": "two", "title": "T", "summary": "S", "steps": steps}
            )
            code, out, _ = run(["--json", *argv[:3], "two", *argv[4:]])
        moved = json.loads(out)["warnings"][-1]  # the extract went beside cli-ws: resume there
        self.assertIn("--from 3 --workspace", moved)
        self.assertFalse(moved.endswith(f"--workspace {ws.resolve()}"), moved)
        with (
            mock.patch.object(cli_guides.sys, "stdin", mock.Mock(isatty=lambda: True)),
            mock.patch("builtins.input", return_value="") as asked,
        ):
            code, out, _ = run(["--json", *argv, "--from", "4"])  # Enter confirms a step you do
        asked.assert_called_once()
        self.assertIsNone(json.loads(out)["data"]["stoppedAt"])
        argv = ["--ini", ini, "runbook", "find-and-patch-live", "--run", "--workspace", str(ws)]
        code, _, err = run([*argv, "--set", f"game={game}"])
        self.assertEqual(code, 2)
        self.assertIn("needs a value for target", err)
        self.assertIn("--from 1", err)


if __name__ == "__main__":
    unittest.main()
