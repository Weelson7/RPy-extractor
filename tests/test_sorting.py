"""L3: one-by-one sorting (SORT) as a property: any sequence of keep, trash and rename, undone
step by step, gives back the exact workspace it started from (names and bytes); a rename over
an existing file or to an illegal name is refused; an undo with nothing left, or of a file that
is gone, is named; previews never show binary data as text; the queue opens on what can be
previewed (images, audio, video, text) and keeps path order within each kind."""

from __future__ import annotations

import hashlib
import random
import tempfile
import unittest
from pathlib import Path

from viwo.contracts import ViwoError
from viwo.core.curation import sorting
from viwo.os import select_os


def _tree(ws: Path) -> dict[str, str]:
    return {
        p.relative_to(ws).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in ws.rglob("*")
        if p.is_file() and not p.relative_to(ws).parts[0].startswith(".")
    }


class QueueOrderTests(unittest.TestCase):
    def test_previewable_files_come_first_and_every_file_once(self) -> None:
        from viwo.core.media import media_type

        rng = random.Random(4)
        exts = [".png", ".ogg", ".mp4", ".txt", ".bin", ".rpyc", ".dds", ".wav", ""]
        for _ in range(10):
            with tempfile.TemporaryDirectory() as tmp:
                ws = Path(tmp)
                made = set()
                for i in range(rng.randint(1, 40)):
                    rel = Path(f"g{rng.randint(0, 3)}") / f"f{i}{rng.choice(exts)}"
                    (ws / rel).parent.mkdir(parents=True, exist_ok=True)
                    (ws / rel).write_bytes(b"x")
                    made.add(rel.as_posix())
                (ws / ".extraction_metadata").mkdir()
                (ws / ".extraction_metadata" / "run.json").write_text("{}")  # never queued
                window = sorting.list_window(ws, 0, 1000)["assets"]
                paths = [a["path"] for a in window]
                self.assertEqual(sorted(paths), sorted(made))
                ranks = [sorting.RANK.get(media_type(Path(p).suffix.lower()), 4) for p in paths]
                self.assertEqual(ranks, sorted(ranks))
                for rank in set(ranks):
                    group = [p for p, r in zip(paths, ranks) if r == rank]
                    self.assertEqual(group, sorted(group, key=lambda x: Path(ws / x)))


class SortSequenceTests(unittest.TestCase):
    def test_every_sequence_undoes_to_where_it_started(self) -> None:
        rng = random.Random(9)
        fs = select_os().fs
        for case in range(20):
            with tempfile.TemporaryDirectory() as tmp:
                ws = Path(tmp) / "ws"
                for i in range(rng.randint(2, 8)):
                    path = ws / rng.choice(["png", "txt"]) / f"f{i}.{rng.choice(['png', 'txt'])}"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(rng.randbytes(rng.randint(1, 50)))
                start, history = _tree(ws), []
                for _ in range(rng.randint(1, 12)):
                    files = sorting.asset_files(ws)
                    if not files:
                        break
                    encoded = sorting.encode(ws.resolve(), rng.choice(files))
                    action = rng.choice(["keep", "trash", "rename", "rename-clash", "rename-bad"])
                    if action == "keep":
                        sorting.keep(ws, encoded, history)
                    elif action == "trash":
                        sorting.trash_item(ws, encoded, history)
                    elif action == "rename":
                        sorting.rename(
                            ws, encoded, f"r{len(history)}_{rng.randrange(99)}.x", history, fs
                        )
                    else:
                        before = len(history)
                        other = rng.choice(files).name if action == "rename-clash" else "bad/name"
                        path = sorting.resolve(ws, encoded)
                        if action == "rename-clash" and (path.parent / other) == path:
                            continue
                        if action == "rename-clash" and not (path.parent / other).exists():
                            continue
                        with self.assertRaises(ViwoError):
                            sorting.rename(ws, encoded, other, history, fs)
                        self.assertEqual(len(history), before)  # a refusal records nothing
                while history:
                    sorting.undo(ws, history)
                self.assertEqual(_tree(ws), start, case)  # every step undone, bytes and names
                with self.assertRaises(ViwoError) as err:
                    sorting.undo(ws, history)
                self.assertEqual(err.exception.code, "invalid_request")

    def test_undo_of_a_vanished_file_and_previews(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            (ws / "txt").mkdir(parents=True)
            text, binary, image = ws / "txt" / "a.txt", ws / "txt" / "b.lmp", ws / "txt" / "c.png"
            text.write_text("line one\nline two\n")
            binary.write_bytes(bytes(range(256)) * 4)
            image.write_bytes(b"\x89PNG")
            history = []
            sorting.trash_item(ws, sorting.encode(ws.resolve(), text), history)
            Path(history[-1]["target"]).unlink()  # gone from the trash behind ViWo's back
            with self.assertRaises(ViwoError) as err:
                sorting.undo(ws, history)
            self.assertEqual(err.exception.code, "not_found")
            enc = lambda p: sorting.encode(ws.resolve(), p)  # noqa: E731
            self.assertEqual(sorting.preview(ws, enc(binary))["type"], "binary")
            self.assertEqual(sorting.preview(ws, enc(image))["type"], "image")
            (ws / "txt" / "d.txt").write_text("\n".join(f"l{i}" for i in range(80)))
            shown = sorting.preview(ws, enc(ws / "txt" / "d.txt"), max_lines=50)
            self.assertEqual(
                (shown["type"], shown["lineCount"], shown["truncated"]), ("text", 50, True)
            )
            clash = ws / "txt" / "c.png__undo"  # a restore never overwrites what is there now
            history = []
            sorting.trash_item(ws, enc(image), history)
            image.write_bytes(b"a new file in its place")
            sorting.undo(ws, history)
            self.assertTrue(image.is_file() and (ws / "txt" / "c__undo1.png").is_file())
            self.assertFalse(clash.exists())


if __name__ == "__main__":
    unittest.main()
