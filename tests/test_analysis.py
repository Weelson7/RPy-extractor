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

from tests.helpers import cleanup, homes, runtime, tree_hashes
from viwo.contracts import ViwoError
from viwo.core.analysis import (
    AnalysisRequest,
    analyze,
    extras_for,
    ghidra,
    open_in,
    slot_for,
    targets_for,
)
from viwo.os import select_os

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
FAKE_ILSPY = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
out, dll = Path(args[args.index("-o") + 1]), Path(args[-1])
assert "-p" in args and dll.read_bytes().startswith(b"MZ"), args
out.mkdir(parents=True, exist_ok=True)
(out / "Game.cs").write_text("class Game {{}}")
(out / "Game.csproj").write_text("<Project/>")
"""
FAKE_CPP2IL = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
game, out = Path(args[args.index("--game-path") + 1]), Path(args[args.index("--output-to") + 1])
assert (game / "GameAssembly.dll").is_file() and (game / "G.exe").is_file(), list(game.iterdir())
assert (game / "G_Data" / "il2cpp_data" / "Metadata" / "global-metadata.dat").is_file()
out.mkdir(parents=True, exist_ok=True)
(out / "Assembly-CSharp.dll").write_bytes(b"MZ")
print("[Info] [Program] Done.")
"""
FAKE_DIEC = """#!{python}
import json, sys
from pathlib import Path
args = sys.argv[1:]
assert args[:2] == ["-j", "-d"] and Path(args[2]).read_bytes().startswith(b"MZ"), args
print(json.dumps({{"detects": [{{"filetype": "PE64", "parentfilepart": "Header", "values": [
    {{"type": "compiler", "name": "MSVC", "string": "Compiler: MSVC(19)"}},
    {{"type": "protector", "name": "Themida", "string": "Protector: Themida(3.x)"}}]}}]}}))
"""
FAKE_UNLUAC = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
out, chunk = Path(args[args.index("--output") + 1]), Path(args[-1])
assert chunk.read_bytes().startswith(b"\\x1bLua"), args
out.write_text("-- decompiled\\nprint('hi')\\n")
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
    (unity / "scripts").mkdir()
    (unity / "scripts" / "init.luac").write_bytes(b"\x1bLua\x51\0\1\4\4\4\\8\0")
    unreal = root / "ue-game"
    (unreal / "Foo" / "Binaries" / "Win64").mkdir(parents=True)
    (unreal / "Foo" / "Binaries" / "Win64" / "Foo-Win64-Shipping.exe").write_bytes(
        b"MZ" + b"\0" * 8
    )
    (unreal / "Foo" / "Content" / "Paks").mkdir(parents=True)
    (unreal / "Foo" / "Content" / "Paks" / "Foo.pak").write_bytes(b"\0" * 8)
    return unity, unreal


class TableNameTests(unittest.TestCase):
    def test_any_executable_name_round_trips_through_the_table(self) -> None:
        import random
        import re
        from xml.etree import ElementTree

        from viwo.core.capture.handoffs import TABLE, table_name

        rng = random.Random(4)
        alphabet = "ab &<>\"'\\é漢.-_"
        for _ in range(300):
            name = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 12))) + ".exe"
            script = (
                ElementTree.fromstring(TABLE.format(name=table_name(name))).find("LuaScript").text
            )
            literal = re.search(r'local name = "((?:[^"\\]|\\.)*)"', script).group(1)
            self.assertEqual(re.sub(r"\\(.)", r"\1", literal), name)


class CopyInputsTests(unittest.TestCase):
    def test_a_copied_binary_gets_a_name_a_tool_can_take(self) -> None:
        from viwo.contracts.analysis import AnalysisTarget
        from viwo.core.analysis import _copy_inputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "g").mkdir()
            names = ["Void's Cave.exe", "a b&c.exe", "fine.exe", "fine.exe"]  # last two collide
            paths = []
            for i, n in enumerate(names):
                sub = root / "g" / str(i)
                sub.mkdir()
                (sub / n).write_bytes(b"MZ")
                paths.append(sub / n)
            target = AnalysisTarget("k", "native_binary", tuple(paths), "owner")
            copied = _copy_inputs(target, root / "scratch")
            out = [p.name for p in copied.paths]
            self.assertEqual(out, ["Void_s_Cave.exe", "a_b_c.exe", "fine.exe", "3-fine.exe"])
            for name in out:
                self.assertRegex(name, r"^[A-Za-z0-9._-]+$")  # Ghidra-safe
                self.assertTrue((root / "scratch" / "input" / name).read_bytes() == b"MZ")


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
                    "lua-bytecode": "script_vm",
                },
            )
            self.assertEqual(len(found["gameassembly"].paths), 3)  # dll, metadata, the exe
            self.assertNotIn("unitycrashhandler64-exe", found)
            keys = {t.key: t for t in targets_for(rt, unreal)}
            self.assertEqual(keys["shipping-exe"].owner, "unreal")
            self.assertEqual(keys["shipping-exe"].paths[0].name, "Foo-Win64-Shipping.exe")


