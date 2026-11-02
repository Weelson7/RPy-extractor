"""L3: sanitizer phase 1: plan, apply safe actions, undo; nothing lossy, nothing lost."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_png, runtime, tree_hashes
from viwo.api import app as app_module
from viwo.api.handlers import POST
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
            self.assertEqual(
                POST["/api/sanitizer/undo"](app, {"undoToken": done["undoToken"]})["restored"], 1
            )


if __name__ == "__main__":
    unittest.main()
