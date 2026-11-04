"""L3: everything else a Unity game holds (objects.py). For random objects the dump writes one
valid JSON array per serialized file holding every object once, raw bytes summarised above a
size, and counts and names the objects it could not read; video clips, fonts and shaders come out
in their own formats or not at all when empty; MonoBehaviour layouts come from the game's managed
assemblies or the reason they cannot is said. Verified on real data: ULTRAKILL Prelude (Mono):
307,864 objects to JSON in 28 files, 89 shaders, 2 fonts and a video in 90 s."""

from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.plugins.unity import objects


class FakeObject:
    def __init__(self, path_id: int, source: str, tree=None, fails: bool = False) -> None:
        self.path_id, self.assets_file = (
            path_id,
            SimpleNamespace(name=source, unity_version="2021.3.1f1"),
        )
        self.tree, self.fails = tree, fails

    def read_typetree(self):
        if self.fails:
            raise ValueError("Expected to read 84 bytes, but only read 32 bytes")
        return self.tree


class DumpTests(unittest.TestCase):
    def test_every_object_once_valid_json_per_file_and_failures_counted(self) -> None:
        rng = random.Random(8)
        for _ in range(12):
            with tempfile.TemporaryDirectory() as tmp:
                dump, expected, failed = objects.Dump(Path(tmp)), {}, {}
                for i in range(rng.randint(0, 60)):
                    source = rng.choice(["level0", "level1", "sharedassets0.assets", "CAB-x"])
                    kind = rng.choice(["GameObject", "Transform", "Material", "MonoBehaviour"])
                    fails = kind == "MonoBehaviour" and rng.random() < 0.5
                    blob = rng.randbytes(rng.choice([0, 16, objects.BLOB + 1]))
                    dump.add(
                        FakeObject(
                            i, source, {"m_Name": f"n{i}", "raw": blob, "p": Path("a")}, fails
                        ),
                        kind,
                    )
                    expected.setdefault(source, []).append((i, kind, fails, len(blob)))
                    failed[kind] = failed.get(kind, 0) + fails
                summary, notes = dump.close()
                for source, rows in expected.items():
                    data = json.loads(
                        (Path(tmp) / "data" / f"{source}.objects.json").read_text("utf-8")
                    )
                    self.assertEqual(
                        [(d["path_id"], d["type"]) for d in data], [r[:2] for r in rows]
                    )
                    for entry, (_, _, fails, size) in zip(data, rows):
                        if fails:
                            self.assertIn("Expected to read", entry["unread"])
                        elif size > objects.BLOB:
                            self.assertEqual(entry["data"]["raw"], f"<{size} bytes>")
                        else:
                            self.assertEqual(len(entry["data"]["raw"]), 2 * size)  # hex inline
                total = sum(len(r) for r in expected.values())
                self.assertEqual(
                    summary,
                    f"{total} object(s) as JSON in {len(expected)} file(s) (data/)"
                    if total
                    else "",
                )
                for kind, n in failed.items():
                    if n:
                        self.assertTrue(
                            any(note.startswith(f"{n} {kind}(s) listed") for note in notes)
                        )
                self.assertEqual(len(notes), sum(1 for n in failed.values() if n))


class MediaTests(unittest.TestCase):
    def ctx(self, tmp: str):
        return SimpleNamespace(staging=Path(tmp))

    def test_fonts_videos_and_shaders_in_their_own_formats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx, obj = self.ctx(tmp), SimpleNamespace(assets_file=None)
            for head, ext in ((b"OTTO", ".otf"), (b"\x00\x01\x00\x00", ".ttf"), (b"ttcf", ".ttc")):
                out = objects.media(
                    ctx, "Font", SimpleNamespace(m_FontData=list(head + b"xx")), obj, "f"
                )
                self.assertEqual((out.suffix, out.read_bytes()), (ext, head + b"xx"))
            self.assertIsNone(objects.media(ctx, "Font", SimpleNamespace(m_FontData=[]), obj, "e"))
            shader = SimpleNamespace(export=lambda: 'Shader "x" {}')
            self.assertEqual(
                objects.media(ctx, "Shader", shader, obj, "s").read_text(), 'Shader "x" {}'
            )
            res = SimpleNamespace(m_Source="a.resource", m_Offset=4, m_Size=3)
            clip = SimpleNamespace(m_ExternalResources=res, m_OriginalPath="Assets/intro.webm")
            with mock.patch(
                "UnityPy.helpers.ResourceReader.get_resource_data", return_value=b"vid"
            ) as read:
                out = objects.media(ctx, "VideoClip", clip, obj, "intro")
            self.assertEqual((out.name, out.read_bytes()), ("intro.webm", b"vid"))
            self.assertEqual(read.call_args[0][2:], (4, 3))  # offset and size from the clip
            empty = SimpleNamespace(
                m_ExternalResources=SimpleNamespace(m_Size=0), m_OriginalPath=""
            )
            self.assertIsNone(objects.media(ctx, "VideoClip", empty, obj, "none"))


