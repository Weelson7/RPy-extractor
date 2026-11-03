"""L3: static analysis arm (doc 6, A1): targets from the plugins, one Ghidra headless run with a
fake analyzeHeadless, the record, the feature switch, and the GUI handoff as a tracked child."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import runtime, tree_hashes
from viwo.contracts import ViwoError
from viwo.core.analysis import AnalysisRequest, analyze, ghidra, open_in, targets_for

FAKE_HEADLESS = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
project, name = Path(args[0]), args[1]
binary = Path(args[args.index("-import") + 1])
out = Path(args[args.index("-postScript") + 2])
assert args[args.index("-postScript") + 1] == "ViwoExport.java"
assert binary.read_bytes().startswith(b"MZ"), "the analyzer must get the copied binary"
project.mkdir(parents=True, exist_ok=True)
(project / f"{{name}}.gpr").write_text("project")
out.mkdir(parents=True, exist_ok=True)
(out / "functions.csv").write_text("address,name,size\\n00401000,main,12\\n")
(out / "decompiled.c").write_text("// 00401000 main\\nint main(void) {{ return 0; }}\\n")
print("INFO  Analysis succeeded")
print("ViWo export done")
"""
FAKE_GUI = """#!{python}
import time
time.sleep(30)
"""


def _folder(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def script(folder: Path, name: str, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.py"
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    if sys.platform == "win32":
        wrapper = folder / f"{name}.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{path}" %*\r\n')
        return wrapper
    return path


def make_games(root: Path) -> tuple[Path, Path]:
    unity = root / "unity-game"
    (unity / "G_Data" / "Managed").mkdir(parents=True)
    (unity / "G_Data" / "il2cpp_data" / "Metadata").mkdir(parents=True)
    (unity / "G.exe").write_bytes(b"MZ" + b"\0" * 64)
    (unity / "UnityCrashHandler64.exe").write_bytes(b"MZ")
    (unity / "GameAssembly.dll").write_bytes(b"MZ" + b"\0" * 32)
    (unity / "G_Data" / "il2cpp_data" / "Metadata" / "global-metadata.dat").write_bytes(b"AF1B")
    (unity / "G_Data" / "Managed" / "Assembly-CSharp.dll").write_bytes(b"MZ")
    unreal = root / "ue-game"
    (unreal / "Foo" / "Binaries" / "Win64").mkdir(parents=True)
    (unreal / "Foo" / "Binaries" / "Win64" / "Foo-Win64-Shipping.exe").write_bytes(
        b"MZ" + b"\0" * 8
    )
    (unreal / "Foo" / "Content" / "Paks").mkdir(parents=True)
    (unreal / "Foo" / "Content" / "Paks" / "Foo.pak").write_bytes(b"\0" * 8)
    return unity, unreal


class TargetTests(unittest.TestCase):
    def test_plugins_propose_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unity, unreal = make_games(root)
            rt = runtime(root, "[plugins]\nunity = on\nunreal = on\n")
            found = {t.key: t for t in targets_for(rt, unity)}
            self.assertEqual(
                {k: v.kind for k, v in found.items()},
                {
                    "g-exe": "native_binary",
                    "gameassembly": "il2cpp",
                    "assembly-csharp": "dotnet_assembly",
                },
            )
            self.assertEqual(len(found["gameassembly"].paths), 2)  # dll + metadata companion
            self.assertNotIn("unitycrashhandler64-exe", found)
            keys = {t.key: t for t in targets_for(rt, unreal)}
            self.assertEqual(keys["shipping-exe"].owner, "unreal")
            self.assertEqual(keys["shipping-exe"].paths[0].name, "Foo-Win64-Shipping.exe")


class AnalyzeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.unity, _ = make_games(self.root)
        tools = self.root / "ghidra" / "support"
        self.headless = script(
            tools, "analyzeHeadless", FAKE_HEADLESS.format(python=sys.executable)
        )
        jar = tools.parent / "Ghidra" / "Framework" / "Utility" / "lib" / "Utility.jar"
        jar.parent.mkdir(parents=True)
        jar.write_bytes(b"PK")
        self.gui = script(tools.parent, "ghidraRun", FAKE_GUI.format(python=sys.executable))
        java = script(self.root / "jdk" / "bin", "java", FAKE_GUI.format(python=sys.executable))
        ini = "[startup]\nfeatures = extraction, analysis\n[plugins]\nunity = on\n"
        ini += f"[tools]\nghidra = {self.headless}\njdk = {java}\n"
        self.rt = runtime(self.root, ini)
        self.ws = self.root / "ws"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_headless_run_writes_artifacts_and_record(self) -> None:
        before = tree_hashes(self.unity)
        events = []
        req = AnalysisRequest(self.unity, self.ws, "g-exe")
        report = analyze(self.rt, req, events.append)
        out = self.ws / ".analysis" / "ghidra-headless" / "g-exe"
        self.assertEqual(report["backend"], "ghidra-headless")
        self.assertEqual(set(report["artifacts"]), {"functions.csv", "decompiled.c"})
        gpr = self.ws.parent / "ws.ghidra" / "g-exe" / "viwo.gpr"
        self.assertTrue(gpr.is_file())  # kept beside the workspace for the handoff
        record = json.loads((out / "record.json").read_text())
        self.assertEqual(record["target"]["key"], "g-exe")
        self.assertIn("tools", record["context"])
        self.assertTrue(any("Analysis succeeded" in e.message for e in events))
        self.assertEqual(tree_hashes(self.unity), before)
        child = open_in(self.rt, req)
        self.assertEqual(child["handoff"], "ghidra-gui")
        from viwo.os._shared import CHILDREN

        tracked = next(c for c in CHILDREN if c.pid == child["pid"])
        self.assertTrue(tracked.alive())
        tracked.kill()
        for _ in range(50):
            if not tracked.alive():
                break
            time.sleep(0.1)
        self.assertFalse(tracked.alive())

    def test_gui_prompts_pre_answered_other_preferences_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"APPDATA": tmp}):
            prefs = Path(tmp) / "ghidra" / "ghidra_12.2_PUBLIC" / "preferences"
            prefs.parent.mkdir(parents=True)
            prefs.write_text("Theme=x\nSHOW_TIPS=true\n", encoding="utf-8")
            ghidra.quiet_gui(Path("/opt/ghidra_12.2_PUBLIC"))
            lines = prefs.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines, ["Theme=x", "USER_AGREEMENT=ACCEPT", "SHOW_TIPS=false"])

    def test_switch_off_unknown_target_and_handoff_without_project(self) -> None:
        with self.assertRaises(ViwoError) as err:
            analyze(
                runtime(_folder(self.root / "off"), "[plugins]\nunity = on\n"),
                AnalysisRequest(self.unity, self.ws, "g-exe"),
            )
        self.assertEqual(err.exception.code, "refused")
        with self.assertRaises(ViwoError) as err:
            analyze(self.rt, AnalysisRequest(self.unity, self.ws, "nope"))
        self.assertEqual(err.exception.code, "not_found")
        with self.assertRaises(ViwoError) as err:
            analyze(self.rt, AnalysisRequest(self.unity, self.ws, "gameassembly"))
        self.assertEqual(err.exception.code, "unavailable")  # no il2cpp slot in A1
        with self.assertRaises(ViwoError) as err:
            open_in(self.rt, AnalysisRequest(self.unity, self.ws, "g-exe"))
        self.assertIn("run the analysis first", err.exception.message)


if __name__ == "__main__":
    unittest.main()
