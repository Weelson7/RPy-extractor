"""L3: every analyzer and handoff backend, one property: with its tool missing it answers
UNAVAILABLE with the install hint; with the tool present but writing nothing (or timing out)
it answers a named failure, never "ok" with nothing; a handoff with its tool says how to start
it, or why it cannot."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime
from viwo.contracts.analysis import KINDS, AnalysisTarget, Analyzer, Handoff, LaunchSpec
from viwo.contracts.types import Outcome, OutcomeKind

PLUGINS = "generic unity godot unreal renpy".split()


def _ctx(root: Path, located: bool, timed_out: bool, os_id: str = "windows"):
    found = root / "tools" / "bin" / "tool.exe"
    found.parent.mkdir(parents=True, exist_ok=True)
    found.write_bytes(b"MZ")
    tool = SimpleNamespace(argv_prefix=(str(found),), path=str(found))
    result = SimpleNamespace(ok=False, timed_out=timed_out, stdout="", stderr="", returncode=1)
    staging = root / "staging"
    staging.mkdir(exist_ok=True)
    (root / "scratch").mkdir(exist_ok=True)  # the analysis flow makes it when it copies inputs
    host = SimpleNamespace(
        os_id=os_id,
        tools=SimpleNamespace(locate=lambda spec: tool if located else None),
        process=SimpleNamespace(run=lambda argv, **k: result),
        config_home=lambda: root / "cfg",
        data_home=lambda: root / "data",
    )
    return SimpleNamespace(
        os=host,
        options={},
        staging=staging,
        scratch=root / "scratch",
        cancel=None,
        game_root=root / "game",
        log=lambda *a, **k: None,
        tool_output=lambda *a, **k: None,
    )


def _target(root: Path, kind: str) -> AnalysisTarget:
    (root / "in").mkdir(exist_ok=True)
    paths = []
    for name in (
        "Game.exe",
        "GameAssembly.dll",
        "global-metadata.dat",
        "a.luac",
        "s.gdc",
        "s.rpyc",
    ):
        path = root / "in" / name
        path.write_bytes(b"MZ" + bytes(200) if name.endswith((".exe", ".dll")) else b"data")
        paths.append(path)
    return AnalysisTarget("t", kind, tuple(paths), "user", hints={})


class AnalyzerContractTests(unittest.TestCase):
    def test_every_analyzer_names_a_missing_tool_and_an_empty_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root, "[plugins]\n" + "".join(f"{p} = on\n" for p in PLUGINS))
            analyzers = [b for b in rt.backends.values() if isinstance(b, Analyzer)]
            self.assertGreaterEqual(len(analyzers), 8)
            for backend in analyzers:
                kind = backend.kinds[0] if backend.kinds else sorted(KINDS)[0]
                for located, timed_out in ((False, False), (True, False), (True, True)):
                    case = root / f"{backend.backend_id}-{located}-{timed_out}"
                    case.mkdir()
                    ctx = _ctx(case, located, timed_out)
                    ctx.options = {"bytecode": "4.3.0", "start": "0x1000", "find": "0x2000"}
                    out = backend.analyze(_target(case, kind), ctx)
                    self.assertIsInstance(out, Outcome, backend.backend_id)
                    self.assertNotEqual(
                        out.kind, OutcomeKind.OK, backend.backend_id
                    )  # nothing written
                    self.assertTrue(out.error, backend.backend_id)  # and it says why
                    if not located:
                        self.assertEqual(out.kind, OutcomeKind.UNAVAILABLE, backend.backend_id)

    def test_every_handoff_names_a_missing_tool_or_says_how_to_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root, "[plugins]\n" + "".join(f"{p} = on\n" for p in PLUGINS))
            handoffs = [b for b in rt.backends.values() if isinstance(b, Handoff)]
            self.assertGreaterEqual(len(handoffs), 3)
            for backend in handoffs:
                kind = backend.accepts[0] if backend.accepts else "native_binary"
                for located in (False, True):
                    case = root / f"{backend.backend_id}-{located}"
                    case.mkdir()
                    got = backend.prepare(_target(case, kind), _ctx(case, located, False))
                    if not located:
                        self.assertEqual(got.kind, OutcomeKind.UNAVAILABLE, backend.backend_id)
                        self.assertTrue(got.error)
                    elif isinstance(got, Outcome):  # e.g. no project yet: a reason, not a crash
                        self.assertTrue(got.error, backend.backend_id)
                    else:
                        self.assertIsInstance(got, LaunchSpec)
                        self.assertTrue(got.argv, backend.backend_id)


class FirstRunAnswerTests(unittest.TestCase):
    """Minimal prompts (owner's rule): the GUI tools' first-run dialogs are pre-answered off
    screen; every answer lands once, a value the user set is kept, a second run changes
    nothing, and a config that cannot be written is said."""

    def test_x64dbg_and_ghidra_answers_keep_the_users_own(self) -> None:
        import random

        from viwo.core.analysis.ghidra import ANSWERS, quiet_gui
        from viwo.core.analysis.handoffs import quiet_x64dbg

        rng = random.Random(4)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(30):
                debugger = root / f"x{case}" / "x64dbg.exe"
                debugger.parent.mkdir()
                lines = rng.sample(
                    ["[Engine]", "Foo=1", "[Gui]", "Theme=dark", "ReleaseNotesEpoch=5"],
                    rng.randint(0, 5),
                )
                if lines:
                    debugger.with_suffix(".ini").write_text("\n".join(lines) + "\n")
                quiet_x64dbg(debugger)
                once = debugger.with_suffix(".ini").read_text()
                quiet_x64dbg(debugger)
                self.assertEqual(debugger.with_suffix(".ini").read_text(), once)  # idempotent
                self.assertEqual(once.count("ReleaseNotesEpoch="), 1)
                for line in lines:
                    self.assertIn(line, once)  # nothing of the user's is lost or changed
                host = SimpleNamespace(config_home=lambda c=case: root / f"cfg{c}")
                pref = root / f"cfg{case}" / "ghidra" / "ghidra_11" / "preferences"
                mine = rng.sample(sorted(ANSWERS), rng.randint(0, len(ANSWERS)))
                if mine:
                    pref.parent.mkdir(parents=True)
                    pref.write_text("".join(f"{k}=mine\n" for k in mine))
                self.assertEqual(quiet_gui(host, Path("ghidra_11")), "")
                text = pref.read_text()
                for key in ANSWERS:
                    self.assertEqual(text.count(f"{key}="), 1)
                    self.assertEqual(f"{key}=mine" in text, key in mine)
            blocked = root / "blocked"
            blocked.write_text("a file where a folder should be")
            said = quiet_gui(SimpleNamespace(config_home=lambda: blocked), Path("g"))
            self.assertIn("not written", said)

    def test_cheat_engine_asks_the_registry_first_and_32_bit_games_get_x32dbg(self) -> None:
        import struct

        from viwo.core.analysis.handoffs import X64dbgGui, quiet_cheatengine

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for present in (0, 1):
                added = []

                def run(argv, timeout=None, present=present, added=added):
                    if argv[1] == "add":
                        added.append(argv[4])
                    return SimpleNamespace(returncode=0 if argv[1] == "query" and present else 1)

                home = root / f"ce{present}"
                (home / "autorun" / "ceshare").mkdir(parents=True)
                quiet_cheatengine(SimpleNamespace(process=SimpleNamespace(run=run)), home)
                self.assertEqual(added, [] if present else ["LuaScriptAction", "First Time User"])
                self.assertTrue((home / "autorun" / "ceshare" / "server.txt").is_file())
            game = root / "game32.exe"
            pe = (
                b"MZ" + bytes(0x3A) + struct.pack("<I", 0x40) + b"PE\0\0" + struct.pack("<H", 0x14C)
            )
            game.write_bytes(pe + bytes(400))
            tool = root / "x64dbg" / "release" / "x64" / "x64dbg.exe"
            tool.parent.mkdir(parents=True)
            tool.write_bytes(b"MZ")
            located = SimpleNamespace(argv_prefix=(str(tool),), path=str(tool))
            ctx = SimpleNamespace(
                os=SimpleNamespace(tools=SimpleNamespace(locate=lambda s: located))
            )
            target = AnalysisTarget("g", "native_binary", (game,), "user")
            missing = X64dbgGui().prepare(target, ctx)  # this x64dbg came without x32dbg
            self.assertEqual(missing.kind, OutcomeKind.UNAVAILABLE)
            self.assertIn("32-bit", missing.error)
            x32 = root / "x64dbg" / "release" / "x32" / "x32dbg.exe"
            x32.parent.mkdir()
            x32.write_bytes(b"MZ")
            spec = X64dbgGui().prepare(target, ctx)
            self.assertEqual(Path(spec.argv[0]), x32.resolve())  # a 32-bit game: x32dbg


if __name__ == "__main__":
    unittest.main()
