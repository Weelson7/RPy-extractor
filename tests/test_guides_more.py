"""L3: the guides' remaining edges (doc 19), each as a property. The CLI's text forms name every
workbook and runbook, mark the user's own, and list every step in order; every misuse of
`viwo runbook` is refused and named; at a terminal a secret input is asked without echo and a
differing answer asks before going on; the runbook routes save, delete and refuse what they
must; expectations name a change anywhere in a wide answer and a replayed flag reads "false" as
false; an unreadable file of the user's never hides an id from the free-id search."""

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
from viwo.core import guides, runbooks, workbooks, workflows

INI = "[plugins]\ngeneric = on\n[server]\nworkspace = ws\nlogs = logs\ntemp = tmp\nmerged = m\n"
MINE = {
    "id": "mine",
    "title": "Mine",
    "summary": "Mine.",
    "steps": [{"title": "Look", "text": "x"}],
}


class _Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.rt = runtime(self.root, INI)
        self.ini = str(write_ini(self.root, INI))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def cli(self, *argv: str, stdin=None):
        from tests.test_cli import run
        from viwo import cli_guides

        with mock.patch.object(cli_guides.sys, "stdin", stdin or io.StringIO()):
            return run(["--ini", self.ini, *argv])


class TextFormTests(_Fixture):
    def test_the_lists_name_everything_and_mark_yours(self) -> None:
        runbooks.save(self.rt, KINDS, MINE)
        for command, books in (
            ("workbook", workbooks.load(self.rt)[0]),
            ("runbook", runbooks.load(self.rt, KINDS)[0]),
        ):
            code, out, _ = self.cli(command)
            self.assertEqual(code, 0)
            for b in books:
                row = next(line for line in out.splitlines() if line.startswith(b["id"]))
                self.assertIn(b["title"], row)
                self.assertEqual(row.endswith("(yours)"), b["source"] == "yours", row)

    def test_one_runbook_shows_its_inputs_and_every_step_in_order(self) -> None:
        for book in runbooks.load(self.rt, KINDS)[0]:
            code, out, _ = self.cli("runbook", book["id"])
            self.assertEqual(code, 0)
            at = [out.index(f"{n}. {s['title']}") for n, s in enumerate(book["steps"], 1)]
            self.assertEqual(at, sorted(at), book["id"])
            for i in book["inputs"]:
                self.assertIn(f"input {i['name']}: {i['label']}", out)

    def test_every_misuse_is_refused_and_named(self) -> None:
        ws = str(self.root / "w")
        for argv, code, said in (
            (("runbook", "nope"), 1, "no runbook 'nope'"),
            (("runbook", "extract-and-clean", "--run"), 2, "give --workspace"),
            (
                ("runbook", "extract-and-clean", "--run", "--workspace", ws, "--from", "0"),
                2,
                "--from 0",
            ),
            (
                ("runbook", "extract-and-clean", "--run", "--workspace", ws, "--set", "game"),
                2,
                "NAME=VALUE",
            ),
        ):
            got, _, err = self.cli(*argv)
            self.assertEqual(got, code, argv)
            self.assertIn(said, err, argv)


class TerminalTests(_Fixture):
    def test_a_secret_is_asked_and_a_differing_answer_asks_before_going_on(self) -> None:
        from viwo import cli_guides

        tty = SimpleNamespace(isatty=lambda: True)
        book = {"id": "s", "inputs": [{"name": "secret_1", "label": "key", "secret": True}]}
        with (
            mock.patch.object(cli_guides.sys, "stdin", tty),
            mock.patch("getpass.getpass", return_value="K") as ask,
        ):
            values, said = cli_guides._values(book, [])
        self.assertEqual((values, said), ({"secret_1": "K"}, []))
        ask.assert_called_once()
        args = SimpleNamespace(quiet=True)
        for reply, going_on in (("y", True), ("yes", True), ("", False), ("n", False)):
            with (
                mock.patch.object(cli_guides.sys, "stdin", tty),
                mock.patch("builtins.input", return_value=reply),
            ):
                self.assertEqual(cli_guides._go_on(args, ["a: 1 -> 2"]), going_on, reply)
        step = {"text": "Do it.", "workbook": "x64dbg-patch-a-byte"}
        with (
            mock.patch.object(cli_guides.sys, "stdin", io.StringIO()),  # no terminal: not asked
            mock.patch.object(cli_guides.sys, "stderr", new_callable=io.StringIO) as err,
        ):
            self.assertFalse(cli_guides._done_by_you(SimpleNamespace(quiet=False), step))
        self.assertIn("viwo workbook x64dbg-patch-a-byte", err.getvalue())