class _AnalysisFixture(unittest.TestCase):
    """A Unity game and fake analyzers (Ghidra, ILSpy, Cpp2IL, unluac, DIE)."""

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
        ilspy = script(self.root / "ilspy", "ilspycmd", FAKE_ILSPY.format(python=sys.executable))
        cpp2il = script(self.root / "cpp2il", "Cpp2IL", FAKE_CPP2IL.format(python=sys.executable))
        unluac = script(self.root / "unluac", "unluac", FAKE_UNLUAC.format(python=sys.executable))
        diec = script(self.root / "die", "diec", FAKE_DIEC.format(python=sys.executable))
        ini = "[startup]\nfeatures = extraction, analysis\n[plugins]\nunity = on\n"
        ini += f"[tools]\nghidra = {self.headless}\njdk = {java}\ndotnet = {java}\n"
        ini += f"ilspycmd = {ilspy}\ncpp2il = {cpp2il}\nunluac = {unluac}\ndie = {diec}\n"
        self.rt = runtime(self.root, ini)
        self.ws = self.root / "ws"

    def tearDown(self) -> None:
        cleanup(self._tmp, 30)  # the killed GUI tools (and a scanning antivirus) let go late


class AnalyzeTests(_AnalysisFixture):
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

    def test_managed_and_script_analyzers(self) -> None:
        runs = (
            ("assembly-csharp", "ilspycmd", "Game.cs"),
            ("gameassembly", "cpp2il", "Assembly-CSharp.dll"),
            ("lua-bytecode", "unluac", "init.lua"),
        )
        for key, backend, artifact in runs:
            report = analyze(self.rt, AnalysisRequest(self.unity, self.ws, key))
            self.assertEqual(report["backend"], backend, key)
            self.assertIn(artifact, report["artifacts"], key)
            self.assertTrue((self.ws / ".analysis" / backend / key / "record.json").is_file())

    def test_protector_identification_as_a_second_analyzer(self) -> None:
        extras = extras_for(self.rt, "native_binary")
        self.assertEqual(
            [(x["slot"], x["backend"]) for x in extras], [("analysis.protector", "die")]
        )
        req = AnalysisRequest(self.unity, self.ws, "g-exe", slot="analysis.protector")
        report = analyze(self.rt, req)
        self.assertEqual(report["backend"], "die")
        self.assertEqual(set(report["artifacts"]), {"identify.json", "identify.txt"})
        self.assertEqual(report["notes"], ["Protector: Themida(3.x)"])
        with self.assertRaises(ViwoError) as err:  # unluac does not take a native binary
            analyze(self.rt, AnalysisRequest(self.unity, self.ws, "g-exe", slot="analysis.script"))
        self.assertEqual(err.exception.code, "unavailable")

    def test_engine_plugin_analyzers_rpyc_and_gdc(self) -> None:
        rpyc = """#!{python}
import sys
from pathlib import Path
folder = Path(sys.argv[-1])
assert "--clobber" in sys.argv and folder.is_dir(), sys.argv
for f in folder.glob("*.rpyc"):
    f.with_suffix(".rpy").write_text("label start:")
"""
        gdc = """#!{python}
import sys
from pathlib import Path
pairs = [a.split("=", 1) for a in sys.argv[1:] if "=" in a]
out = Path(dict(pairs)["--output"])
assert dict(pairs)["--bytecode"] == "4.3.0", sys.argv
for f in [Path(v) for k, v in pairs if k == "--decompile"]:
    (out / f.with_suffix(".gd").name).write_text("extends Node")
"""
        game = self.root / "vn"
        (game / "game").mkdir(parents=True)
        (game / "game" / "script.rpyc").write_bytes(b"RENPY RPC2")
        (game / "game" / "main.gdc").write_bytes(b"GDSC")
        (game / "vn.exe").write_bytes(b"MZ ... 4.3.0.stable.official ...")
        unrpyc = script(self.root / "unrpyc", "unrpyc", rpyc.format(python=sys.executable))
        gdre = script(self.root / "gdre", "gdre_tools", gdc.format(python=sys.executable))
        ini = "[startup]\nfeatures = extraction, analysis\n[plugins]\nrenpy = on\ngodot = on\n"
        rt = runtime(
            _folder(self.root / "eng"), ini + f"[tools]\nunrpyc = {unrpyc}\ngdre = {gdre}\n"
        )
        for key, backend, artifact in (
            ("rpyc", "unrpyc-analyze", "script.rpy"),
            ("gdscript", "gdre-decompile", "main.gd"),
        ):
            report = analyze(rt, AnalysisRequest(game, self.ws, key))
            self.assertEqual((report["backend"], report["artifacts"]), (backend, [artifact]), key)

    def test_gui_prompts_pre_answered_other_preferences_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, homes(tmp)):
            prefs = select_os().config_home() / "ghidra" / "ghidra_12.2_PUBLIC" / "preferences"
            prefs.parent.mkdir(parents=True)
            prefs.write_text("Theme=x\nSHOW_TIPS=true\n", encoding="utf-8")
            for _ in range(2):  # idempotent: a second handoff changes nothing
                self.assertEqual(ghidra.quiet_gui(select_os(), Path("/opt/ghidra_12.2_PUBLIC")), "")
            lines = prefs.read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                lines, ["Theme=x", "SHOW_TIPS=true", "USER_AGREEMENT=ACCEPT"]
            )  # the user's choice kept

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
            open_in(self.rt, AnalysisRequest(self.unity, self.ws, "g-exe"))
        self.assertIn("run the analysis first", err.exception.message)


