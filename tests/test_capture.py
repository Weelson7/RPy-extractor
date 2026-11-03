"""L3: runtime capture pilot: refusal policy, journaled overlay, fake RenderDoc run + diff."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import make_png, runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest, ViwoError
from viwo.core.capture import CaptureRequest, capture, renderdoc
from viwo.core.capture.journal import Journal, pending
from viwo.core.capture.policy import check
from viwo.core.capture.renderdoc import quiet_ui
from viwo.core.pipeline.runner import extract

FAKE_RDCMD = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
assert args[:2] == ["capture", "-w"], args  # -w in both modes: the game is in the tree
template = Path(args[args.index("-c") + 1])
Path(str(template) + "_frame120.rdc").write_bytes(b"RDOC")
"""
FAKE_RDPY = """#!{python}
import os, sys, shutil, time
from pathlib import Path
if sys.argv[1].endswith("rd_trigger.py"):  # unattended: the trigger asks for the frame
    assert sys.argv[2] == os.environ["VIWO_RD_DELAY"], sys.argv
    Path({marker!r}).write_text("ran")
    time.sleep(0.5)
    sys.exit(0)
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


class QuietUiTests(unittest.TestCase):
    def test_first_run_prompts_answered_once_user_choice_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"APPDATA": tmp}):
            quiet_ui()
            cfg = json.loads(renderdoc.ui_config().read_text(encoding="utf-8"))
            self.assertTrue(cfg["Analytics_ManualCheck"] and cfg["Tips_HasSeenFirst"])
            cfg.update({"Analytics_TotalOptOut": False, "Tips_HasSeenFirst": False})
            renderdoc.ui_config().write_text(json.dumps(cfg), encoding="utf-8")
            quiet_ui()
            cfg = json.loads(renderdoc.ui_config().read_text(encoding="utf-8"))
            self.assertEqual(
                (cfg["Analytics_TotalOptOut"], cfg["Tips_HasSeenFirst"]), (False, True)
            )


class PolicyTests(unittest.TestCase):
    def test_feature_switch_confirmation_and_warnings(self) -> None:
        """Capture is gated by the ini switch and one confirmation; the rest are warnings."""
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
            plain = [w for w in check(rt, game, True, []) if "network" not in w]
            self.assertEqual(len(plain), 1)  # the offline advice; the network probe may add one
            (game / "EasyAntiCheat").mkdir()
            (root / "Overwatch").mkdir()
            self.assertIn("anti-cheat", check(rt, game, True, [])[0])
            warned = [
                w for w in check(rt, root / "Overwatch", True, ["overwatch"]) if "network" not in w
            ]
            self.assertEqual(len(warned), 3)  # online title, sensitive plugin, offline advice
            self.assertIn("online", warned[0])


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
            self.assertFalse((game / "BepInEx").exists())  # folders the agent created are gone
            self.assertEqual(pending(root / "state"), [])

    def test_damaged_journal_restores_what_it_can(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            (game / "a.txt").write_text("A")
            journal = Journal(root / "state", game, "s2")
            journal.write("a.txt", b"patched")
            journal.write("new/b.txt", b"B")
            text = journal.file.read_text(encoding="utf-8")
            journal.file.write_text(text[:-10], encoding="utf-8")  # truncated last line
            warned = []
            [found] = pending(root / "state", warned.append)
            self.assertEqual(len(found.entries), 1)
            self.assertTrue(warned and "damaged" in warned[0])
            self.assertEqual(found.restore(), [])
            self.assertEqual((game / "a.txt").read_text(), "A")
            (root / "state" / "s3").mkdir(parents=True)
            (root / "state" / "s3" / "journal.json").write_text("garbage", encoding="utf-8")
            self.assertEqual(pending(root / "state", warned.append), [])
            self.assertTrue(any("unreadable" in w for w in warned))


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
                FAKE_RDPY.format(
                    python=sys.executable,
                    known=str(known),
                    fresh=str(fresh),
                    marker=str(root / "trigger.ran"),
                ),
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
            auto = CaptureRequest(game, game / "Game.exe", ws, True, capture_after=0.2)
            self.assertEqual(capture(rt, auto)["alreadyStatic"], 2)  # unattended: trigger + stop
            self.assertTrue((root / "trigger.ran").is_file())
            foreign = root / "foreign"
            foreign.mkdir()
            (foreign / "mine.txt").write_text("x")
            with self.assertRaises(ViwoError):
                capture(rt, CaptureRequest(game, game / "Game.exe", foreign, confirmed=True))


if __name__ == "__main__":
    unittest.main()