class RouteTests(_Fixture):
    def test_the_routes_save_delete_and_refuse(self) -> None:
        from viwo.api.app import App
        from viwo.api.handlers_runbooks import RUNBOOKS_POST

        app = App(self.rt)
        saved = RUNBOOKS_POST["/api/runbooks/save"](app, {"runbook": MINE})
        self.assertTrue(saved["success"] and Path(saved["path"]).is_file())
        self.assertEqual(
            RUNBOOKS_POST["/api/runbooks/save"](app, {"runbook": "x"})["code"], "invalid_request"
        )
        for body, code in (
            ({"id": "mine", "step": "two"}, "invalid_request"),
            ({"id": "nope", "step": 0}, "not_found"),
            ({"id": "mine", "step": 0}, "invalid_request"),  # a step you do is not run
        ):
            self.assertEqual(RUNBOOKS_POST["/api/runbooks/step"](app, body)["code"], code, body)
        self.assertTrue(RUNBOOKS_POST["/api/runbooks/delete"](app, {"id": "mine"})["success"])
        self.assertEqual(
            RUNBOOKS_POST["/api/runbooks/delete"](app, {"id": "mine"})["code"], "not_found"
        )


class ValueTests(_Fixture):
    def test_a_change_anywhere_in_a_wide_answer_is_named_and_flags_read_as_flags(self) -> None:
        rng = random.Random(9)
        for _ in range(40):
            answer = {f"k{i:02}": rng.randint(0, 9) for i in range(rng.randint(61, 90))}
            answer["rows"] = [{"n": 1}, {"n": 2}]
            expect = workflows.expectation(answer, {})
            self.assertEqual(len(expect["facts"]), workflows.MAX_FACTS)
            key = rng.choice(sorted(answer))
            changed = {**answer, key: "changed"}
            self.assertTrue(workflows.compare(expect, changed, {}), key)  # even past the facts
        for value, flag in (("true", True), ("False", False), ("TRUE", True)):
            self.assertIs(runbooks.resolve({"plan": "{plan}"}, {"plan": value})["plan"], flag)
        self.assertEqual(runbooks.resolve(["{a}", 1], {"a": "x"}), ["x", 1])
        for bad in ({"name": "k", "secret": "yes"}, {"name": "k", "secret": True, "default": "d"}):
            book = {**MINE, "inputs": [bad]}
            self.assertIn("secret", runbooks.parse(book, KINDS, set()))
        step = {"title": "t", "do": "survey", "with": {}, "expect": {"digest": "short"}}
        self.assertIn("expect", runbooks.parse({**MINE, "steps": [step]}, KINDS, set()))

    def test_an_unreadable_file_never_hides_an_id_and_a_pid_input_is_added_once(self) -> None:
        folder = guides.user_dir(self.rt, runbooks.KIND)
        folder.mkdir(parents=True)
        (folder / "broken.json").write_text("{", encoding="utf-8")
        (folder / "list.json").write_text("[1]", encoding="utf-8")
        (folder / "held.json").write_text(json.dumps({"id": "held", "steps": 3}), encoding="utf-8")
        self.assertEqual(guides.file_ids(self.rt, runbooks.KIND), {"held"})  # usable or not
        rec = SimpleNamespace(inputs=[], answers=[])
        for _ in range(3):
            step = workflows.record_step(self.rt, "trace", {"pid": 7}, {}, {}, rec)
            self.assertEqual(step["with"], {"pid": "{pid}"})
        self.assertEqual([i["name"] for i in rec.inputs], ["pid"])  # asked once, not per step
        game = make_game(self.root)
        inner = str(game / "a")  # its separator kept: the OS's own
        params = {"gamePath": str(game), "onExisting": "replace", "list": [inner]}
        step = workflows.record_step(self.rt, "extract", params, {}, {"game": str(game)}, rec)
        want = ["{game}" + inner[len(str(game)) :]]
        self.assertEqual(
            step["with"], {"gamePath": "{game}", "onExisting": "replace", "list": want}
        )


if __name__ == "__main__":
    unittest.main()
