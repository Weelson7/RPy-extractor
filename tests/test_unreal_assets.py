"""L3: Unreal asset export (export.unreal) and the fixes it brought. The engine version comes from
any game's build string; the mappings are the user's, else the newest the RUNTIME agent left,
else one the game ships; every mode runs over every Paks folder with the version, mappings and
key, failures are counted and the missing mappings named; an empty tool path in the ini means
automatic; the dynamic arm makes a fresh folder a workspace an extraction can follow into, never
a folder with the user's files; retoc converts a container together with `global.utoc`; vgmstream
decodes a file without subsongs as one stream. Verified on real data: a UE5.1 game (the
UE4SS agent's mappings, 695 PNG, 122 models, 3 animations, 23 sounds, 513 packages as JSON)."""

from __future__ import annotations

import os
import random
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.contracts.types import OutcomeKind
from viwo.plugins.unreal import assets


def build_string(major: int, minor: int) -> bytes:
    return f"++UE{major}+Release-{major}.{minor}-CL-123".encode("utf-16-le")


class EngineTests(unittest.TestCase):
    def test_the_version_is_read_from_any_games_binaries(self) -> None:
        rng = random.Random(2)
        for _ in range(20):
            major = rng.choice([4, 5])
            minor = rng.randint(20, 27) if major == 4 else rng.randint(0, 7)
            with tempfile.TemporaryDirectory() as tmp:
                game = Path(tmp)
                (game / "G" / "Binaries" / "Win64").mkdir(parents=True)
                exe = game / "G" / "Binaries" / "Win64" / "G-Win64-Shipping.exe"
                exe.write_bytes(
                    rng.randbytes(500) + build_string(major, minor) + rng.randbytes(500)
                )
                (game / "Launcher.exe").write_bytes(b"MZ")  # small: read after the big one
                self.assertEqual(assets.engine(game), f"GAME_UE{major}_{minor}")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.exe").write_bytes(b"MZ no build string")
            self.assertEqual(assets.engine(Path(tmp)), "")


