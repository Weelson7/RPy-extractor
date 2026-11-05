"""L3: workbooks (doc 19.1). Properties: every shipped workbook loads, is written for its tool's
current pin (a pin change fails here, so the steps get checked again) and opens a slot whose
backend is that tool; any broken file, of any kind, is skipped and named, never silently, and
never hides the others; a user workbook replaces the shipped one with its id; a workbook for
another version is marked stale with both versions; the CLI and the API answer what load()
answers."""

from __future__ import annotations

import copy
import json
import random
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime
from viwo.core import thirdparty
from viwo.core.workbooks import SHIPPED, load, user_dir

GOOD = {
    "id": "mine",
    "title": "Do a thing",
    "tool": "x64dbg",
    "written_for": "2026.05.27",
    "opens": "attach.debug",
    "summary": "How.",
    "steps": [{"title": "One", "text": "Press it.", "keys": ["F9"], "expect": "It ran."}],
}


def _breakages() -> list:
    """Each breaks exactly one rule of doc 19.1 (or the file itself)."""
    out = [lambda b, k=k: b.pop(k) for k in ("id", "title", "tool", "written_for", "summary")]
    out += [lambda b, k=k: b.update({k: "  "}) for k in ("title", "tool", "summary")]
    out += [
        lambda b: b.update(id="Bad Id"),
        lambda b: b.update(id=7),
        lambda b: b.update(opens="nowhere.slot"),
        lambda b: b.update(opens="unarchive.zip"),  # a slot, but no tool opens from it
        lambda b: b.update(opens=["attach.debug"]),
        lambda b: b.update(steps=[]),
        lambda b: b.update(steps="press F9"),
        lambda b: b["steps"].append({"title": "no text"}),
        lambda b: b["steps"].append({"title": "t", "text": "x", "keys": "F9"}),
        lambda b: b["steps"].append({"title": "t", "text": "x", "keys": [""]}),
        lambda b: b["steps"].append({"title": "t", "text": "x", "expect": 3}),
        lambda b: b["steps"].append("a step"),
    ]
    return out


class WorkbookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.rt = runtime(self.root, "[plugins]\ngeneric = on\n")
        self.mine = user_dir(self.rt)
        self.mine.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, name: str, body) -> Path:
        path = self.mine / name
        path.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
        return path

    def test_shipped_workbooks_match_the_pins_and_open_their_own_tool(self) -> None:
        books, problems = load(self.rt)
        self.assertEqual(problems, [])
        self.assertEqual(len(books), len(list(SHIPPED.glob("*.json"))))
        pins = thirdparty.manifest()["tools"]
        for b in books:
            self.assertEqual(b["source"], "viwo", b["id"])
            self.assertEqual((b["writtenFor"], b["stale"]), (pins[b["tool"]]["version"], False))
            if b["opens"]:  # optional (doc 19.1): no handoff opens every tool
                backend = self.rt.backends[self.rt.slots[b["opens"]].default_main]
                self.assertIn(b["tool"], {spec.dep_id for spec in backend.requires}, b["id"])
            self.assertTrue(all(s["title"] and s["text"] for s in b["steps"]), b["id"])

    def test_every_broken_file_is_named_and_hides_nothing_else(self) -> None:
        rng = random.Random(19)
        breakages = _breakages()
        shipped = {b["id"] for b in load(self.rt)[0]}
        for case in range(60):
            broken = copy.deepcopy(GOOD)
            rng.choice(breakages)(broken)
            bad = self._write(f"bad{case}.json", broken)
            if case % 7 == 0:
                bad.write_text(rng.choice(["{", "[]", '"text"', ""]), encoding="utf-8")
            self._write("ok.json", {**GOOD, "id": f"ok-{case}"})
            books, problems = load(self.rt)
            ids = {b["id"] for b in books}
            self.assertEqual(ids, shipped | {f"ok-{case}"}, case)  # the broken one, only it, gone
            self.assertEqual(len(problems), 1, (case, problems))
            self.assertIn(bad.name, problems[0])
            bad.unlink()

    def test_yours_replaces_the_shipped_one_and_versions_are_said(self) -> None:
        shipped = load(self.rt)[0][0]
        self._write("a.json", {**GOOD, "id": shipped["id"], "title": "My way"})
        self._write("b.json", {**GOOD, "id": "old", "written_for": "1999.01.01"})
        self._write("c.json", {**GOOD, "id": "c", "tool": "my-own-tool", "opens": ""})
        self._write("d.json", {**GOOD, "id": "c"})  # the same id twice in one folder
        books, problems = load(self.rt)
        by_id = {b["id"]: b for b in books}
        self.assertEqual(
            (by_id[shipped["id"]]["title"], by_id[shipped["id"]]["source"]), ("My way", "yours")
        )
        pinned = thirdparty.manifest()["tools"]["x64dbg"]["version"]
        self.assertEqual((by_id["old"]["stale"], by_id["old"]["pinned"]), (True, pinned))
        self.assertEqual((by_id["c"]["stale"], by_id["c"]["pinned"]), (False, ""))  # unpinned
        self.assertEqual(len(problems), 1)
        self.assertIn("d.json", problems[0])
        self.assertIn("used twice", problems[0])

    def test_cli_and_api_answer_what_load_answers(self) -> None:
        from tests.helpers import write_ini
        from tests.test_cli import run
        from viwo.api.app import App
        from viwo.api.handlers_system import SYSTEM_GET

        self._write("old.json", {**GOOD, "id": "old", "written_for": "1999.01.01"})
        self._write("bad.json", "{")
        books, problems = load(self.rt)
        got = SYSTEM_GET["/api/workbooks"](App(self.rt), {})
        self.assertEqual((got["workbooks"], got["problems"]), (books, problems))
        ini = str(write_ini(self.root, "[plugins]\ngeneric = on\n[server]\ntemp = tmp\n"))
        code, out, _ = run(["--ini", ini, "--json", "workbook"])
        self.assertEqual(code, 0)
        listed = json.loads(out)
        self.assertEqual([b["id"] for b in listed["data"]["workbooks"]], [b["id"] for b in books])
        self.assertTrue(any("bad.json" in w for w in listed["warnings"]))
        code, out, err = run(["--ini", ini, "workbook", "old"])
        self.assertEqual(code, 0)
        self.assertIn("1. One", out)
        self.assertIn("you should see: It ran.", out)
        self.assertIn("written for x64dbg 1999.01.01", err)  # stale steps are said
        code, _, err = run(["--ini", ini, "workbook", "nope"])
        self.assertEqual(code, 1)
        self.assertIn("not_found", err)


if __name__ == "__main__":
    unittest.main()
