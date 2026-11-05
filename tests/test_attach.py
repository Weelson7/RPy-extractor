"""L3: the dynamic arm's attach tools (doc 11.2, D3): x64dbg and Cheat Engine on the game itself.
Properties: only the `capture` switch gates them (never `analysis`), with one confirmation per
game; the debugger attaches to the one process running the target's executable (or the pid
given), starts the game's own executable when none runs, and never a copy; several processes
ask for the pid; static ANALYSIS never offers them; the game folder is only read; the CLI and
the API reach the same core."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import cleanup, runtime, tree_hashes, write_ini
from tests.test_analysis import FAKE_GUI, make_games, script
from viwo.contracts import ViwoError
from viwo.core.analysis import handoffs_for
from viwo.core.capture.attach import AttachRequest, attach, attach_for, listing
from viwo.os._shared import CHILDREN

TOOLS = ("x64dbg-gui", "cheatengine-gui")


class AttachTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.unity, _ = make_games(self.root)
        gui = FAKE_GUI.format(python=sys.executable)
        x64 = script(self.root / "x64dbg" / "release" / "x64", "x64dbg", gui)
        ce = script(self.root / "ce", "cheatengine-x86_64", gui)
        self.tools = f"[tools]\nx64dbg = {x64}\ncheatengine = {ce}\n[plugins]\nunity = on\n"
        self.ws = self.root / "ws"

    def tearDown(self) -> None:
        cleanup(self._tmp, 30)  # the killed GUI tools let go of their folders late

    def _ini(self, features: str) -> Path:
        folder = self.root / f"rt-{features.replace(', ', '-')}"
        folder.mkdir(exist_ok=True)
        return write_ini(folder, f"[startup]\nfeatures = {features}\n" + self.tools)

    def _rt(self, features: str):
        ini = self._ini(features)
        return runtime(ini.parent, ini.read_text())

    def _open(self, rt, tool: str, running: list[int], pid: int = 0) -> dict:
        req = AttachRequest(self.unity, self.ws, "g-exe", tool, pid, confirm=True)
        with mock.patch.object(rt.os, "pids_of", return_value=running):
            opened = attach(rt, req)
        next(c for c in CHILDREN if c.pid == opened["pid"]).kill()
        return opened

    def test_capture_alone_gates_and_the_debugger_takes_the_game_itself(self) -> None:
        off = self._rt("extraction, analysis")  # analysis on, the dynamic arm off
        for tool in TOOLS:
            with self.assertRaises(ViwoError) as err:
                attach(off, AttachRequest(self.unity, self.ws, "g-exe", tool, confirm=True))
            self.assertEqual(err.exception.code, "refused", tool)
        rt = self._rt("capture")  # no analysis needed
        self.assertEqual([t["id"] for t in attach_for(rt, "native_binary")], list(TOOLS))
        static = {h["id"] for h in handoffs_for(self._rt("analysis, capture"), "native_binary")}
        self.assertFalse(static & set(TOOLS))  # static ANALYSIS never offers them
        with self.assertRaises(ViwoError) as err:  # not confirmed for this game yet
            attach(rt, AttachRequest(self.unity, self.ws, "g-exe"))
        self.assertEqual(err.exception.code, "needs_decision")
        before = tree_hashes(self.unity)
        launched, real = [], rt.os.process.launch
        rt.os.process.launch = lambda argv, *a, **k: (
            launched.append(list(argv)) or real(argv, *a, **k)
        )
        exe = str((self.unity / "G.exe").resolve())
        cases = (
            ([], 0, [exe], 0),
            ([4242], 0, ["-p", "4242"], 4242),
            ([1, 2], 99, ["-p", "99"], 99),
        )
        for running, pid, args, attached in cases:
            opened = self._open(rt, "x64dbg-gui", running, pid)
            self.assertEqual((launched[-1][1:], opened["attached"]), (args, attached), running)
        with self.assertRaises(ViwoError) as err:  # two processes run G.exe: which one?
            self._open(rt, "x64dbg-gui", [1, 2])
        self.assertEqual(err.exception.code, "needs_decision")
        self.assertIn("2 running processes named G.exe", err.exception.message)
        self._open(rt, "cheatengine-gui", [1, 2])  # its table finds the game by name itself
        table = self.ws / ".runtime" / "cheatengine-gui" / "g-exe" / "G.CT"
        self.assertIn('local name = "G.exe"', table.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "ws.debug-copy").exists())  # never a copy
        self.assertFalse((self.ws / ".analysis").exists())  # nothing of the static arm's
        self.assertEqual(tree_hashes(self.unity), before)

    def test_cli_and_api_reach_the_same_core(self) -> None:
        from tests.test_cli import run
        from viwo.api.app import App
        from viwo.api.handlers_capture import CAPTURE_GET, CAPTURE_POST

        ini, rt = str(self._ini("capture")), self._rt("capture")
        code, out, _ = run(["--ini", ini, "--json", "attach", str(self.unity)])
        self.assertEqual(code, 0)
        listed = json.loads(out)["data"]["targets"]
        self.assertEqual(listed, json.loads(json.dumps(listing(rt, self.unity))))
        self.assertTrue(listed and all(t["attach"] for t in listed))
        code, _, err = run(["--ini", ini, "attach", str(self.unity), "--target", "g-exe"])
        self.assertIn("--workspace", err)
        opened = {"label": "Continue in x64dbg", "pid": 7, "attached": 0, "warnings": ["w"]}
        with (
            mock.patch("viwo.core.capture.attach.attach", return_value=opened) as core,
            mock.patch("viwo.core.handoff.wait_for", return_value=True) as wait,
        ):
            argv = ["--ini", ini, "attach", str(self.unity), "--target", "g-exe", "--pid", "5"]
            code, _, err = run([*argv, "--workspace", str(self.ws), "--confirm"])
        self.assertEqual(code, 0, err)
        req = core.call_args.args[1]
        self.assertEqual((req.target_key, req.pid, req.confirm), ("g-exe", 5, True))
        wait.assert_called_once_with(7)  # the tool is ViWo's child: the CLI waits for it
        self.assertIn("[ATTACH:WARN] w", err)
        app = App(rt)
        app.set_workspace(self.ws)
        got = CAPTURE_GET["/api/runtime/attach"](app, {"gamePath": str(self.unity)})
        self.assertEqual((got["targets"], got["enabled"]), (listing(rt, self.unity), True))
        post, game = CAPTURE_POST["/api/runtime/attach"], str(self.unity)
        bad = (
            ({"gamePath": str(self.root / "nowhere"), "targetKey": "g-exe"}, "not_found"),
            ({"gamePath": game}, "invalid_request"),
            ({"gamePath": game, "targetKey": "g-exe", "pid": "x"}, "invalid_request"),
        )
        for body, code in bad:
            self.assertEqual(post(app, body)["code"], code, body)
        body = {"gamePath": game, "targetKey": "g-exe", "tool": "cheatengine-gui", "confirm": True}
        with mock.patch.object(rt.os, "pids_of", return_value=[]):
            answer = post(app, body)
        next(c for c in CHILDREN if c.pid == answer["pid"]).kill()
        self.assertEqual((answer["success"], answer["handoff"]), (True, "cheatengine-gui"))


if __name__ == "__main__":
    unittest.main()
