"""L4: the way back of decoded files (doc 18.3). An edited decoded file is planned as the member
it becomes (encoder, container, packer, mod or overwrite), encoded at build time and verified
against the encoded bytes: a Genie sprite edited as PNG comes back as the SLP in its DRS; a
Ren'Py script edited as `.rpy` replaces its `.rpyc` (loose or archived), the stale one removed;
`mod` writes loose files over the archive, `overwrite` rewrites it. Every file that cannot go
back is named with its reason, and an encoder's failure is a failed result, never silent."""

from __future__ import annotations

import io
import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from tests.helpers import runtime
from tests.test_containers import drs
from tests.test_encoders import dds
from tests.test_renpy import make_rpa
from tests.test_slp import COLORS, PAL
from tests.test_slp import encode as random_slp
from tests.test_vtf import vtf
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts import workspace as ws
from viwo.core.pipeline.collect import sha256
from viwo.core.pipeline.runner import extract
from viwo.core.roundtrip import repack
from viwo.core.roundtrip_encode import origin_parts
from viwo.plugins.genie.slp import frames, sheet
from viwo.plugins.renpy.rpa import read_index


def workspace(root: Path, game: Path, files: dict[str, tuple[bytes, dict]]) -> Path:
    """A workspace as extraction leaves it: the run record, the files, their provenance."""
    work = root / "ws"
    (work / ws.RUNS_DIR).mkdir(parents=True)
    record = {"finished": "2026-11-18", "request": {"game_path": str(game)}}
    (work / ws.RUNS_DIR / "run.json").write_text(json.dumps(record))
    lines = []
    for rel, (data, fields) in files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_bytes(data)
        lines.append(json.dumps({"path": rel, "sha256": sha256(work / rel), **fields}))
    (work / ws.PROVENANCE_FILE).write_text("\n".join(lines) + "\n")
    return work


def decoded(source: str, out: str, backend: str) -> dict:
    return {"origin": f"decode:{backend}:{source}:{out}", "kind": "derived"}


class RenPyScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = self.root = Path(self._tmp.name)
        self.rt = runtime(root)
        game = self.game = root / "vn"
        (game / "renpy").mkdir(parents=True)
        (game / "game").mkdir()
        members = {"script.rpyc": b"RPC2 old", "images/bg.png": b"old-bg"}
        make_rpa(game / "game" / "scripts.rpa", members)
        (game / "game" / "other.rpyc").write_bytes(b"RPC2 other")
        rpa = {"kind": "member", "container": "game/scripts.rpa"}
        self.ws = workspace(
            root,
            game,
            {
                "rpyc/script.rpyc": (b"RPC2 old", {**rpa, "member": "script.rpyc"}),
                "png/bg.png": (b"old-bg", {**rpa, "member": "images/bg.png"}),
                "rpyc/other.rpyc": (b"RPC2 other", {"kind": "loose", "member": "game/other.rpyc"}),
                "rpy/script.rpy": (
                    b"label a:",
                    decoded("rpyc/script.rpyc", "script.rpy", "unrpyc-cli"),
                ),
                "rpy/other.rpy": (
                    b"label b:",
                    decoded("rpyc/other.rpyc", "other.rpy", "unrpyc-cli"),
                ),
            },
        )
        (self.ws / "rpy" / "script.rpy").write_text("label a:\n    'edited'\n")
        (self.ws / "rpy" / "other.rpy").write_text("label b:\n    'edited too'\n")
        (self.ws / "png" / "bg.png").write_bytes(b"NEW-BG")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def archive(self, copy: Path) -> dict[str, bytes]:
        path = copy / "game" / "scripts.rpa"
        with open(path, "rb") as fh:
            index = read_index(fh)
        data = path.read_bytes()
        return {m: data[e[0][0] : e[0][0] + e[0][1]] for m, e in index.items()}

    def test_mod_writes_loose_files_and_takes_the_stale_script_out_of_the_archive(self) -> None:
        plan = repack(self.rt, self.ws, None, apply=False)
        shown = [(p["container"], p["mode"], p["members"], p["drops"]) for p in plan["plan"]]
        self.assertEqual(
            shown,
            [
                ("", "overwrite", ["game/other.rpy"], ["game/other.rpyc"]),
                ("", "mod", ["game/images/bg.png", "game/script.rpy"], []),
                ("game/scripts.rpa", "overwrite", [], ["script.rpyc"]),
            ],
        )
        ways = {w["file"]: w for p in plan["plan"] for w in p["ways"]}
        self.assertEqual(ways["rpy/script.rpy"]["member"], "game/script.rpy")
        self.assertEqual(ways["rpy/script.rpy"]["replaces"], "script.rpyc")
        self.assertEqual(ways["rpy/other.rpy"]["encoder"], "decode.rpyc")
        self.assertIn("stale member must not win", plan["plan"][2]["why"])
        copy = self.root / "copy"
        report = repack(self.rt, self.ws, copy)
        self.assertTrue(report["verified"], report)
        self.assertIn("'edited'", (copy / "game" / "script.rpy").read_text())
        self.assertIn("'edited too'", (copy / "game" / "other.rpy").read_text())
        self.assertFalse((copy / "game" / "other.rpyc").exists())
        self.assertEqual((copy / "game" / "images" / "bg.png").read_bytes(), b"NEW-BG")
        self.assertEqual(self.archive(copy), {"images/bg.png": b"old-bg"})  # the rest kept
        self.assertTrue((self.game / "game" / "other.rpyc").is_file())  # the game: only read

    def test_overwrite_rewrites_the_archive(self) -> None:
        copy = self.root / "copy"
        report = repack(self.rt, self.ws, copy, mode="overwrite")
        self.assertTrue(report["verified"], report)
        rpa = [p for p in report["plan"] if p["container"]][0]
        self.assertEqual((rpa["members"], rpa["drops"]), (["images/bg.png"], ["script.rpyc"]))
        self.assertEqual(self.archive(copy), {"images/bg.png": b"NEW-BG"})
        self.assertFalse((copy / "game" / "images").exists())
        self.assertIn("'edited'", (copy / "game" / "script.rpy").read_text())

    def test_an_encoder_failure_is_a_failed_result(self) -> None:
        (self.ws / "rpy" / "other.rpy").write_bytes(b"\xff\xfe not text")
        report = repack(self.rt, self.ws, self.root / "copy")
        self.assertFalse(report["verified"])
        failed = [r for r in report["results"] if r.get("error")]
        self.assertEqual(failed[0]["failed"], ["game/other.rpy"])
        self.assertIn("not UTF-8", failed[0]["error"])


