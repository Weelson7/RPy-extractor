"""L3: sanitizer phase 1: plan, apply safe actions, undo; nothing lossy, nothing lost."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_png, runtime, tree_hashes
from viwo.api import app as app_module
from viwo.api.handlers import POST
from viwo.contracts import CancelToken, ViwoError
from viwo.core import sanitizer


def make_workspace(root: Path) -> Path:
    ws = root / "ws"
    for group in ("png", "jpg", "db", "import", "txt"):
        (ws / group).mkdir(parents=True)
    (ws / ".viwo-workspace").write_text("")
    png = make_png(root / "real.png").read_bytes()
    (ws / "png" / "ok.png").write_bytes(png)
    (ws / "png" / "copy.png").write_bytes(png)  # duplicate of ok.png
    (ws / "png" / "cut.png").write_bytes(png[:-20])  # truncated
    (ws / "jpg" / "photo.jpg").write_bytes(png)  # really a PNG (and a duplicate)
    (ws / "jpg" / "other.jpg").write_bytes(make_png(root / "b.png", 4, 4).read_bytes())
    (ws / "db" / "Thumbs.db").write_bytes(b"x" * 30)
    (ws / "import" / "icon.png.import").write_text("[remap]")
    (ws / "txt" / "empty.txt").write_bytes(b"")
    return ws


class SanitizerSafetyTests(unittest.TestCase):
    """A plan acts only on the files it saw: a file changed since the scan refuses the plan, a
    bad id or a missing plan is named, a finding that cannot be carried out is listed (the rest
    go on), and an undo that cannot bring a file back keeps it in the journal for later."""

    def test_stale_plans_bad_ids_and_partial_undo(self) -> None:
        from viwo.core.sanitizer_rules import collect_rules

        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp))
            self.assertEqual(sanitizer.recipes(collect_rules())[0]["rules"] != [], True)
            for bad in ("../../etc", "2026", ""):
                with self.assertRaises(ViwoError) as err:
                    sanitizer.apply(ws, bad)
                self.assertEqual(err.exception.code, "invalid_request")
            with self.assertRaises(ViwoError) as err:
                sanitizer.apply(ws, "20260101-000000-abcdef")
            self.assertEqual(err.exception.code, "not_found")
            with self.assertRaises(ViwoError):
                sanitizer.undo(ws, "20260101-000000-abcdef")
            plan = sanitizer.plan(ws)
            sized = next(f for f in plan["findings"] if "size" in f)
            target = ws / sized["path"]
            original = target.read_bytes()
            target.write_bytes(original + b"changed since the scan")
            with self.assertRaises(ViwoError) as err:
                sanitizer.apply(ws, plan["planId"])
            self.assertIn("plan is stale", err.exception.message)
            target.write_bytes(original)
            with self.assertRaises(ViwoError):
                sanitizer.apply(ws, plan["planId"], accept="nonsense")
            gone = next(
                f for f in plan["findings"] if f["action"] in ("trash", "rename") and f is not sized
            )
            (ws / gone["path"]).unlink()  # removed by hand between plan and apply
            done = sanitizer.apply(ws, plan["planId"])
            self.assertTrue(
                any(gone["path"] in f for f in done["failed"])
            )  # named, the rest went on
            moved = done["moved"][0]
            (ws / moved["to"]).unlink()  # one moved file is lost before the undo
            undone = sanitizer.undo(ws, done["undoToken"])
            self.assertEqual(undone["notRestored"], [moved["to"]])
            self.assertEqual(undone["restored"], len(done["moved"]) - 1)
            again = sanitizer.undo(ws, done["undoToken"])  # the journal kept the one left
            self.assertEqual(again["notRestored"], [moved["to"]])


class SanitizerTests(unittest.TestCase):
    def test_plan_apply_undo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp))
            before = tree_hashes(ws, skip_reserved=True)
            plan = sanitizer.plan(ws)
            got = {(f["rule"], f["path"], f["action"]) for f in plan["findings"]}
            self.assertLessEqual(
                {
                    ("core.zero_byte", "txt/empty.txt", "trash"),
                    ("core.junk", "db/Thumbs.db", "trash"),
                    ("core.junk", "import/icon.png.import", "trash"),
                    ("core.health", "png/cut.png", "none"),
                    ("core.extension", "jpg/other.jpg", "rename"),
                },
                got,
            )
            health = next(f for f in plan["findings"] if f["rule"] == "core.health")
            self.assertIn("truncated", health["message"])
            dupes = [f["path"] for f in plan["findings"] if f["rule"] == "core.duplicate"]
            self.assertEqual(sorted(dupes), ["jpg/photo.jpg", "png/ok.png"])  # copy.png kept
            self.assertNotIn(("core.extension", "jpg/photo.jpg", "rename"), got)  # trashed instead
            done = sanitizer.apply(ws, plan["planId"])
            self.assertEqual(done["failed"], [])
            self.assertTrue((ws / "jpg" / "other.png").is_file())
            self.assertTrue((ws / "png" / "cut.png").is_file())  # health is report-only
            self.assertFalse((ws / "txt" / "empty.txt").exists())
            self.assertTrue(
                (ws / ".trash" / "items" / "txt" / "empty.txt").is_file()
            )  # SORT layout
            self.assertIn({"from": "jpg/other.jpg", "to": "jpg/other.png"}, done["moved"])
            sanitizer.undo(ws, done["undoToken"])
            self.assertEqual(tree_hashes(ws, skip_reserved=True), before)

    def test_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = make_workspace(root)
            app = app_module.App(runtime(root))
            app.set_workspace(ws)
            plan = POST["/api/sanitizer/plan"](app, {})
            self.assertTrue(plan["success"] and plan["findings"], plan)
            done = POST["/api/sanitizer/apply"](app, {"planId": plan["planId"], "accept": [0]})
            self.assertEqual(done["applied"], 1)
            odd = POST["/api/sanitizer/apply"](app, {"planId": plan["planId"], "accept": [999, -1]})
            self.assertEqual(odd["applied"], 0)
            self.assertEqual(
                POST["/api/sanitizer/apply"](app, {"planId": plan["planId"], "accept": ["x"]})[
                    "code"
                ],
                "invalid_request",
            )
            undone = POST["/api/sanitizer/undo"](app, {"undoToken": done["undoToken"]})
            self.assertEqual(undone["restored"], 1)
            kinds = [app.jobs.get(r["jobId"]).kind for r in (plan, done, undone)]
            self.assertEqual(kinds, ["cleanup"] * 3)  # visible in 04 JOBS and the chips
            lines = [e.message for e in app.jobs.get(plan["jobId"]).events]
            self.assertTrue(any(m.startswith("Scanning files: ") for m in lines), lines)
            self.assertTrue(any(m.startswith("Hashing files: ") for m in lines), lines)
            self.assertIn(
                "Applying actions: 1 / 1", [e.message for e in app.jobs.get(done["jobId"]).events]
            )
            self.assertIn(
                "Undoing actions: 1 / 1", [e.message for e in app.jobs.get(undone["jobId"]).events]
            )

    def test_plan_request_fields_and_plugin_rules(self) -> None:
        """Doc 5.3: recipeId, path, offset, limit on the wire; doc 5.2: a plugin rule runs."""
        from viwo.core.sanitizer_rules import SanitizerRule

        class Flag(SanitizerRule):
            rule_id, owner, category, cost = "generic.flag", "generic", "junk", 1

            def inspect(self, path, ctx):
                return [ctx.finding(self.rule_id, path, "flagged by a plugin rule", "none")]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = make_workspace(root)
            app = app_module.App(runtime(root))
            app.set_workspace(ws)
            app.rt.plugins["generic"].sanitizer_rules = lambda: [Flag()]
            page = POST["/api/sanitizer/plan"](app, {"limit": 1, "offset": 1})
            self.assertEqual((len(page["findings"]), page["findings"][0]["index"]), (1, 1))
            self.assertGreater(page["total"], 1)
            whole = POST["/api/sanitizer/plan"](app, {"path": "png"})
            self.assertTrue(
                whole["findings"] and all(f["path"].startswith("png/") for f in whole["findings"])
            )
            self.assertIn("generic.flag", {f["rule"] for f in whole["findings"]})
            self.assertFalse(POST["/api/sanitizer/plan"](app, {"recipeId": "nope"})["success"])
            self.assertFalse(POST["/api/sanitizer/plan"](app, {"path": "../.."})["success"])

    def test_a_cancel_anywhere_in_apply_stays_undoable(self) -> None:
        class After(CancelToken):  # cancelled once `k` actions have run
            def __init__(self, k: int) -> None:
                super().__init__()
                self.left = k

            @property
            def cancelled(self) -> bool:
                self.left -= 1
                return self.left < 0

        for k in range(6):
            with tempfile.TemporaryDirectory() as tmp:
                ws = make_workspace(Path(tmp))
                before = tree_hashes(ws, skip_reserved=True)
                plan = sanitizer.plan(ws)
                try:
                    done = sanitizer.apply(ws, plan["planId"], cancel=After(k))
                except ViwoError as err:
                    self.assertEqual(err.code, "cancelled")
                    done = {"undoToken": plan["planId"]}
                undone = sanitizer.undo(ws, done["undoToken"])
                self.assertEqual(undone["notRestored"], [])
                self.assertEqual(tree_hashes(ws, skip_reserved=True), before, f"cancel after {k}")

    def test_cancel_stops_the_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp))
            cancel = CancelToken()
            cancel.cancel()
            with self.assertRaises(ViwoError) as err:
                sanitizer.plan(ws, None, cancel)
            self.assertEqual(err.exception.code, "cancelled")
            self.assertFalse((ws / sanitizer.ROOT).exists())


if __name__ == "__main__":
    unittest.main()
