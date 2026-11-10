"""L3: a folder of the user's own files converted into a workspace (core/adopt.py, doc 4.3).
Properties over random trees: every file's bytes survive exactly once (duplicates included) in
the group of its type; provenance names each file's original path; a dot-folder at the top is
untouched; the folders the moves emptied are gone; the marker is written last and a second run
changes nothing; the preview says what the run then does; a home folder is refused."""

import hashlib
import json
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from viwo.contracts import ViwoError
from viwo.contracts import workspace as ws
from viwo.core import adopt


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root: Path, rng: random.Random) -> Counter:
    """Random files: nested folders, mixed and missing extensions, repeated contents."""
    blobs = [rng.randbytes(rng.randint(0, 40)) for _ in range(4)]
    names = ["a.flac", "b.FLAC", "c.csv", "d", "e.png", "f.png", "flac", "g.tar.gz"]
    for _ in range(rng.randint(1, 14)):
        folder = root.joinpath(*rng.sample(["x", "y", "flac", "deep"], rng.randint(0, 3)))
        if any(p.is_file() for p in (folder, *folder.parents)):
            continue  # a file already holds that name (the top-level `flac`)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / rng.choice(names)
        if not path.exists():
            path.write_bytes(rng.choice(blobs))
    return Counter(digest(p) for p in root.rglob("*") if p.is_file())


class AdoptTests(unittest.TestCase):
    def test_every_file_lands_once_in_its_group_with_its_original_path(self) -> None:
        rng = random.Random(43)
        for case in range(60):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "songs"
                root.mkdir()
                before = tree(root, rng)
                (root / ".git").mkdir()
                (root / ".git" / "HEAD").write_text("ref")
                plan = adopt.preview(root)
                done = adopt.adopt(root)
                self.assertEqual((done["files"], done["moved"]), (plan["files"], plan["moves"]))
                files = [p for p in root.rglob("*") if p.is_file() and not ws.is_reserved(
                    p.relative_to(root).parts[0])]  # fmt: skip
                self.assertEqual(Counter(digest(p) for p in files), before, case)
                for p in files:  # each in the group of its type, one level down
                    self.assertEqual(p.parent.name, ws.ext_folder(ws.ext_of(p)), (case, p))
                    self.assertEqual(p.parent.parent, root, (case, p))
                records = [json.loads(x) for x in
                           (root / ws.PROVENANCE_FILE).read_text("utf-8").splitlines()]  # fmt: skip
                self.assertEqual(sorted(r["path"] for r in records),
                                 sorted(p.relative_to(root).as_posix() for p in files))  # fmt: skip
                self.assertEqual({r["kind"] for r in records} - {"adopted"}, set())
                for r in records:
                    self.assertEqual(digest(root / r["path"]), r["sha256"])
                self.assertEqual((root / ".git" / "HEAD").read_text(), "ref")
                self.assertTrue(ws.has_marker(root))
                groups = {p.parent.name for p in files}
                dirs = {p.name for p in root.iterdir() if p.is_dir() and not ws.is_reserved(p.name)}
                self.assertEqual(dirs, groups, case)  # the emptied folders are gone
                again = adopt.adopt(root)
                self.assertEqual((again["moved"], again["owned"]), (0, True))
                self.assertEqual(len((root / ws.PROVENANCE_FILE).read_text().splitlines()),
                                 len(records))  # fmt: skip

    def test_a_home_or_missing_folder_is_refused_before_anything_moves(self) -> None:
        for folder in (Path.home(), Path(tempfile.gettempdir()) / "viwo-no-such-folder"):
            self.assertTrue(adopt.preview(folder)["refused"])
            with self.assertRaises(ViwoError) as err:
                adopt.adopt(folder)
            self.assertEqual(err.exception.code, "refused")


if __name__ == "__main__":
    unittest.main()
