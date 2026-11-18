"""L3: COLLECT goes on when a source file is held while it is copied (an antivirus taking it
between its hash and its copy). Properties, over random trees copied from a game and moved from
staging: the run never stops for a held source; every held file is named once in `unreadable`
and nothing of it is left in the workspace; every other file is collected whole with its
provenance; a refusal on the workspace side still stops the run. On Windows the same with real
share locks: an exclusive hold is named, and a staging file whose copy landed but whose
original stays held (no delete sharing) is collected."""

from __future__ import annotations

import os
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from viwo.contracts import CancelToken
from viwo.contracts import workspace as ws
from viwo.core.pipeline import collect

REAL_COPY, REAL_MOVE = shutil.copy2, shutil.move


def _tree(rng: random.Random, root: Path, tag: str) -> dict[str, bytes]:
    files = {}
    for i in range(rng.randint(1, 8)):
        name = f"{tag}{i}.{rng.choice(('png', 'ogg', 'txt'))}"
        files[name] = f"{tag}{i}".encode() + rng.randbytes(rng.randint(0, 300))
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(files[name])
    return files


def _collected(workspace: Path) -> list[bytes]:
    skip = {ws.MARKER, ws.EXPORT_MAP, ws.NAMES_FILE}
    return sorted(
        p.read_bytes() for p in workspace.rglob("*") if p.is_file() and p.name not in skip
    )


class HeldWhileCopiedTests(unittest.TestCase):
    def test_a_held_source_is_named_and_the_run_goes_on(self) -> None:
        rng = random.Random(74)
        for case in range(30):
            with tempfile.TemporaryDirectory() as tmp:
                game, staging, workspace = (Path(tmp) / n for n in ("game", "staging", "ws"))
                files = {**_tree(rng, game, "g"), **_tree(rng, staging, "s")}
                held = set(rng.sample(sorted(files), rng.randint(0, len(files))))

                def refuse(src, dst, real):
                    if Path(src).name in held:  # a half copy, then the hold
                        Path(dst).write_bytes(b"half")
                        raise PermissionError(13, "held by another process")
                    return real(src, dst)

                with (
                    mock.patch.object(shutil, "copy2", lambda s, d: refuse(s, d, REAL_COPY)),
                    mock.patch.object(shutil, "move", lambda s, d: refuse(s, d, REAL_MOVE)),
                    mock.patch.object(collect, "_readable", lambda p: p.name not in held),
                ):
                    sources = [
                        collect.Source(game, False, "game"),
                        collect.Source(staging, True, "x"),
                    ]
                    report = collect.collect(sources, workspace, None, set(), CancelToken())
                named = sorted(entry.split(" (")[0] for entry in report.unreadable)
                self.assertEqual(named, sorted(held), case)
                kept = sorted(blob for name, blob in files.items() if name not in held)
                self.assertEqual(_collected(workspace), kept)  # whole, and nothing half
                self.assertEqual((report.collected, len(report.provenance)), (len(kept),) * 2)

    def test_a_refusal_on_the_workspace_side_still_stops_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "game"
            _tree(random.Random(75), game, "g")

            def full(src, dst):
                raise OSError(28, "No space left on device")

            with mock.patch.object(shutil, "copy2", full), self.assertRaises(OSError):
                source = collect.Source(game, False, "game")
                collect.collect([source], Path(tmp) / "ws", None, set(), CancelToken())


@unittest.skipUnless(os.name == "nt", "Windows share locks")
class RealLockTests(unittest.TestCase):
    def setUp(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k.CreateFileW.restype = wintypes.HANDLE
        self.k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.k.CreateFileW.argtypes += [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
        self.k.CreateFileW.argtypes += [wintypes.HANDLE]
        self.k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handles: list = []

    def tearDown(self) -> None:
        self.release()

    def release(self) -> None:
        while self.handles:
            self.k.CloseHandle(self.handles.pop())

    def hold(self, path: Path, share: int) -> None:
        """Open path for reading with only `share` allowed to others (0: nothing)."""
        self.handles.append(self.k.CreateFileW(str(path), 0x80000000, share, None, 3, 0x80, None))

    def test_a_real_hold_after_the_hash_is_named_and_a_held_staging_original_is_kept(self):
        rng = random.Random(76)
        with tempfile.TemporaryDirectory() as tmp:
            game, staging, workspace = (Path(tmp) / n for n in ("game", "staging", "ws"))
            files = {**_tree(rng, game, "g"), **_tree(rng, staging, "s")}
            grabbed, kept = sorted(n for n in files if n[0] == "g")[0], sorted(files)[-1]
            self.hold(staging / kept, 1)  # read shared, delete not: the move's unlink fails

            def grab(src, dst):  # the hold starts after the hash, as an antivirus does
                if Path(src).name == grabbed:
                    self.hold(Path(src), 0)
                return REAL_COPY(src, dst)

            try:
                with mock.patch.object(shutil, "copy2", grab):
                    sources = [collect.Source(game, False, "g"), collect.Source(staging, True, "s")]
                    report = collect.collect(sources, workspace, None, set(), CancelToken())
            finally:
                self.release()  # before the folder goes
            self.assertEqual([e.split(" (")[0] for e in report.unreadable], [grabbed])
            want = sorted(blob for name, blob in files.items() if name != grabbed)
            self.assertEqual(_collected(workspace), want)
            self.assertTrue((staging / kept).exists())  # held: staging keeps it until it goes


if __name__ == "__main__":
    unittest.main()
