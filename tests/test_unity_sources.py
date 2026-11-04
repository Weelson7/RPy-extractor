"""L3: where the Unity exporters look and what they say: containers by name or by signature
(a locked file is skipped, never fatal), the game's own cache folders from app.info (and none
when app.info says nothing), the source map follows an object to its file on disk, and the
AssetStudioModCLI spare names a missing tool and a failed run."""

from __future__ import annotations

import builtins
import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.contracts.types import OutcomeKind
from viwo.plugins.unity import exporters


class ContainerTests(unittest.TestCase):
    def test_names_signatures_and_a_locked_file(self) -> None:
        rng = random.Random(5)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            want = set()
            for i in range(20):
                kind = rng.choice(["name", "signature", "plain", "locked"])
                if kind == "name":
                    path = root / rng.choice(
                        [f"sharedassets{i}.assets", f"level{i}", f"b{i}.bundle"]
                    )
                    path.write_bytes(rng.randbytes(50))
                    want.add(path)
                elif kind == "signature":  # a custom header before the Unity signature
                    path = root / f"blob{i}.dat"
                    path.write_bytes(rng.randbytes(rng.randint(0, 3000)) + b"UnityFS" + bytes(20))
                    want.add(path)
                else:
                    path = root / f"{kind}{i}.dat"
                    path.write_bytes(b"\0" * 100)
            real = builtins.open

            def held(path, *a, **k):
                if Path(path).name.startswith("locked"):
                    raise PermissionError(13, "held by an antivirus")
                return real(path, *a, **k)

            with mock.patch.object(builtins, "open", held):
                found = set(exporters.unity_containers(root))
            self.assertEqual(found, want)
            self.assertEqual(exporters.unity_containers(root / "nowhere"), [])

    def test_cache_folders_come_from_app_info_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, home = Path(tmp) / "game", Path(tmp) / "home"
            (root / "Game_Data").mkdir(parents=True)
            with mock.patch.object(exporters.Path, "home", return_value=home):
                self.assertEqual(exporters.cache_roots(root), [])  # no app.info
                (root / "Game_Data" / "app.info").write_text("TVGS\n\n")
                self.assertEqual(exporters.cache_roots(root), [])  # no product line
                (root / "Game_Data" / "app.info").write_text("TVGS\nSchedule I\n")
                local = home / "AppData" / "LocalLow" / "TVGS" / "Schedule I"
                self.assertEqual(exporters.cache_roots(root), [])  # nothing there yet
                local.mkdir(parents=True)
                self.assertEqual(exporters.cache_roots(root), [local])

    def test_the_source_map_follows_an_object_to_its_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Data").mkdir()
            disk = root / "Data" / "sharedassets0.assets"
            disk.write_bytes(b"x")

            class Environment:
                pass

            bundle = SimpleNamespace(name=str(disk), parent=Environment())
            inner = SimpleNamespace(name="CAB-123", parent=bundle)  # a file inside a bundle
            obj = SimpleNamespace(assets_file=SimpleNamespace(name="CAB-123/x", parent=inner))
            self.assertEqual(exporters.container_of(obj, [disk], root), "Data/sharedassets0.assets")
            self.assertIsNone(exporters.container_of(SimpleNamespace(), [disk], root))


class ExportOptionTests(unittest.TestCase):
    def test_extension_filter_cache_option_and_cancel(self) -> None:
        from tests.test_unity import fake_unitypy, make_unity_game

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = make_unity_game(root)

            def ctx(name, exts=None, cancelled=False, cache=False):
                (root / name).mkdir()
                return SimpleNamespace(
                    game_root=game,
                    staging=root / name,
                    selected_exts=exts,
                    options={"include_cache": "true" if cache else "false"},
                    cancel=SimpleNamespace(cancelled=cancelled),
                    log=lambda *a, **k: None,
                )

            with mock.patch.dict(sys.modules, {"UnityPy": fake_unitypy()}):
                everything = exporters.UnityPyExporter().export(ctx("all"))
                only = exporters.UnityPyExporter().export(ctx("png", exts=frozenset({".png"})))
                stopped = exporters.UnityPyExporter().export(ctx("stop", cancelled=True))
                with mock.patch.object(exporters, "cache_roots", return_value=[]) as cache:
                    exporters.UnityPyExporter().export(ctx("cache", cache=True))
            cache.assert_called_once_with(game)  # the cache is read only when asked for
            self.assertEqual(stopped.files, 0)
            self.assertLess(only.files, everything.files)  # the other kinds were not written
            written = {p.suffix for p in (root / "png").rglob("*") if p.is_file()}
            self.assertLessEqual(written - {".json"}, {".png"})  # only the selected extension


class SpareTests(unittest.TestCase):
    def test_assetstudio_names_a_missing_tool_and_a_failed_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            tool = SimpleNamespace(argv_prefix=("AssetStudioModCLI",))
            for ok in (True, False):
                result = SimpleNamespace(ok=ok, stderr="bad bundle", stdout="")
                ctx = SimpleNamespace(
                    os=SimpleNamespace(
                        tools=SimpleNamespace(locate=lambda spec: tool),
                        process=SimpleNamespace(run=lambda argv, timeout, cancel, r=result: r),
                    ),
                    game_root=staging,
                    staging=staging,
                    cancel=None,
                    options={"meshes": "false"},
                )
                out = exporters.AssetStudioModCli().export(ctx)
                self.assertEqual(out.kind, OutcomeKind.OK if ok else OutcomeKind.FAILED)
            argv = exporters.AssetStudioModCli.argv(ctx, tool)
            self.assertNotIn("mesh", argv[argv.index("-t") + 1])  # meshes off: not asked for
            ctx.os.tools.locate = lambda spec: None
            self.assertEqual(
                exporters.AssetStudioModCli().export(ctx).kind, OutcomeKind.UNAVAILABLE
            )
            with mock.patch.dict(sys.modules, {"UnityPy": None}):
                self.assertEqual(
                    exporters.UnityPyExporter().export(ctx).kind, OutcomeKind.UNAVAILABLE
                )


if __name__ == "__main__":
    unittest.main()
