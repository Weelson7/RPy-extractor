"""L3: provenance follows files that SORT or the sanitizer rename, trash, restore or move."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_png
from viwo.contracts import workspace as ws
from viwo.core import provenance, sanitizer
from viwo.core.curation import sorting
from viwo.os.windows import WindowsFs


def make_workspace(root: Path) -> Path:
    work = root / "ws"
    (work / "png").mkdir(parents=True)
    (work / "jpg").mkdir()
    (work / ws.MARKER).write_text("")
    png = make_png(root / "a.png").read_bytes()
    (work / "png" / "a.png").write_bytes(png)
    (work / "jpg" / "photo.jpg").write_bytes(png)  # really a PNG: the sanitizer renames it
    (work / ws.METADATA_DIR).mkdir()
    entries = [
        {"path": "png/a.png", "sha256": "x", "kind": "loose"},
        {"path": "jpg/photo.jpg", "sha256": "x", "kind": "loose"},
    ]
    (work / ws.PROVENANCE_FILE).write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return work


def paths(work: Path) -> set[str]:
    lines = (work / ws.PROVENANCE_FILE).read_text().splitlines()
    return {json.loads(line)["path"] for line in lines}


class ProvenanceTests(unittest.TestCase):
    def test_sort_rename_trash_and_undo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work, history = make_workspace(Path(tmp)), []
            sorting.rename(work, "png/a.png", "hero.png", history, WindowsFs())
            self.assertIn("png/hero.png", paths(work))
            sorting.trash_item(work, "png/hero.png", history)
            trashed = next(p for p in paths(work) if p.startswith(ws.TRASH_DIR))
            self.assertTrue((work / trashed).is_file())
            sorting.undo(work, history)  # back from the trash
            self.assertIn("png/hero.png", paths(work))
            sorting.undo(work, history)  # rename undone
            self.assertEqual(paths(work), {"png/a.png", "jpg/photo.jpg"})
            self.assertTrue(all((work / p).is_file() for p in paths(work)))

    def test_sanitizer_apply_and_undo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = make_workspace(Path(tmp))
            plan = sanitizer.plan(work)
            applied = sanitizer.apply(work, plan["planId"])
            self.assertTrue(applied["applied"] >= 1)
            self.assertTrue(all((work / p).is_file() for p in paths(work)), paths(work))
            self.assertNotIn("jpg/photo.jpg", paths(work))
            sanitizer.undo(work, applied["undoToken"])
            self.assertEqual(paths(work), {"png/a.png", "jpg/photo.jpg"})

    def test_rewrite_leaves_other_lines_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = make_workspace(Path(tmp))
            self.assertEqual(provenance.rewrite(work, {"nope": "x", "png/a.png": None}), 0)
            self.assertEqual(provenance.rewrite(work, {"png/a.png": "png/b.png"}), 1)
            self.assertEqual(paths(work), {"png/b.png", "jpg/photo.jpg"})


if __name__ == "__main__":
    unittest.main()