class SkippedTests(unittest.TestCase):
    def test_every_file_that_cannot_go_back_says_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt, game = runtime(root), root / "g"
            game.mkdir()
            member = {"kind": "member", "container": "data.zip"}
            animated = vtf(random.Random(1), 12, (4, 4), 1, 4, 3, bytes(64))
            work = workspace(
                root,
                game,
                {
                    "wem/a.wem": (b"RIFF wem", {**member, "member": "a.wem"}),
                    "wav/a_0.wav": (b"RIFF", decoded("wem/a.wem", "a_0.wav", "vgmstream-cli")),
                    "rpyc/n.rpyc": (b"nested", {"kind": "derived", "origin": "game:x.zip!y"}),
                    "rpy/n.rpy": (b"x", decoded("rpyc/n.rpyc", "n.rpy", "unrpyc-cli")),
                    "rpy/gone.rpy": (b"x", decoded("rpyc/gone.rpyc", "gone.rpy", "unrpyc-cli")),
                    "rpyc/e.rpyc": (b"compiled", {**member, "member": "e.rpyc"}),
                    "rpy/e.rpy": (b"x", decoded("rpyc/e.rpyc", "e.rpy", "unrpyc-cli")),
                    "dds/t.dds": (dds("DX10:98", (4, 4)), {**member, "member": "t.dds"}),
                    "png/t.dds.png": (b"x", decoded("dds/t.dds", "t.dds.png", "ffmpeg-image")),
                    "vtf/m.vtf": (animated, {**member, "member": "m.vtf"}),
                    "png/m.png": (b"x", decoded("vtf/m.vtf", "m.png", "vtf-builtin")),
                },
            )
            edited = ("wav/a_0.wav", "rpy/n.rpy", "rpy/gone.rpy", "rpy/e.rpy", "rpyc/e.rpyc")
            for rel in (*edited, "png/t.dds.png", "png/m.png"):
                (work / rel).write_bytes(b"edited")
            report = repack(rt, work, None, apply=False)
            why = dict(s.split(": ", 1) for s in report["skipped"])
            self.assertIn("decode.audio is one way", why["wav/a_0.wav"])
            self.assertIn("proprietary", why["wav/a_0.wav"])
            self.assertIn("nested container", why["rpy/n.rpy"])
            self.assertIn("no longer in the workspace", why["rpy/gone.rpy"])
            self.assertIn("was edited too", why["rpy/e.rpy"])
            self.assertIn("block-compressed", why["png/t.dds.png"])  # named at plan time
            self.assertIn("only single images", why["png/m.png"])
            self.assertEqual([w for p in report["plan"] for w in p["ways"]], [])  # none goes

    def test_the_origin_names_backend_source_and_output(self) -> None:
        rng = random.Random(9)
        for _ in range(50):
            parts = ["".join(rng.choice("ab./_-") for _ in range(rng.randint(1, 9))) for _ in "xyz"]
            source = f"{parts[1]}:{parts[2]}" if rng.random() < 0.3 else parts[1]  # Linux names
            self.assertEqual(
                origin_parts(f"decode:{parts[0]}:{source}:{parts[2]}"),
                (parts[0], source, parts[2]),
            )


class GenieSpriteTests(unittest.TestCase):
    def test_an_edited_sheet_goes_back_into_its_drs_and_reads_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt, game = runtime(root), root / "aoe"
            game.mkdir()
            original, _ = random_slp(random.Random(4), [(6, 3), (4, 5)])
            (game / "graphics.drs").write_bytes(drs({"slp": {1: original}}))
            palette = drs({"bina": {50500: PAL.encode()}}).replace(b" ani", b"anib", 1)
            (game / "interfac.drs").write_bytes(palette)  # the table type of a 4-letter suffix
            work = root / "ws"
            request = ExtractionRequest(str(game), str(work))
            extract(rt, request, "j", lambda e: None, CancelToken())
            pixels = [
                [COLORS[(x * y) % 200] if x != y else None for x in range(6)] for y in range(3)
            ]
            edit = sheet([(6, 3, pixels), (4, 5, [[COLORS[7]] * 4] * 5)])
            out = io.BytesIO()
            edit.save(out, "PNG")
            (work / "png" / "1.png").write_bytes(out.getvalue())
            plan = repack(rt, work, None, apply=False)
            item = plan["plan"][0]
            self.assertEqual((item["container"], item["slot"]), ("graphics.drs", "pack.drs"))
            self.assertEqual((item["mode"], item["members"]), ("overwrite", ["1.slp"]))
            self.assertIn("no mod form", item["why"])
            self.assertEqual(item["ways"][0]["encoder"], "decode.slp")
            report = repack(rt, work, root / "copy")
            self.assertTrue(report["verified"], report)
            from viwo.plugins.genie import DrsBuiltin

            back = root / "back"
            back.mkdir()
            DrsBuiltin().extract(
                root / "copy" / "graphics.drs", back, SimpleNamespace(cancel=CancelToken())
            )
            shown = sheet(frames((back / "1.slp").read_bytes(), COLORS))
            self.assertEqual(shown.tobytes(), Image.open(io.BytesIO(out.getvalue())).tobytes())


if __name__ == "__main__":
    unittest.main()
