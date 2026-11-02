"""L3: runtime capture pilot: refusal policy, journaled overlay, fake RenderDoc run + diff."""

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_png, runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest, ViwoError
from viwo.core.capture import CaptureRequest, capture
from viwo.core.capture.journal import Journal, pending
from viwo.core.capture.policy import check
from viwo.core.pipeline.runner import extract

FAKE_RDCMD = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
assert args[:2] == ["capture", "-w"], args
template = Path(args[args.index("-c") + 1])
Path(str(template) + "_frame120.rdc").write_bytes(b"RDOC")
"""
FAKE_RDPY = """#!{python}
import sys, shutil
from pathlib import Path
helper, rdc, out = sys.argv[1:4]
assert helper.endswith("rd_harvest.py")
Path(out).mkdir(parents=True, exist_ok=True)
shutil.copy({known!r}, Path(out) / "tex_1.png")
shutil.copy({fresh!r}, Path(out) / "tex_2.png")
"""


def script(folder: Path, name: str, body: str) -> Path:
    path = folder / f"{name}.py"
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    if sys.platform == "win32":
        wrapper = folder / f"{name}.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{path}" %*\r\n')
        return wrapper
    return path


class PolicyTests(unittest.TestCase):
    def test_refusals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "MyGame"
            game.mkdir()
            off = runtime(root)
            with self.assertRaises(ViwoError) as err:
                check(off, game, True, [])
            self.assertEqual(err.exception.code, "refused")
            rt = runtime(root, "[startup]\nfeatures = extraction, capture\n")
            with self.assertRaises(ViwoError) as err:
                check(rt, game, False, [])
            self.assertEqual(err.exception.code, "needs_decision")
            self.assertTrue(check(rt, game, True, []))
            (game / "EasyAntiCheat").mkdir()
            for folder in (game, root / "Overwatch"):
                folder.mkdir(exist_ok=True)
                with self.assertRaises(ViwoError) as err:
                    check(rt, folder, True, [])
                self.assertEqual(err.exception.code, "refused")
            with self.assertRaises(ViwoError):
                check(rt, root / "Overwatch", True, ["overwatch"])


class JournalTests(unittest.TestCase):
    def test_restore_and_crash_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            (game / "config.ini").write_text("original")
            before = tree_hashes(game)
            journal = Journal(root / "state", game, "s1")
            journal.write("config.ini", b"patched")
            journal.write("BepInEx/core/agent.dll", b"agent")
            with self.assertRaises(ViwoError):
                journal.write("../outside.txt", b"no")
            self.assertEqual((game / "config.ini").read_text(), "patched")
            # simulate a crash: a new process finds the journal and restores it
            [found] = pending(root / "state")
            self.assertEqual(found.restore(), [])
            self.assertEqual({k: v for k, v in tree_hashes(game).items()}, before)
            self.assertEqual(pending(root / "state"), [])


class CaptureRunTests(unittest.TestCase):
    def test_capture_harvest_gather_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            known = make_png(game / "title.png")  # static extraction finds this one
            fresh = make_png(root / "fresh.png", 8, 8, (1, 2, 3))
            (game / "Game.exe").write_bytes(b"MZ")
            rdcmd = script(root, "fake_rdcmd", FAKE_RDCMD.format(python=sys.executable))
            rdpy = script(
                root,
                "fake_rdpy",
                FAKE_RDPY.format(python=sys.executable, known=str(known), fresh=str(fresh)),
            )
            ini = "[startup]\nfeatures = extraction, capture\n"
            ini += f"[tools]\nrenderdoccmd = {rdcmd}\nrdpython = {rdpy}\n"
            rt = runtime(root, ini)
            ws = root / "ws"
            extract(rt, ExtractionRequest(str(game), str(ws)), "j", lambda e: None, CancelToken())
            before = tree_hashes(game)
            report = capture(rt, CaptureRequest(game, game / "Game.exe", ws, confirmed=True))
            self.assertEqual(
                (report["gathered"], report["newVsStatic"]), (1, 1)
            )  # tex_1 = title.png
            self.assertEqual(report["new"], ["png/tex_2.png"])
            self.assertEqual(tree_hashes(game), before)
            foreign = root / "foreign"
            foreign.mkdir()
            (foreign / "mine.txt").write_text("x")
            with self.assertRaises(ViwoError):
                capture(rt, CaptureRequest(game, game / "Game.exe", foreign, confirmed=True))


if __name__ == "__main__":
    unittest.main()