class MappingsTests(unittest.TestCase):
    def test_the_users_then_the_agents_newest_then_the_games(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws, game = root / "ws", root / "game"
            agent = ws / ".runtime" / "agent" / "ue4ss-agent"
            agent.mkdir(parents=True)
            game.mkdir()
            ctx = SimpleNamespace(options={}, workspace=ws, game_root=game)
            self.assertIsNone(assets.mappings(ctx))
            (game / "Shipped.usmap").write_bytes(b"x")
            self.assertEqual(assets.mappings(ctx).name, "Shipped.usmap")
            old, new = agent / "old" / "Mappings.usmap", agent / "Mappings.usmap"
            old.parent.mkdir()
            old.write_bytes(b"x")
            new.write_bytes(b"x")
            os.utime(old, (time.time() + 60, time.time() + 60))  # the newest wins
            self.assertEqual(assets.mappings(ctx), old)
            mine = root / "mine.usmap"
            mine.write_bytes(b"x")
            ctx.options = {"usmap": str(mine)}
            self.assertEqual(assets.mappings(ctx), mine)
            ctx.options, ctx.workspace = {"usmap": str(root / "gone.usmap")}, None
            self.assertEqual(assets.mappings(ctx).name, "Shipped.usmap")  # a missing one is ignored


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.game = self.root / "game"
        self.paks = self.game / "G" / "Content" / "Paks"
        self.paks.mkdir(parents=True)
        (self.paks / "G-Windows.pak").write_bytes(b"\0" * 64)
        exe = self.game / "G" / "Binaries" / "Win64" / "G-Win64-Shipping.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(build_string(5, 3))
        self.staging, self.calls = self.root / "out", []

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def ctx(self, run, options=None, located=True):
        tool = SimpleNamespace(argv_prefix=("uas",))
        host = SimpleNamespace(
            tools=SimpleNamespace(locate=lambda s: tool if located else None),
            process=SimpleNamespace(run=run),
        )
        return SimpleNamespace(
            os=host,
            game_root=self.game,
            staging=self.staging,
            scratch=self.root / "s",
            options=options or {},
            workspace=None,
            cancel=None,
            log=lambda *a, **k: None,
            tool_output=lambda stage, mask="": None,
        )

    def fake(self, failed_json: int = 0, needs: bool = True):
        def run(argv, cwd=None, timeout=None, cancel=None, on_line=None):
            self.calls.append(argv)
            mode, out = argv[2], Path(argv[argv.index("-o") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / ".uas-manifest.json").write_text("{}")
            if mode == "Textures":
                (out / "T_Wall.png").write_bytes(b"png")
            why = "could not load package" if needs else "bad data"
            text = "".join(f"[WRN] [FAILED]   G/P{i}.uasset: {why}\n" for i in range(failed_json))
            return SimpleNamespace(ok=True, stdout=text if mode == "Json" else "", stderr="")

        return run

    def test_every_mode_with_version_mappings_and_key_and_the_missing_mappings_named(self) -> None:
        with mock.patch.object(assets, "resolve_key", return_value=("ab" * 32, "")):
            out = assets.UasExport().export(self.ctx(self.fake(failed_json=7)))
        self.assertEqual((out.kind, out.files), (OutcomeKind.OK, 1))
        self.assertEqual([c[2] for c in self.calls], list(assets.MODES))
        for argv in self.calls:
            self.assertEqual(argv[argv.index("-g") + 1], "GAME_UE5_3")
            self.assertEqual(argv[argv.index("-a") + 1], "0x" + "ab" * 32)
            self.assertNotIn("-u", argv)
        self.assertIn("7 package(s) need the game's mappings", out.notes[0])
        self.assertEqual(
            sorted(p.name for p in self.staging.rglob("*")), ["T_Wall.png", "textures"]
        )

    def test_with_mappings_failures_are_only_counted(self) -> None:
        usmap = self.root / "Mappings.usmap"
        usmap.write_bytes(b"x")
        with mock.patch.object(assets, "resolve_key", return_value=("", "")):
            out = assets.UasExport().export(
                self.ctx(self.fake(2, needs=False), {"usmap": str(usmap)})
            )
        self.assertEqual(out.notes, ("2 package(s) could not be read",))
        self.assertTrue(all(c[c.index("-u") + 1] == str(usmap) for c in self.calls))
        self.assertTrue(all("-a" not in c for c in self.calls))

    def test_every_reason_not_to_run_is_said(self) -> None:
        self.assertEqual(
            assets.UasExport().export(self.ctx(None, located=False)).kind, OutcomeKind.UNAVAILABLE
        )
        with mock.patch.object(
            assets, "resolve_key", return_value=("", "encrypted: give the AES key")
        ):
            out = assets.UasExport().export(self.ctx(self.fake()))
        self.assertEqual(
            (out.kind, out.error), (OutcomeKind.NEEDS_KEY, "encrypted: give the AES key")
        )
        with mock.patch.object(assets, "engine", return_value=""):
            self.assertIn(
                "no engine version", assets.UasExport().export(self.ctx(self.fake())).error
            )
        broken = SimpleNamespace(
            ok=False, stdout="", stderr="Directory does not exist", returncode=1
        )
        with mock.patch.object(assets, "resolve_key", return_value=("", "")):
            out = assets.UasExport().export(self.ctx(lambda *a, **k: broken))
        self.assertEqual(
            (out.kind, out.error), (OutcomeKind.FAILED, "Textures: Directory does not exist")
        )
        (self.paks / "G-Windows.pak").unlink()
        self.assertIn("no .pak/.utoc", assets.UasExport().export(self.ctx(self.fake())).error)


class FixTests(unittest.TestCase):
    def test_an_empty_or_auto_tool_path_means_automatic(self) -> None:
        from viwo.core.wiring.ini import load_ini

        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "startup.ini"
            ini.write_text("[tools]\nue4ss =\nrepak = auto\nretoc = tools/retoc.exe\n")
            tools = load_ini(ini).tools
            self.assertEqual(set(tools), {"retoc"})
            self.assertEqual(Path(tools["retoc"]), (Path(tmp) / "tools" / "retoc.exe").resolve())

    def test_the_dynamic_arm_claims_a_fresh_folder_never_the_users(self) -> None:
        from viwo.contracts import workspace as ws
        from viwo.core.capture.runtime import runtime_dir
        from viwo.core.workspace import _has_content

        with tempfile.TemporaryDirectory() as tmp:
            fresh, mine = Path(tmp) / "fresh", Path(tmp) / "mine"
            runtime_dir(fresh, "agent")
            self.assertTrue(ws.has_marker(fresh))
            self.assertFalse(_has_content(fresh))  # .runtime alone is no extraction to replace
            mine.mkdir()
            (mine / "notes.txt").write_text("mine")
            runtime_dir(mine, "agent")
            self.assertFalse(ws.has_marker(mine))

    def test_a_container_converts_with_global_utoc_beside_it(self) -> None:
        from viwo.plugins.unreal.pak import RetocLegacy

        with tempfile.TemporaryDirectory() as tmp:
            paks = Path(tmp) / "Paks"
            paks.mkdir()
            for name in ("global.utoc", "global.ucas", "G.utoc", "G.ucas", "Other.utoc"):
                (paks / name).write_bytes(name.encode())
            ctx = SimpleNamespace(scratch=Path(tmp) / "scratch")
            self.assertEqual(
                RetocLegacy().input_for(paks / "global.utoc", ctx), paks / "global.utoc"
            )
            folder = RetocLegacy().input_for(paks / "G.utoc", ctx)
            self.assertEqual(
                sorted(p.name for p in folder.iterdir()),
                ["G.ucas", "G.utoc", "global.ucas", "global.utoc"],
            )
            self.assertEqual((folder / "G.ucas").read_bytes(), b"G.ucas")
            with mock.patch("os.link", side_effect=OSError("other volume")):
                again = RetocLegacy().input_for(paks / "G.utoc", ctx)
            self.assertEqual((again / "global.utoc").read_bytes(), b"global.utoc")  # copied
            (paks / "global.utoc").unlink()
            self.assertEqual(RetocLegacy().input_for(paks / "G.utoc", ctx), paks / "G.utoc")

    def test_the_agent_never_copies_a_folder_into_itself(self) -> None:
        from viwo.contracts import ViwoError
        from viwo.plugins.unreal.agent import Ue4ssAgent

        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy"
            win64 = copy / "G" / "Binaries" / "Win64"
            win64.mkdir(parents=True)
            exe = win64 / "G-Win64-Shipping.exe"
            exe.write_bytes(b"MZ")
            located = SimpleNamespace(
                path=str(Path(tmp) / "UE4SS.dll")
            )  # its folder holds the copy
            ctx = SimpleNamespace(
                os=SimpleNamespace(tools=SimpleNamespace(locate=lambda s: located))
            )
            with self.assertRaises(ViwoError) as err:
                Ue4ssAgent().install(copy, exe, ctx)
            self.assertIn("holds the copy", err.exception.message)

    def test_a_file_without_subsongs_is_decoded_as_one_stream(self) -> None:
        from viwo.core.decode import VgmstreamCli

        with tempfile.TemporaryDirectory() as tmp:
            dest, src = Path(tmp) / "out", Path(tmp) / "ambience.binka"
            dest.mkdir()
            src.write_bytes(b"UEBA")
            seen = []

            def run(argv, timeout=None, cancel=None):
                seen.append(argv)
                if "-S" not in argv:  # all-subsongs writes nothing for this file
                    Path(argv[argv.index("-o") + 1]).write_bytes(b"RIFF")
                return SimpleNamespace(ok=True, stdout="", stderr="")

            tool = SimpleNamespace(argv_prefix=("vgmstream-cli",))
            ctx = SimpleNamespace(
                os=SimpleNamespace(
                    tools=SimpleNamespace(locate=lambda s: tool), process=SimpleNamespace(run=run)
                ),
                cancel=None,
            )
            argv = VgmstreamCli().argv(Path("C:/game/what?.bank"), dest)
            self.assertEqual(
                Path(argv[argv.index("-o") + 1]).name, "what__?s.wav"
            )  # the stem, not ?f
            out = VgmstreamCli().decode(src, dest, ctx)
            self.assertEqual((out.kind, out.files), (OutcomeKind.OK, 1))
            self.assertEqual(len(seen), 2)
            self.assertTrue((dest / "ambience.wav").is_file())


if __name__ == "__main__":
    unittest.main()
