"""L3: Unity plugin. UnityPy is replaced by a fake module (no game data in the repo)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.plugins.unity import UnityPlugin
from viwo.plugins.unity.exporters import AssetStudioModCli


class _Image:
    def save(self, path) -> None:
        Path(path).write_bytes(b"PNG")


def _obj(kind: str, path_id: int, **fields):
    data = types.SimpleNamespace(**fields)
    return types.SimpleNamespace(
        type=types.SimpleNamespace(name=kind), path_id=path_id, parse_as_object=lambda: data
    )


def _broken():
    def boom():
        raise ValueError("corrupt object")

    return types.SimpleNamespace(
        type=types.SimpleNamespace(name="Texture2D"), path_id=9, parse_as_object=boom
    )


def fake_unitypy() -> types.ModuleType:
    objects = [
        _obj("Texture2D", 1, m_Name="hero", image=_Image()),
        _obj("Sprite", 2, m_Name="hero", image=_Image()),  # same name -> hero__1.png
        _obj("AudioClip", 3, m_Name="theme", samples={"theme.wav": b"RIFF"}),
        _obj("TextAsset", 4, m_Name="dialog", m_Script="hello"),
        _obj("Mesh", 5, m_Name="rock", export=lambda: "v 0 0 0\n"),
        _obj("MonoBehaviour", 6, m_Name="ignored"),
        _broken(),
    ]
    module = types.ModuleType("UnityPy")
    module.load = lambda *paths: types.SimpleNamespace(objects=objects)
    return module


class _Stored:
    """A UnityPy object's parsed data as the packer sees it: text or an image, saved back."""

    def __init__(self, kind: str):
        from PIL import Image

        self.kind, self.m_Script = kind, "old text"
        self.image = Image.new("RGBA", (2, 2), (1, 2, 3, 255))

    def set_image(self, img, target_format=None):
        self.image = img.copy()

    def save(self):
        self.saved = True


def fake_pack_unitypy(kinds: dict[int, str]) -> types.ModuleType:
    """UnityPy over one container whose objects keep what the packer writes into them."""
    stored = {pid: _Stored(kind) for pid, kind in kinds.items()}
    module = types.ModuleType("UnityPy")

    def load(path):
        objects = [
            types.SimpleNamespace(
                path_id=pid,
                type=types.SimpleNamespace(name=kinds[pid]),
                parse_as_object=lambda pid=pid: stored[pid],
            )
            for pid in kinds
        ]
        bundle = types.SimpleNamespace(save=lambda packer: b"UnityFS repacked")
        return types.SimpleNamespace(objects=objects, files={"f": bundle})

    module.load = load
    return module


class UnityPackTests(unittest.TestCase):
    def test_edits_written_back_verify_and_every_refusal_is_named(self) -> None:
        import random

        from PIL import Image

        from viwo.contracts.types import OutcomeKind
        from viwo.plugins.unity.pack import UnityPyPacker

        rng = random.Random(3)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            container = root / "data.unity3d"
            for _ in range(8):
                kinds = {pid: rng.choice(["TextAsset", "Texture2D"]) for pid in range(1, 6)}
                members = {}
                for pid in rng.sample(sorted(kinds), rng.randint(1, 5)):
                    src = root / f"edit{pid}"
                    if kinds[pid] == "TextAsset":
                        src.write_bytes(rng.randbytes(20).hex().encode())
                    else:
                        color = tuple(rng.randrange(256) for _ in range(3)) + (255,)
                        Image.new("RGBA", (3, 3), color).save(src, format="PNG")
                    members[str(pid)] = src
                container.write_bytes(b"UnityFS original")
                module = fake_pack_unitypy(kinds)
                with mock.patch.dict(sys.modules, {"UnityPy": module}):
                    out = UnityPyPacker().pack(container, members, None)
                    self.assertEqual((out.kind, out.files), (OutcomeKind.OK, len(members)))
                    self.assertEqual(container.read_bytes(), b"UnityFS repacked")
                    self.assertEqual(UnityPyPacker().verify(container, members, None), [])
                    other = root / "other.txt"
                    other.write_text("not what was written")
                    some = (
                        next(m for m in members if kinds[int(m)] == "TextAsset")
                        if any(kinds[int(m)] == "TextAsset" for m in members)
                        else None
                    )
                    if some:  # a member whose bytes differ is reported by verify
                        self.assertEqual(
                            UnityPyPacker().verify(container, {some: other}, None), [some]
                        )
            refusals = (
                ({1: "TextAsset"}, {"99": root / "edit1"}, "object 99 not found"),
                ({1: "Mesh"}, {"1": root / "edit1"}, "Mesh cannot be written back"),
            )
            for kinds, members, why in refusals:
                with mock.patch.dict(sys.modules, {"UnityPy": fake_pack_unitypy(kinds)}):
                    out = UnityPyPacker().pack(container, members, None)
                self.assertEqual(out.kind, OutcomeKind.FAILED)
                self.assertIn(why, out.error)
            with mock.patch.dict(sys.modules, {"UnityPy": None}):
                out = UnityPyPacker().pack(container, {}, None)
            self.assertEqual(out.kind, OutcomeKind.UNAVAILABLE)


