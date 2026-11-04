"""L3: one-by-one sorting (03 SORT) as a property: any sequence of keep, trash and rename, undone
step by step, gives back the exact workspace it started from (names and bytes); a rename over
an existing file or to an illegal name is refused; an undo with nothing left, or of a file that
is gone, is named; previews never show binary data as text."""

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
                        other = rng.choice(files).name if action == "rename-clash" else "bad:name?"
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
