"""L3: the way back of decode.cr2w through WolvenKit's console (doc 18.3), with a fake WolvenKit
CLI (the real one is never run here). An edited PNG goes back with `import --keep` beside a copy
of the original resource, an edited JSON with `convert deserialize`, each run capped like the
export; what WolvenKit refuses, a raw format it does not import and a missing tool are named.
End to end: a texture extracted as PNG and edited is planned as its member, through decode.cr2w,
into the override archive (`mod`, the only form Cyberpunk 2077 has); its JSON edited too is
named as the second edit of one member."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime
from tests.test_redengine import cr2w, rdar
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts.types import OutcomeKind
from viwo.core.context import core_context
from viwo.core.pipeline.runner import extract
from viwo.core.roundtrip import repack
from viwo.plugins.redengine.export import WolvenKitExport

FAKE = """import sys
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index("-o") + 1])
with open(Path(__file__).with_name("calls.txt"), "a") as log:
    log.write(" ".join(args) + "\\n")
if args[0] == "import":
    raw = Path(args[1])
    if "bad" in raw.stem:
        print(f"[ 0: Error ] - Failed to import {raw}.")
    for red in out.glob(raw.stem + ".*"):
        red.write_bytes(red.read_bytes() + b"|imported:" + raw.read_bytes())
elif args[:2] == ["convert", "deserialize"]:
    src = Path(args[2])
    (out / src.name[: -len(".json")]).write_bytes(b"CR2W" + src.read_bytes())
else:
    kind = "png" if args[0] == "export" else "json"
    for name in args[1:]:
        if name.endswith(".xbm") and Path(name).is_file():
            (out / f"{Path(name).name}.{kind}").write_text("{}")
"""


def fake_wolvenkit(folder: Path) -> Path:
    script = folder / "fake_wolvenkit.py"
    script.write_text(f"#!{sys.executable}\n" + FAKE)
    if sys.platform != "win32":
        script.chmod(0o755)
        return script
    wrapper = folder / "fake_wolvenkit.cmd"
    wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
    return wrapper


class EncodeTests(unittest.TestCase):
    def test_import_and_deserialize_write_the_resource_and_failures_are_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root, f"[tools]\nwolvenkit = {fake_wolvenkit(root)}\n")
            ctx = core_context(rt, "repack", root, root / "work")
            original = root / "0000000000001234.xbm"
            original.write_bytes(cr2w("CBitmapTexture"))
            cases = {"t.xbm.png": b"PNG-EDIT", "t.xbm.json": b'{"edited": 1}'}
            for name, data in cases.items():
                (root / name).write_bytes(data)
                out = root / "enc" / name / original.name
                out.parent.mkdir(parents=True)
                done = WolvenKitExport().encode(root / name, original, out, ctx)
                self.assertTrue(done.ok, done.error)
                if name.endswith(".png"):
                    self.assertEqual(out.read_bytes(), original.read_bytes() + b"|imported:" + data)
                else:
                    self.assertEqual(out.read_bytes(), b"CR2W" + data)
            calls = (root / "calls.txt").read_text().splitlines()
            self.assertIn(" -k -o ", calls[0])  # import --keep, into its own output folder
            self.assertTrue(calls[1].startswith("convert deserialize "))
            self.assertTrue(all(c.endswith("-v Minimal") for c in calls))
            (root / "bad.png").write_bytes(b"x")
            bad = original.with_name("bad.xbm")
            bad.write_bytes(b"CR2W")
            failed = WolvenKitExport().encode(root / "bad.png", bad, root / "enc" / "b", ctx)
            self.assertEqual(failed.kind, OutcomeKind.FAILED)
            self.assertIn("Failed to import", failed.error)
            (root / "t.txt").write_text("x")
            odd = WolvenKitExport().encode(root / "t.txt", original, root / "enc" / "o", ctx)
            self.assertIn("not .txt", odd.error)
            none = SimpleNamespace(os=SimpleNamespace(tools=SimpleNamespace(locate=lambda s: None)))
            gone = WolvenKitExport().encode(root / "t.xbm.png", original, root / "x", none)
            self.assertEqual(gone.kind, OutcomeKind.UNAVAILABLE)


class PlanTests(unittest.TestCase):
    def test_an_edited_texture_is_planned_into_the_override_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "cp"
            (game / "archive" / "pc" / "content").mkdir(parents=True)
            (game / "REDprelauncher.exe").write_bytes(b"MZ")
            archive = game / "archive" / "pc" / "content" / "basegame_1.archive"
            archive.write_bytes(rdar({0x1234: [cr2w("CBitmapTexture"), b"pixels"]}))
            rt = runtime(root, f"[tools]\nwolvenkit = {fake_wolvenkit(root)}\n")
            work = root / "ws"
            extract(rt, ExtractionRequest(str(game), str(work)), "j", lambda e: None, CancelToken())
            (work / "png" / "0000000000001234.xbm.png").write_bytes(b"edited texture")
            (work / "json" / "0000000000001234.xbm.json").write_text('{"edited": true}')
            for mode in ("mod", "overwrite"):
                plan = repack(rt, work, None, apply=False, mode=mode)
                item = plan["plan"][0]
                self.assertEqual(item["container"], "archive/pc/content/basegame_1.archive")
                self.assertEqual((item["slot"], item["mode"]), ("pack.archive", "mod"))
                self.assertEqual(item["ways"][0]["encoder"], "decode.cr2w")
                self.assertTrue(item["members"][0].endswith(".xbm"))
                twice = [s for s in plan["skipped"] if "same member" in s]
                self.assertEqual(len(twice), 1)
            self.assertIn("no rewrite of it", item["why"])  # overwrite asked: said why not


if __name__ == "__main__":
    unittest.main()
