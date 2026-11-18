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
from types import SimpleNamespace

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


class ReleasedMoveTests(unittest.TestCase):
    def test_a_file_let_go_in_time_moves_once_and_one_held_longer_says_so(self) -> None:
        from unittest import mock

        from viwo.api.app import in_use

        rng = random.Random(32)
        for _ in range(30):
            held, tries = rng.randint(0, 6), rng.randint(1, 5)
            calls = []

            def move(src, dst, held=held, calls=calls):
                calls.append(src)
                if len(calls) <= held:  # the preview stream still has it open
                    raise PermissionError(13, "in use")

            with (
                mock.patch.object(sorting.shutil, "move", move),
                mock.patch.object(sorting.time, "sleep"),
            ):
                if held < tries:
                    sorting.move_released(Path("a"), Path("b"), tries)
                    self.assertEqual(len(calls), held + 1)  # moved once, as soon as it was let go
                else:
                    with self.assertRaises(PermissionError):
                        sorting.move_released(Path("a"), Path("b"), tries)
                    self.assertEqual(len(calls), tries)
        locked = PermissionError(13, "The process cannot access the file")
        locked.winerror = 32
        self.assertIn("in use by another program", in_use(locked))
        self.assertEqual(in_use(FileNotFoundError(2, "gone")), "gone")


class HeldQueueTests(unittest.TestCase):
    def test_the_held_queue_is_never_stale_and_never_shared(self) -> None:
        """The queue is kept between requests: after any file appears, goes or is renamed, at
        any depth, the next queue is the one a fresh walk gives; a caller's changes to the
        list it got never reach the next caller."""
        rng = random.Random(75)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "ws"
            (folder / "png").mkdir(parents=True)
            for step in range(60):
                files = [p for p in folder.rglob("*") if p.is_file()]
                move = rng.choice(("add", "add", "deep", "drop", "rename") if files else ("add",))
                if move in ("add", "deep"):
                    home = (
                        folder / rng.choice(("png", "glb", "x")) / ("sub" if move == "deep" else "")
                    )
                    home.mkdir(parents=True, exist_ok=True)
                    (home / f"f{step}{rng.choice(('.png', '.glb', '.bin'))}").write_bytes(b"x")
                elif move == "drop":
                    rng.choice(files).unlink()
                else:
                    victim = rng.choice(files)
                    victim.rename(victim.with_name(f"r{step}{victim.suffix}"))
                got = sorting.asset_files(folder)
                want = sorted(p for p in folder.rglob("*") if p.is_file())
                self.assertEqual(sorted(got), want, (step, move))
                got.clear()  # what a caller does to its list is its own business
                self.assertEqual(sorted(sorting.asset_files(folder)), want)


class TypeFilterTests(unittest.TestCase):
    def test_a_type_pick_pages_that_type_over_the_whole_workspace(self) -> None:
        """Whatever the files and the pick: the pages together hold exactly the files of the
        picked types, each once, in the queue's order; the count is theirs; no pick is the
        whole queue; the counts per type stay those of the whole workspace."""
        from viwo.api.handlers import assets_window
        from viwo.core.media import media_type

        rng = random.Random(74)
        exts = (".png", ".ogg", ".mp4", ".glb", ".txt", ".bin", ".owmdl")
        with tempfile.TemporaryDirectory() as tmp:
            for round_ in range(8):
                folder = Path(tmp) / f"w{round_}"
                for i in range(rng.randint(0, 60)):
                    file = folder / rng.choice(("a", "b")) / f"f{i}{rng.choice(exts)}"
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_bytes(b"x")
                folder.mkdir(exist_ok=True)
                queue = sorting.asset_files(folder)
                kinds = ("image", "audio", "video", "model", "text", "other")
                pick = frozenset(rng.sample(kinds, rng.randint(0, 3)))
                want = [p for p in queue if not pick or media_type(p.suffix) in pick]
                got, offset, limit = [], 0, rng.randint(1, 9)
                while True:
                    page = sorting.list_window(folder, offset, limit, pick)
                    self.assertEqual(page["totalCount"], len(want))
                    got += [a["name"] for a in page["assets"]]
                    offset += limit
                    if not page["assets"]:
                        break
                self.assertEqual(got, [p.name for p in want])
                app = SimpleNamespace(workspace=folder)
                answer = assets_window(app, {"types": ",".join(sorted(pick)), "limit": "5"})
                self.assertEqual(answer["totalCount"], len(want))
                self.assertEqual(answer["total"], len(queue))  # the chips count everything


if __name__ == "__main__":
    unittest.main()
