"""L3: sanitizer phases 2 and 3 (doc 5.1): open-format copies by the lossless decoders,
originals to the trash only in the replace recipe, lossy transcodes only when picked, renumbered
sequences; every apply undone exactly. ffmpeg is a Python stand-in (tests/test_godot.py)."""

import random
import stat
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.api import app as app_module
from viwo.api.handlers import GET, POST
from viwo.contracts import ViwoError
from viwo.core import provenance, sanitizer
from viwo.core.sanitizer_rules import collect_rules

FAKE_FFMPEG = """import sys
from pathlib import Path
args = sys.argv[1:]
if "-version" in args:
    print("ffmpeg version 6.1.1-fake")
    sys.exit(0)
src, out = Path(args[args.index("-i") + 1]), Path(args[-1])
if "bad" in src.name:
    print("Invalid data found when processing input", file=sys.stderr)
    sys.exit(1)
tag = b"PNG:" if out.suffix == ".png" else out.suffix.encode() + b":" + " ".join(args).encode()
out.write_bytes(tag + b"|" + src.read_bytes())
"""
DDS = b"DDS " + bytes(124)


def fake_ffmpeg(folder: Path) -> str:
    """[tools] lines pointing ffmpeg and ffprobe at the stand-in (a .cmd wrapper on Windows)."""
    script = folder / "fake_ffmpeg.py"
    script.write_text(f"#!{sys.executable}\n{FAKE_FFMPEG}")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    tool = script
    if sys.platform == "win32":
        tool = folder / "fake_ffmpeg.cmd"
        tool.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
    return f"[tools]\nffmpeg = {tool}\nffprobe = {tool}\n"


def workspace(root: Path, files: dict[str, bytes]) -> Path:
    ws = root / "ws"
    ws.mkdir()
    (ws / ".viwo-workspace").write_text("")
    for rel, data in files.items():
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_bytes(data)
    return ws


class PhaseTwoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.rt = runtime(self.root, fake_ffmpeg(self.root))
        self.rules = collect_rules(self.rt)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def plan(self, ws: Path, recipe: str) -> dict:
        return sanitizer.plan(ws, rules=self.rules, recipe=recipe)

    def test_convert_copies_beside_and_undo_takes_them_away(self) -> None:
        ws = workspace(self.root, {"dds/a.dds": DDS + b"a", "dds/b.dds": DDS + b"b"})
        (ws / "dds" / "empty.dds").write_bytes(b"")
        provenance.add(ws, [{"path": "png/b.dds.png", "origin": "decode:x:dds/b.dds:b.dds.png"}])
        before = tree_hashes(ws, skip_reserved=True)
        plan = self.plan(ws, "phase2-convert")
        self.assertEqual(
            [(f["path"], f["action"]) for f in plan["findings"]], [("dds/a.dds", "convert")]
        )
        self.assertIn("lossless", plan["findings"][0]["message"])
        self.assertFalse(plan["findings"][0]["lossy"])
        done = sanitizer.apply(ws, plan["planId"], rules=self.rules)
        self.assertEqual(done["converted"][0]["made"], ["png/a.dds.png"])
        self.assertEqual((ws / "png/a.dds.png").read_bytes(), b"PNG:|" + DDS + b"a")
        self.assertEqual((ws / "dds/a.dds").read_bytes(), DDS + b"a")  # the original stays
        entry = next(e for e in provenance.entries(ws) if e["path"] == "png/a.dds.png")
        self.assertEqual(entry["origin"], "decode:ffmpeg-image:dds/a.dds:a.dds.png")
        self.assertEqual(self.plan(ws, "phase2-convert")["findings"], [])  # decoded now
        undone = sanitizer.undo(ws, done["undoToken"])
        self.assertEqual((undone["removed"], undone["notRestored"]), (1, []))
        self.assertEqual(tree_hashes(ws, skip_reserved=True), before)
        self.assertNotIn("png/a.dds.png", {e["path"] for e in provenance.entries(ws)})

    def test_replace_trashes_the_original_and_an_edited_copy_survives_undo(self) -> None:
        ws = workspace(self.root, {"dds/a.dds": DDS + b"a", "dds/bad.dds": DDS + b"x"})
        before = tree_hashes(ws, skip_reserved=True)
        plan = self.plan(ws, "phase2-replace")
        done = sanitizer.apply(ws, plan["planId"], rules=self.rules)
        self.assertFalse((ws / "dds/a.dds").exists())
        self.assertTrue((ws / ".trash/items/dds/a.dds").is_file())
        self.assertEqual(done["trashed"], 1)
        self.assertTrue(any("bad.dds" in f and "Invalid data" in f for f in done["failed"]))
        self.assertTrue((ws / "dds/bad.dds").is_file())  # a failed copy trashes nothing
        sanitizer.undo(ws, done["undoToken"])
        self.assertEqual(tree_hashes(ws, skip_reserved=True), before)
        again = sanitizer.apply(ws, self.plan(ws, "phase2-convert")["planId"], rules=self.rules)
        (ws / "png/a.dds.png").write_bytes(b"edited by the user")
        undone = sanitizer.undo(ws, again["undoToken"])
        self.assertEqual(undone["notRestored"], ["png/a.dds.png"])  # kept, named
        self.assertEqual((ws / "png/a.dds.png").read_bytes(), b"edited by the user")

    def test_property_apply_then_undo_restores_any_workspace(self) -> None:
        rng = random.Random(5)
        for case in range(6):
            with tempfile.TemporaryDirectory() as tmp:
                files = {
                    f"{rng.choice(['dds', 'x'])}/{rng.choice(['s', 'bad', 't'])}{i}"
                    f"{rng.choice(['.dds', '.wav', '.txt'])}": rng.randbytes(rng.randint(1, 64))
                    for i in range(rng.randint(1, 8))
                }
                ws = workspace(Path(tmp), files)
                before = tree_hashes(ws, skip_reserved=True)
                recipe = rng.choice(["phase2-convert", "phase2-replace", "phase3-audio"])
                plan = self.plan(ws, recipe)
                done = sanitizer.apply(ws, plan["planId"], "all", rules=self.rules)
                for item in done["converted"]:  # each copy is what its decoder wrote
                    made = (ws / item["made"][0]).read_bytes()
                    self.assertTrue(made.endswith(b"|" + files[item["path"]]), case)
                undone = sanitizer.undo(ws, done["undoToken"])
                self.assertEqual(undone["notRestored"], [], case)
                self.assertEqual(tree_hashes(ws, skip_reserved=True), before, f"case {case}")


class PhaseThreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_lossy_runs_only_when_picked(self) -> None:
        rt = runtime(self.root, fake_ffmpeg(self.root))
        rules = collect_rules(rt)
        ws = workspace(self.root, {"wav/a.wav": b"RIFF....", "avi/m.avi": b"AVI data"})
        safe = sanitizer.plan(ws, rules=rules)
        self.assertNotIn("transcode", {f["action"] for f in safe["findings"]})
        plan = sanitizer.plan(ws, rules=rules, recipe="phase3-audio")
        self.assertEqual([f["path"] for f in plan["findings"]], ["wav/a.wav"])
        self.assertTrue(plan["findings"][0]["lossy"] and "LOSSY" in plan["findings"][0]["message"])
        skipped = sanitizer.apply(ws, plan["planId"], "all-safe", rules=rules)
        self.assertEqual((skipped["applied"], skipped["converted"]), (0, []))  # never by default
        done = sanitizer.apply(ws, plan["planId"], [0], rules=rules)
        made = (ws / done["converted"][0]["made"][0]).read_bytes()
        self.assertIn(b"libopus", made)
        self.assertTrue((ws / "wav/a.wav").is_file())  # the original stays
        video = sanitizer.plan(ws, rules=rules, recipe="phase3-video")
        done = sanitizer.apply(ws, video["planId"], "all", rules=rules)
        self.assertEqual(done["converted"][0]["made"], ["mp4/m.mp4"])
        self.assertIn(b"libx264", (ws / "mp4/m.mp4").read_bytes())

    def test_without_ffmpeg_the_recipe_says_why(self) -> None:
        rt = runtime(self.root)  # media.encode unbound, whatever ffmpeg this machine has
        rt.bindings["media.encode"] = replace(rt.bindings["media.encode"], main="", spare="")
        rules = collect_rules(rt)
        ws = workspace(self.root, {"wav/a.wav": b"RIFF...."})
        plan = sanitizer.plan(ws, rules=rules, recipe="phase3-audio")
        self.assertEqual(plan["findings"], [])
        self.assertTrue(plan["warnings"] and "ffmpeg" in plan["warnings"][0])
        listed = {r["id"]: r for r in sanitizer.recipes(rules)}
        self.assertIn("ffmpeg", listed["phase3-audio"]["unready"])
        self.assertTrue(listed["phase3-audio"]["lossy"] and not listed["phase2-convert"]["lossy"])
        self.assertEqual(listed["phase1-safe"]["unready"], "")
        no_rt = {r["id"]: r for r in sanitizer.recipes()}  # without a runtime: named, not hidden
        self.assertIn("not loaded", no_rt["phase2-convert"]["unready"])

    def test_property_renumber_is_contiguous_ordered_and_undoable(self) -> None:
        rng = random.Random(11)
        for case in range(10):
            with tempfile.TemporaryDirectory() as tmp:
                numbers = rng.sample(range(0, 300), rng.randint(2, 9))
                files = {f"png/f_{n:0{rng.choice([1, 3])}d}.png": bytes([n % 256]) for n in numbers}
                ws = workspace(Path(tmp), files)
                before = tree_hashes(ws, skip_reserved=True)
                plan = sanitizer.plan(ws, recipe="phase3-renumber")
                done = sanitizer.apply(ws, plan["planId"], "all")
                self.assertEqual(done["failed"], [])
                names = sorted(p.name for p in (ws / "png").iterdir())
                width = len(names[0]) - len("f_.png")
                low = min(numbers)
                want = [f"f_{low + i:0{width}d}.png" for i in range(len(numbers))]
                self.assertEqual(names, want, case)
                order = [(ws / "png" / n).read_bytes() for n in names]  # numeric order kept
                self.assertEqual(order, [bytes([n % 256]) for n in sorted(numbers)], case)
                sanitizer.undo(ws, done["undoToken"])
                self.assertEqual(tree_hashes(ws, skip_reserved=True), before, case)

    def test_renumber_leaves_a_sequence_with_a_number_twice(self) -> None:
        ws = workspace(self.root, {"png/a2.png": b"1", "png/a02.png": b"2", "png/a7.png": b"3"})
        plan = sanitizer.plan(ws, recipe="phase3-renumber")
        self.assertEqual([f["action"] for f in plan["findings"]], ["none"])
        self.assertIn("numbered 2", plan["findings"][0]["message"])


class RouteTests(unittest.TestCase):
    def test_recipes_plan_apply_undo_over_http(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = app_module.App(runtime(root, fake_ffmpeg(root)))
            ws = workspace(root, {"dds/a.dds": DDS + b"a"})
            app.set_workspace(ws)
            listed = GET["/api/sanitizer/recipes"](app, {})["recipes"]
            self.assertEqual([r["id"] for r in listed], [r["id"] for r in sanitizer.RECIPES])
            plan = POST["/api/sanitizer/plan"](app, {"recipeId": "phase2-convert"})
            done = POST["/api/sanitizer/apply"](app, {"planId": plan["planId"], "accept": [0]})
            self.assertEqual(done["converted"][0]["path"], "dds/a.dds", done)
            undone = POST["/api/sanitizer/undo"](app, {"undoToken": done["undoToken"]})
            self.assertEqual(undone["removed"], 1)
            journal = ws / sanitizer.JOURNAL / f"{plan['planId']}.json"
            self.assertFalse(journal.exists())
            with self.assertRaises(ViwoError):
                sanitizer.plan(ws, recipe="phase9")


if __name__ == "__main__":
    unittest.main()
