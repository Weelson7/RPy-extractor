"""L3: curation (group trash, item sorting, merger trash) and the workspace lock."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import write_ini
from viwo.api.app import App
from viwo.contracts import ViwoError
from viwo.core.curation import sorting, trash
from viwo.core.wiring.boot import boot
from viwo.core.workspace import workspace_lock
from viwo.os.windows import WindowsFs


def make_workspace(root: Path) -> Path:
    ws = root / "ws"
    for rel in (
        "png/a.png",
        "png/b.png",
        "pngx/c.pngx",
        "txt/notes.txt",
        ".extraction_metadata/r.json",
    ):
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_text(rel)
    return ws


class GroupTrashTests(unittest.TestCase):
    def test_trash_restore_delete_exact_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp))
            self.assertEqual(trash.kept(ws), {"png": 2, "pngx": 1, "txt": 1})
            self.assertTrue(trash.trash_group(ws, "png")[0])
            self.assertTrue(trash.trash_group(ws, "pngx")[0])
            self.assertEqual(trash.trashed(ws), {"png": 2, "pngx": 1})
            ok, message = trash.restore_group(ws, "png")
            self.assertTrue(ok)
            self.assertEqual(sorted(p.name for p in (ws / "png").iterdir()), ["a.png", "b.png"])
            self.assertTrue((ws / ".trash/groups/pngx").is_dir())  # not taken by the prefix
            ok, message = trash.delete_group(ws, "pngx")
            self.assertIn("(1 files)", message)  # counted before deletion (v1 F9)
            self.assertFalse(trash.trash_group(ws, ".extraction_metadata")[0])

    def test_migrate_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp))
            for rel in ("png/old.png", "png_1/older.png", "media-merger/clip.mp4"):
                (ws / ".trash" / rel).parent.mkdir(parents=True, exist_ok=True)
                (ws / ".trash" / rel).write_text("x")
            self.assertEqual(trash.migrate(ws), 3)
            self.assertTrue((ws / ".trash/groups/png_1/older.png").exists())
            self.assertTrue((ws / ".trash/merger/clip.mp4").exists())
            self.assertEqual(trash.migrate(ws), 0)
            count, _ = trash.clear(ws)
            self.assertEqual(count, 3)
            self.assertEqual(trash.trashed(ws), {})


class SortingTests(unittest.TestCase):
    def test_item_trash_rename_and_undo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp))
            history: list[dict] = []
            page = sorting.list_window(ws, 0, 10)
            self.assertEqual(page["totalCount"], 4)  # reserved folders hidden
            encoded = sorting.encode(ws, ws / "png" / "a.png")
            sorting.trash_item(ws, encoded, history)
            self.assertTrue((ws / ".trash/items/png/a.png").exists())
            self.assertEqual(sorting.undo(ws, history)["undone"], "trash")
            self.assertTrue((ws / "png/a.png").exists())
            with self.assertRaises(ViwoError):
                sorting.rename(ws, encoded, "CON.png", history, WindowsFs())
            renamed = sorting.rename(ws, encoded, "hero.png", history, WindowsFs())
            self.assertEqual(renamed["name"], "hero.png")
            self.assertEqual(sorting.undo(ws, history)["undone"], "rename")
            self.assertTrue((ws / "png/a.png").exists())

    def test_paths_stay_inside_the_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp))
            for bad in ("../outside.txt", ".extraction_metadata/r.json", ""):
                with self.subTest(bad=bad), self.assertRaises(ViwoError):
                    sorting.resolve(ws, bad)
            self.assertEqual(sorting.preview(ws, "txt/notes.txt")["content"], "txt/notes.txt")

    def test_save_remaining(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp))
            dest = Path(tmp) / "out"
            dest.mkdir()
            result = sorting.save_remaining(ws, ["png/a.png", "png/missing.png"], dest)
            self.assertEqual((result["moved"], result["skipped"]), (1, 1))
            self.assertTrue((dest / "png/a.png").exists())


class LockTests(unittest.TestCase):
    def test_curation_is_busy_during_a_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp))
            app = App(boot(write_ini(Path(tmp), "[server]\nlogs = logs\n")))
            with workspace_lock(ws):
                result = app.locked(lambda: {"success": True}, ws)
            self.assertEqual(result["code"], "busy")
            self.assertTrue(app.locked(lambda: {"success": True}, ws)["success"])


if __name__ == "__main__":
    unittest.main()


class StatusCountsTests(unittest.TestCase):
    def test_item_trash_is_counted_and_preview_truncation_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp))
            sorting.trash_item(ws, "png/a.png", [])
            self.assertEqual(trash.trashed(ws), {"png": 1})
            (ws / "txt" / "fifty.txt").write_text("\n".join(str(i) for i in range(50)) + "\n")
            self.assertFalse(sorting.preview(ws, "txt/fifty.txt")["truncated"])
            (ws / "txt" / "more.txt").write_text("\n".join(str(i) for i in range(51)))
            self.assertTrue(sorting.preview(ws, "txt/more.txt")["truncated"])
            (ws / "txt" / "100%.txt").write_text("percent")
            self.assertEqual(sorting.preview(ws, "txt/100%25.txt")["content"], "percent")