class LayoutTests(unittest.TestCase):
    def test_managed_assemblies_give_layouts_and_every_other_case_says_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            env = SimpleNamespace(objects=[FakeObject(1, "level0")], typetree_generator=None)
            self.assertIn("IL2CPP", objects.layouts(env, game))
            (game / "G_Data" / "Managed").mkdir(parents=True)
            (game / "G_Data" / "Managed" / "Assembly-CSharp.dll").write_bytes(b"MZ")
            loaded = []
            fake = mock.Mock(
                side_effect=lambda v: SimpleNamespace(load_local_dll_folder=loaded.append, v=v)
            )
            with mock.patch("UnityPy.helpers.TypeTreeGenerator.TypeTreeGenerator", fake):
                self.assertEqual(objects.layouts(env, game), "")
                self.assertEqual(fake.call_args[0][0], "2021.3.1f1")
                self.assertEqual(Path(loaded[0]).name, "Managed")
                self.assertIsNotNone(env.typetree_generator)
                bare = SimpleNamespace(
                    objects=[SimpleNamespace(assets_file=SimpleNamespace(unity_version=""))]
                )
                self.assertIn("no Unity version", objects.layouts(bare, game))
            with mock.patch(
                "UnityPy.helpers.TypeTreeGenerator.TypeTreeGenerator",
                side_effect=ImportError("no API"),
            ):
                self.assertIn("no API", objects.layouts(env, game))


class ExporterTests(unittest.TestCase):
    def env(self):
        def obj(i, kind, parsed=None, tree=None, fails=False):
            o = FakeObject(i, "level0", tree or {"m_Name": kind}, fails)
            o.type, o.parse_as_object = SimpleNamespace(name=kind), lambda: parsed
            return o

        font = SimpleNamespace(m_Name="Body", m_FontData=list(b"OTTOfont"))
        return SimpleNamespace(
            objects=[
                obj(1, "GameObject"),
                obj(2, "Font", font),
                obj(3, "MonoBehaviour", fails=True),
            ]
        )

    def run_export(self, options):
        from viwo.contracts import CancelToken
        from viwo.plugins.unity import exporters

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "game" / "G_Data").mkdir(parents=True)
        (root / "game" / "G_Data" / "level0").write_bytes(b"x")
        logs = []
        ctx = SimpleNamespace(
            game_root=root / "game",
            staging=root / "out",
            options=options,
            selected_exts=None,
            cancel=CancelToken(),
            log=lambda m, **k: logs.append(m),
        )
        ctx.staging.mkdir()
        with mock.patch("UnityPy.load", return_value=self.env()):
            out = exporters.UnityPyExporter().export(ctx)
        return out, ctx.staging, logs

    def test_objects_on_dumps_writes_media_and_says_what_is_missing(self) -> None:
        out, staging, logs = self.run_export({})
        self.assertEqual(out.files, 1)  # the font; the dump is not an asset count
        self.assertTrue((staging / "font" / "Body.otf").is_file())
        data = json.loads((staging / "data" / "level0.objects.json").read_text("utf-8"))
        self.assertEqual([d["type"] for d in data], ["GameObject", "MonoBehaviour"])
        self.assertIn("2 object(s) as JSON in 1 file(s) (data/)", logs)
        self.assertTrue(any(n.startswith("1 MonoBehaviour(s) listed") for n in out.notes))
        self.assertTrue(any("IL2CPP" in n for n in out.notes))  # no managed assemblies: said

    def test_objects_off_keeps_the_old_export(self) -> None:
        out, staging, logs = self.run_export({"objects": "off"})
        self.assertFalse((staging / "data").exists())
        self.assertFalse((staging / "font").exists())
        self.assertEqual(out.notes, ())


if __name__ == "__main__":
    unittest.main()