class AnalysisApiTests(_AnalysisFixture):
    def test_the_api_answers_what_the_core_answers(self) -> None:
        """ANALYSIS over HTTP handlers: the targets are the core's, each with its bound
        analyzer; a run is a job that writes what analyze() writes; every bad request is named."""
        from viwo.api.app import App
        from viwo.api.handlers_analysis import ANALYSIS_GET, ANALYSIS_POST

        app = App(self.rt)
        app.set_workspace(self.ws)
        listed = ANALYSIS_GET["/api/analysis/targets"](app, {"gamePath": str(self.unity)})
        self.assertTrue(listed["success"] and listed["enabled"])
        core = {t.key: t.kind for t in targets_for(self.rt, self.unity)}
        self.assertEqual({t["key"]: t["kind"] for t in listed["targets"]}, core)
        for t in listed["targets"]:
            binding = self.rt.bindings.get(slot_for(t["kind"]))
            self.assertEqual(t["analyzer"], binding.main if binding and binding.bound else "")
        run = ANALYSIS_POST["/api/analysis/run"]
        for key in ("g-exe", "assembly-csharp", "lua-bytecode"):
            done = run(app, {"gamePath": str(self.unity), "targetKey": key})
            self.assertTrue(done["success"] and done["jobId"], done)
            self.assertTrue(
                (self.ws / ".analysis" / done["backend"] / key / "record.json").is_file()
            )
        bad = (
            ({"gamePath": str(self.root / "nowhere"), "targetKey": "g-exe"}, "not_found"),
            ({"gamePath": str(self.unity)}, "invalid_request"),
        )
        for body, code in bad:
            for route in ("/api/analysis/run", "/api/analysis/open"):
                self.assertEqual(ANALYSIS_POST[route](app, body)["code"], code, (route, body))
        self.assertEqual(ANALYSIS_GET["/api/analysis/targets"](app, {})["code"], "not_found")
        opened = ANALYSIS_POST["/api/analysis/open"](
            app, {"gamePath": str(self.unity), "targetKey": "g-exe"}
        )
        from viwo.os._shared import CHILDREN

        next(c for c in CHILDREN if c.pid == opened["pid"]).kill()
        self.assertEqual(opened["handoff"], "ghidra-gui")


if __name__ == "__main__":
    unittest.main()
