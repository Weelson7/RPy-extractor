"""L3: D2 runtime agents: the UE4SS agent installs into a patched copy (console off, bundled
mods off, the ViWo mod on), a fake game that writes the mappings is stopped once the agent is
finished, outputs land in the workspace, the game folder is only read; Mono Unity is refused."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from tests.test_capture import script
from viwo.contracts import ViwoError
from viwo.core.capture.agents import AgentRequest, run_agent

FAKE_GAME = """#!{python}
import re, sys, time
from pathlib import Path
here = Path.cwd()  # the runner starts the copy in its own folder
lua = (here / "Mods" / "ViwoDump" / "Scripts" / "main.lua").read_text()
assert "-windowed" in sys.argv, sys.argv
(here / "Mappings.usmap").write_bytes(b"\\xc4\\x30usmap")
(here / "UE4SS_ObjectDump.txt").write_text("[000] Class /Script/CoreUObject.Object")
done = re.search(r'io.open\\("([^"]+)"', lua).group(1)
Path(done).write_text("done")
time.sleep(60)
"""


def unreal_game(root: Path) -> tuple[Path, Path]:
    game = root / "game"
    win64 = game / "Foo" / "Binaries" / "Win64"
    win64.mkdir(parents=True)
    (game / "Foo" / "Content" / "Paks").mkdir(parents=True)
    (game / "Foo" / "Content" / "Paks" / "Foo-Windows.pak").write_bytes(b"\0" * 64)
    exe = script(win64, "Foo-Win64-Shipping", FAKE_GAME.format(python=sys.executable))
    return game, exe


def ue4ss_tool(root: Path) -> Path:
    tool = root / "ue4ss"
    (tool / "Mods" / "Keybinds").mkdir(parents=True)
    (tool / "UE4SS.dll").write_bytes(b"MZ")
    (tool / "dwmapi.dll").write_bytes(b"MZ")
    (tool / "UE4SS-settings.ini").write_text(
        "GuiConsoleEnabled = 1\nGuiConsoleVisible = 1\nConsoleEnabled = 1\n"
    )
    (tool / "Mods" / "mods.txt").write_text("CheatManagerEnablerMod : 1\nKeybinds : 1\n")
    return tool / "UE4SS.dll"


class AgentTests(unittest.TestCase):
    def test_ue4ss_in_a_patched_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, exe = unreal_game(root)
            before = tree_hashes(game)
            ini = "[startup]\nfeatures = extraction, capture\n[plugins]\nunreal = on\n"
            rt = runtime(root, ini + f"[tools]\nue4ss = {ue4ss_tool(root)}\n")
            report = run_agent(rt, AgentRequest(game, exe, root / "ws", timeout=60))
            self.assertTrue(report["finished"])
            self.assertEqual(sorted(report["files"]), ["Mappings.usmap", "UE4SS_ObjectDump.txt"])
            win64 = Path(report["copy"]) / "Foo" / "Binaries" / "Win64"
            settings = (win64 / "UE4SS-settings.ini").read_text()
            self.assertIn("GuiConsoleEnabled = 0", settings)
            mods = (win64 / "Mods" / "mods.txt").read_text()
            self.assertIn("Keybinds : 0", mods)
            self.assertIn("ViwoDump : 1", mods)
            self.assertEqual(tree_hashes(game), before)  # the game folder was only read

    def test_mono_unity_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "mono"
            (game / "G_Data" / "Managed").mkdir(parents=True)
            (game / "G_Data" / "Managed" / "Assembly-CSharp.dll").write_bytes(b"MZ")
            (game / "G.exe").write_bytes(b"MZ")
            (game / "UnityPlayer.dll").write_bytes(b"MZ")
            bep = root / "bep"
            bep.mkdir()
            (bep / "winhttp.dll").write_bytes(b"MZ")
            ini = "[startup]\nfeatures = extraction, capture\n[plugins]\nunity = on\n"
            rt = runtime(root, ini + f"[tools]\nbepinex = {bep / 'winhttp.dll'}\n")
            with self.assertRaises(ViwoError) as err:
                run_agent(rt, AgentRequest(game, game / "G.exe", root / "ws", timeout=5))
            self.assertIn("Mono", err.exception.message)


if __name__ == "__main__":
    unittest.main()