def make_unity_game(root: Path) -> Path:
    game = root / "MyGame"
    (game / "MyGame_Data").mkdir(parents=True)
    (game / "UnityPlayer.dll").write_bytes(b"MZ")
    (game / "MyGame_Data" / "globalgamemanagers").write_bytes(b"\0" * 16)
    return game


class UnityTests(unittest.TestCase):
    def test_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = make_unity_game(Path(tmp))
            self.assertEqual(UnityPlugin().detect(FolderProbe(game)).confidence, 0.92)
            (game / "UnityPlayer.dll").unlink()
            (game / "MyGame_Data" / "globalgamemanagers").unlink()
            self.assertEqual(UnityPlugin().detect(FolderProbe(game)).confidence, 0.5)

    def test_export_into_extension_layout(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(sys.modules, {"UnityPy": fake_unitypy()}),
        ):
            root = Path(tmp)
            game = make_unity_game(root)
            rt = runtime(root, "[plugins]\nunity = on\n")
            self.assertEqual(rt.bindings["export.unity"].main, "unitypy")
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            files = tree_hashes(root / "ws", skip_reserved=True)
            for expected in (
                "png/hero.png",
                "png/hero__1.png",
                "wav/theme.wav",
                "txt/dialog.txt",
                "obj/rock.obj",
            ):
                self.assertIn(expected, files)
            run = result.runs[0]
            self.assertEqual((run.plugin_id, run.backend, run.exported), ("unity", "unitypy", 5))

    def test_meshes_option_off_skips_obj_everywhere(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(sys.modules, {"UnityPy": fake_unitypy()}),
        ):
            root = Path(tmp)
            game = make_unity_game(root)
            rt = runtime(root, "[plugins]\nunity = on\n")
            request = ExtractionRequest(
                str(game), str(root / "ws"), plugin_options={"unity": {"meshes": "off"}}
            )
            result = extract(rt, request, "j", lambda e: None, CancelToken())
            files = tree_hashes(root / "ws", skip_reserved=True)
            self.assertIn("png/hero.png", files)
            self.assertFalse([f for f in files if f.endswith(".obj")])
            self.assertEqual(result.runs[0].exported, 4)
            tool = types.SimpleNamespace(argv_prefix=("dotnet", "AssetStudioModCLI.dll"))
            on = types.SimpleNamespace(options={}, game_root=game, staging=root / "st")
            off = types.SimpleNamespace(options={"meshes": "0"}, game_root=game, staging=root)
            self.assertIn("tex2d,sprite,audio,textAsset,mesh", AssetStudioModCli.argv(on, tool))
            self.assertIn("tex2d,sprite,audio,textAsset", AssetStudioModCli.argv(off, tool))
            self.assertNotIn("tex2d,sprite,audio,textAsset,mesh", AssetStudioModCli.argv(off, tool))
            head = ["dotnet", "AssetStudioModCLI.dll", str(game), "-m"]
            self.assertEqual(AssetStudioModCli.argv(on, tool)[:4], head)

    def test_missing_exporters_degrade_to_a_warning(self) -> None:
        no_tools = {"VIWO_ASSETSTUDIOMOD": "", "PATH": ""}  # independent of installed tools
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(sys.modules, {"UnityPy": None}),
            mock.patch.dict(os.environ, no_tools),
        ):
            root = Path(tmp)
            game = make_unity_game(root)
            rt = runtime(root, "[plugins]\nunity = on\n")
            self.assertFalse(rt.bindings["export.unity"].bound)
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertTrue(result.success)
            self.assertTrue(any("export.unity" in w for w in result.warnings))


