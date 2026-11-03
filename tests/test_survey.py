"""L3: `viwo survey`: categories, density, coverage, deep carving, CLI and HTTP handler."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests.helpers import make_zip, runtime, tree_hashes, write_ini
from tests.test_carve import blob
from tests.test_doom import make_wad
from viwo.api import app as app_module
from viwo.api.handlers_tools import TOOL_GET, survey_library
from viwo.cli import main
from viwo.contracts import ViwoError
from viwo.core import surveys
from viwo.core.survey import games_in, survey


def make_library(root: Path) -> Path:
    lib = root / "lib"
    (lib / "Doomish").mkdir(parents=True)
    make_wad(lib / "Doomish" / "game.wad", [("X", b"x")], b"IWAD")
    (lib / "Doomish" / "readme.txt").write_text("hello")
    odd = lib / "Odd"
    odd.mkdir()
    (odd / "secret.pak").write_bytes(os.urandom(200_000))
    (odd / "assets.bin").write_bytes(blob(root)[0] * 20)
    make_zip(odd / "extra.zip", {"a.txt": b"a"})
    (odd / "Game.exe").write_bytes(b"MZ" + b"\0" * 5000)
    return lib


class SurveyTests(unittest.TestCase):
    def test_library_report_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lib = make_library(Path(tmp))
            before = tree_hashes(lib)
            rt = runtime(Path(tmp))
            self.assertEqual([g.name for g in games_in(lib, rt)], ["Doomish", "Odd"])
            self.assertEqual(games_in(lib / "Doomish", rt), [lib / "Doomish"])
            doom, odd = survey(rt, lib)
            self.assertEqual((doom["engine"], doom["coverage"]), ("doom", 1.0))
            cats = odd["categories"]
            self.assertEqual(cats["code"]["files"], 1)
            self.assertEqual(cats["container"]["files"], 1)
            self.assertEqual(cats["unknown-dense"]["files"], 1)
            self.assertEqual(cats["unknown"]["files"], 1)
            self.assertEqual(
                {u["file"]: u["dense"] for u in odd["unknown"]},
                {"secret.pak": True, "assets.bin": False},
            )
            deep = survey(rt, lib, deep=True)[1]
            self.assertEqual(deep["categories"]["carvable"]["files"], 1)
            self.assertGreater(deep["coverage"], odd["coverage"])
            self.assertEqual(tree_hashes(lib), before)

    def test_cli_and_http(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lib = make_library(Path(tmp))
            ini = write_ini(Path(tmp))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["--ini", str(ini), "survey", str(lib), "--json"]), 0)
            self.assertEqual(len(json.loads(out.getvalue())["data"]["games"]), 2)
            app = app_module.App(runtime(Path(tmp)))
            result = survey_library(app, {"folder": str(lib), "deep": True})
            self.assertTrue(result["success"] and result["jobId"], result)
            self.assertEqual(
                survey_library(app, {"folder": str(lib / "nope")})["code"], "not_found"
            )
            self.assertEqual(app.jobs.get(result["jobId"]).kind, "survey")
            lines = [e.message for e in app.jobs.get(result["jobId"]).events]
            for head in (
                "Surveying Doomish (1/2)",
                "Scanning files: ",
                "Identifying files: ",
                "Identified containers: ",
                "Probing archives: ",
                "Carving unknown blobs: ",
                "Decoders available: ",
                "Report saved: ",
            ):
                self.assertTrue(any(m.startswith(head) for m in lines), (head, lines))
            self.assertTrue(Path(result["reportPath"]).is_file())
            again = survey_library(app, {"folder": str(lib)})
            self.assertNotEqual(again["reportId"], result["reportId"])  # never overwritten
            listed = TOOL_GET["/api/surveys"](app, {})["reports"]
            self.assertEqual([r["id"] for r in listed][:2], [again["reportId"], result["reportId"]])
            self.assertEqual(listed[0]["gameCount"], 2)
            report = TOOL_GET["/api/survey-report"](app, {"id": result["reportId"]})["report"]
            self.assertEqual(len(report["games"]), 2)
            self.assertTrue(report["deep"])
            self.assertEqual(
                TOOL_GET["/api/survey-report"](app, {"id": "../x"})["code"], "invalid_request"
            )

    def test_reports_are_numbered_and_contained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "surveys"
            first = surveys.save(root, Path("C:/Games/My Game!"), False, [{"path": "a"}])
            second = surveys.save(root, Path("C:/Games/My Game!"), False, [])
            self.assertTrue(first["id"].endswith("-My_Game"))
            self.assertEqual(second["id"], first["id"] + "-2")
            ids = [r["id"] for r in surveys.list_reports(root)]
            self.assertEqual(ids, [second["id"], first["id"]])
            self.assertEqual(surveys.load(root, first["id"])["gameCount"], 1)
            for bad in ("../../etc/passwd", "20260101-000000-x/../y", "nope"):
                with self.assertRaises(ViwoError):
                    surveys.load(root, bad)
            self.assertEqual(surveys.list_reports(Path(tmp) / "missing"), [])


if __name__ == "__main__":
    unittest.main()
