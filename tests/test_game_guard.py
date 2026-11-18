"""L3: the game folder is read-only, structurally (doc 3.1 PREPARE, doc 18 COPY).

Properties, over random game layouts and random markers on the game folder (a patched copy
copied over the install carries `.viwo-patched/`, a stray `.viwo-workspace` may be there too):

1. `guard.guarded(game, folder)` refuses exactly the folders that are the game, lie inside it
   or hold it; ViWo's temp folder may hold it. No marker on either folder changes the answer.
2. `guard.guarded(None, folder)` (a run on a process id: no game to compare with) refuses a
   patched copy and a folder of files that is no ViWo workspace; an empty folder, a missing
   one and a ViWo workspace pass.
3. Every CLI command that takes a game and a folder it writes (workspace, --out, --copy), run
   with that folder = the game, a folder inside it (new or existing) or the folder holding it,
   exits `refused` (3), says why, and leaves the game's tree byte-identical, its folders too.
4. The commands that take no game (dump, trace, hook, profile, record, sanitize), run on the
   game folder itself, exit `refused` and leave it identical, whatever the patched marker.
   What they cannot tell (a new folder inside a game, a folder above one, a game carrying a
   ViWo workspace marker) is not asserted: there is no game path to compare with.
"""

from __future__ import annotations

import json
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import homes, make_zip, runtime
from tests.test_cli import run
from viwo import cli
from viwo.cli import EXIT
from viwo.contracts import ViwoError
from viwo.contracts import workspace as ws
from viwo.core.pipeline.guard import PATCHED, guarded

INI = "[startup]\nfeatures = extraction, capture, analysis\n[plugins]\ngeneric = on\n"


def _state(folder: Path) -> dict[str, str]:
    """Every entry under folder: a file's bytes, or "dir" (a created empty folder shows too)."""
    return {
        p.relative_to(folder).as_posix(): p.read_bytes().hex() if p.is_file() else "dir"
        for p in folder.rglob("*")
    }


def _game(root: Path, rng: random.Random, marks: set[str]) -> Path:
    game = root / "lib" / "Game"
    body = bytearray(b"MZ" + rng.randbytes(254))
    for i in range(rng.randint(1, 6)):
        part = game / rng.choice(["data", "bin", "data/sub"]) / f"f{i}.bin"
        part.parent.mkdir(parents=True, exist_ok=True)
        part.write_bytes(rng.randbytes(rng.randint(0, 200)))
    (game / "Game.exe").write_bytes(bytes(body))
    if "patched" in marks:
        (game / PATCHED).mkdir()
        (game / PATCHED / "report.json").write_text("{}")
    if "workspace" in marks:
        (game / ws.MARKER).write_text("")
    return game


def _inputs(root: Path, game: Path) -> dict[str, Path]:
    """What the commands read besides the game: a fitting patch set, a mod, a run record."""
    body = (game / "Game.exe").read_bytes()
    patch = {"file": "Game.exe", "offset": "0x2", "original": f"{body[2]:02x}"}
    patch["patched"] = f"{(body[2] + 1) % 256:02x}"
    sets = root / "in" / "p.patch.json"
    sets.parent.mkdir(parents=True, exist_ok=True)
    sets.write_text(json.dumps({"schema": 1, "patches": [patch]}))
    mod = make_zip(root / "in" / "m.zip", {"viwo-mod.json": b'{"name": "m", "files": []}'})
    work = root / "in" / "ws"
    (work / ws.RUNS_DIR).mkdir(parents=True)
    (work / ws.MARKER).write_text("")
    record = work / ws.RUNS_DIR / "job.json"
    request = {"game_path": str(game), "mode": "auto"}
    record.write_text(json.dumps({"finished": "1", "request": request}))
    script = root / "in" / "hook.js"
    script.write_text("console.log('x');")
    return {"set": sets, "mod": mod, "ws": work, "record": record, "script": script}


def _with_game(game: Path, given: dict[str, Path], ok: Path) -> dict[str, list[str]]:
    """command -> argv with {P} where the folder under test goes."""
    g, exe = str(game), str(game / "Game.exe")
    return {
        "extract": ["extract", g, "--workspace", "{P}", "--on-existing", "new"],
        "replay": ["replay", str(given["record"]), "--workspace", "{P}", "--on-existing", "new"],
        "capture": ["capture", g, "--exe", exe, "--workspace", "{P}", "--confirm"],
        "attach": ["attach", g, "--target", "game-exe", "--workspace", "{P}", "--confirm"],
        "analyze": ["analyze", g, "--target", "game-exe", "--workspace", "{P}"],
        "analyze --open": ["analyze", g, "--target", "game-exe", "--workspace", "{P}", "--open"],
        "agent": ["agent", g, "--exe", exe, "--workspace", "{P}"],
        "agent --copy": ["agent", g, "--exe", exe, "--workspace", str(ok), "--copy", "{P}"],
        "patch": ["patch", g, str(given["set"]), "--out", "{P}"],
        "mod apply": ["mod", "apply", g, str(given["mod"]), "--copy", "{P}"],
        "repack": ["repack", str(given["ws"]), "--out", "{P}"],
    }