class UnitySourceCoverageTests(unittest.TestCase):
    def test_signatures_cache_roots_and_group_fallback(self) -> None:
        from viwo.plugins.unity import exporters

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = make_unity_game(root)
            assets = game / "MyGame_Data" / "StreamingAssets" / "aa"
            assets.mkdir(parents=True)
            (assets / "chars").write_bytes(b"XORHEADER" * 10 + b"UnityFS\0\0\0\x08rest")
            (assets / "notes.txt").write_text("plain")
            found = {p.name for p in exporters.unity_containers(game)}
            self.assertEqual(found, {"globalgamemanagers", "chars"})
            (game / "MyGame_Data" / "app.info").write_text("Acme Studio\nMy Game\n")
            cache = root / "home" / ".config" / "unity3d" / "Acme Studio" / "My Game"
            cache.mkdir(parents=True)
            with mock.patch("pathlib.Path.home", return_value=root / "home"):
                self.assertEqual(exporters.cache_roots(game), [cache])

            calls = []

            def load(*paths):
                calls.append(len(paths))
                if len(paths) > 1:
                    raise ValueError("one file is corrupt")
                return types.SimpleNamespace(objects=[])

            files = [assets / "chars", assets / "notes.txt"]
            exporters._export_group(
                None, types.SimpleNamespace(load=load), files, {}, {"dump": None}
            )
            self.assertEqual(calls, [2, 1, 1])


class Environment:  # the class name is what the exporter looks for
    pass


def stateful_unitypy() -> types.ModuleType:
    """Fake UnityPy whose containers are JSON {path_id: {type, name, script}}."""

    def load(*paths):
        env = Environment()
        env.files, env.objects = {}, []
        for path in paths:
            state = json.loads(Path(path).read_text())
            node = types.SimpleNamespace(name=path, parent=env)
            env.files[path] = types.SimpleNamespace(
                save=lambda packer=None, st=state: json.dumps(st).encode()
            )
            for pid, rec in state.items():
                data = types.SimpleNamespace(m_Name=rec["name"], m_Script=rec["script"])
                data.save = lambda rec=rec, data=data: rec.update(script=data.m_Script)
                env.objects.append(
                    types.SimpleNamespace(
                        type=types.SimpleNamespace(name=rec["type"]),
                        path_id=int(pid),
                        assets_file=node,
                        parse_as_object=lambda data=data: data,
                    )
                )
        return env

    module = types.ModuleType("UnityPy")
    module.load = load
    return module


class UnityRoundTripTests(unittest.TestCase):
    def test_text_asset_edit_is_written_back_and_verified(self) -> None:
        from viwo.core.roundtrip import repack

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(sys.modules, {"UnityPy": stateful_unitypy()}),
        ):
            root = Path(tmp)
            game = make_unity_game(root)
            assets = game / "MyGame_Data" / "resources.assets"
            assets.write_text(
                json.dumps({"7": {"type": "TextAsset", "name": "dialog", "script": "hello"}})
            )
            rt = runtime(root, "[plugins]\nunity = on\n")
            extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            (root / "ws" / "txt" / "dialog.txt").write_text("bonjour")
            report = repack(rt, root / "ws", root / "patched")
            self.assertTrue(report["verified"], report)
            self.assertEqual(report["plan"][0]["slot"], "pack.unity")
            patched = json.loads(
                (root / "patched" / "MyGame_Data" / "resources.assets").read_text()
            )
            self.assertEqual(patched["7"]["script"], "bonjour")
            self.assertEqual(
                json.loads(assets.read_text())["7"]["script"], "hello"
            )  # original kept


if __name__ == "__main__":
    unittest.main()