def _without_game(given: dict[str, Path]) -> dict[str, list[str]]:
    pid = ["--pid", "4242", "--workspace", "{P}"]
    return {
        "dump": ["dump", *pid],
        "trace": ["trace", *pid],
        "hook": ["hook", *pid, "--script", str(given["script"])],
        "profile": ["profile", *pid],
        "record": ["record", "--workspace", "{P}"],
        "sanitize": ["sanitize", "{P}"],
        "sanitize --apply": ["sanitize", "{P}", "--apply"],
    }


class GuardPropertyTests(unittest.TestCase):
    def test_refused_exactly_when_the_folder_is_in_holds_or_is_the_game(self) -> None:
        rng = random.Random(41)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(30):
                parts = [f"d{rng.randrange(3)}" for _ in range(rng.randint(1, 4))]
                game = root / f"r{i}" / Path(*parts)
                game.mkdir(parents=True)
                for mark in rng.sample([PATCHED, ws.MARKER], rng.randint(0, 2)):
                    (game / mark).mkdir()  # a marker never switches the guard off
                up = rng.randint(0, len(parts))
                above = game.parents[up - 1] if up else game
                down = Path(*(f"s{rng.randrange(2)}" for _ in range(rng.randint(0, 2))))
                aside = root / f"r{i}" / "elsewhere" / down
                folder = rng.choice([above, game / down, aside])
                f, g = folder.resolve(), game.resolve()
                bad = f == g or g in f.parents or f in g.parents  # is, is inside, holds
                with self.subTest(game=game, folder=folder):
                    if bad:
                        with self.assertRaises(ViwoError) as err:
                            guarded(game, folder, "patched copy", temp=root)
                        self.assertEqual(err.exception.code, "refused")
                        self.assertIn("game folder", err.exception.message)
                        self.assertTrue(err.exception.hint)
                    else:
                        self.assertEqual(guarded(game, folder, temp=root), folder)

    def test_without_a_game_a_folder_that_may_be_one_is_refused(self) -> None:
        rng = random.Random(43)
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(30):
                folder = Path(tmp) / f"f{i}"
                files, patched, owned = (rng.random() < 0.5 for _ in range(3))
                if files or patched or owned or rng.random() < 0.5:
                    folder.mkdir()
                if files:
                    (folder / rng.choice(["a.bin", "data"])).mkdir(exist_ok=True)
                if patched:
                    (folder / PATCHED).mkdir()
                if owned:
                    (folder / ws.MARKER).write_text("")
                if rng.random() < 0.5 and folder.is_dir():
                    (folder / ".runtime").mkdir()  # ViWo's own dot-folders are no files
                with self.subTest(files=files, patched=patched, owned=owned):
                    if patched or (files and not owned):
                        with self.assertRaises(ViwoError) as err:
                            guarded(None, folder)
                        self.assertEqual(err.exception.code, "refused")
                        self.assertIn("empty folder or a ViWo workspace", err.exception.hint)
                    else:
                        self.assertEqual(guarded(None, folder), folder)


class CommandMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, homes(self.tmp.name))
        env.start()
        self.addCleanup(env.stop)
        (self.root / "rt").mkdir()
        self.rt = runtime(self.root / "rt", INI)
        boot = mock.patch.object(cli, "boot_for_cli", return_value=self.rt)
        boot.start()
        self.addCleanup(boot.stop)
        self.ini = str(self.root / "rt" / "test.ini")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _refused(self, name: str, argv: list[str], folder: Path, lib: Path) -> None:
        before = _state(lib)
        line = ["--quiet", "--ini", self.ini, *(str(folder) if a == "{P}" else a for a in argv)]
        code, _, err = run(line)
        with self.subTest(command=name, folder=folder):
            self.assertEqual(code, EXIT["refused"], err)
            self.assertIn("viwo: refused:", err)
            self.assertIn("game", err)  # the reason names the game (or a folder that may be one)
            self.assertNotIn("Traceback", err)
            self.assertEqual(_state(lib), before)  # byte-identical, no folder created

    def test_every_command_with_a_game_refuses_its_folder_in_on_or_around_it(self) -> None:
        rng = random.Random(47)
        for i in range(2):
            marks = set(rng.sample(["patched", "workspace"], rng.randint(0, 2)))
            root = self.root / f"case{i}"
            game = _game(root, rng, marks)
            given = _inputs(root, game)
            folders = [game, game / "data", game / "new" / "out", game.parent]
            for name, argv in _with_game(game, given, root / "fine").items():
                for folder in folders:
                    self._refused(name, argv, folder, game.parent)

    def test_every_command_without_a_game_refuses_the_game_folder_itself(self) -> None:
        rng = random.Random(53)
        for marks in (set(), {"patched"}, {"patched", "workspace"}):
            root = self.root / f"m{len(marks)}"
            game = _game(root, rng, marks)
            for name, argv in _without_game(_inputs(root, game)).items():
                self._refused(name, argv, game, game.parent)


if __name__ == "__main__":
    unittest.main()
