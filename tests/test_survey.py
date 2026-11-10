"""L3: `viwo survey`: categories, density, coverage, deep carving, CLI and HTTP handler."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

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
    (lib / "Doomish" / "port" / "x64").mkdir(parents=True)
    (lib / "Doomish" / "port" / "x64" / "doom.exe").write_bytes(b"MZ")  # its source port
    odd = lib / "Odd"
    odd.mkdir()
    (odd / "secret.pak").write_bytes(os.urandom(200_000))
    (odd / "assets.bin").write_bytes(blob(root)[0] * 20)
    make_zip(odd / "extra.zip", {"a.txt": b"a"})
    (odd / "Game.exe").write_bytes(b"MZ" + b"\0" * 5000)
    return lib


class SurveyPropertyTests(unittest.TestCase):
    """Random games: every file lands in exactly one category, the coverage is what the
    categories say, every missing tool is named, and an unreadable file is counted, never
    fatal."""

    def test_every_file_is_counted_once_and_coverage_is_honest(self) -> None:
        import random

        from tests.helpers import make_rar
        from viwo.core.survey import COVERED, survey_game

        rng = random.Random(11)
        kinds = {
            "asset": lambda r: (".png", b"\x89PNG" + r.randbytes(2000)),
            "code": lambda r: (".dll", b"MZ" + r.randbytes(2000)),
            "small": lambda r: (".bin", r.randbytes(100)),
            "dense": lambda r: (".dat", r.randbytes(5000)),
            "structured": lambda r: (".dat", b"rows " * 1000),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root)
            for case in range(8):
                game = root / f"g{case}"
                (game / "sub").mkdir(parents=True)
                want = {}
                for i in range(rng.randint(3, 12)):
                    kind = rng.choice(sorted(kinds))
                    ext, body = kinds[kind](rng)
                    (game / rng.choice(["", "sub"]) / f"f{i}{ext}").write_bytes(body)
                    want[kind] = want.get(kind, 0) + 1
                make_zip(game / "a.zip", {"x.txt": b"x"})
                make_rar(game / "b.rar", {"y.txt": b"y"})  # its tool is made missing below
                locked = game / "locked.bin"
                locked.write_bytes(b"x" * 4000)
                real = Path.stat

                def stat(self, *a, **k):
                    if self.name == "locked.bin" and k.get("follow_symlinks", True) is not False:
                        raise PermissionError(13, "held by an antivirus")
                    return real(self, *a, **k)

                no_rar = {"unarchive.rar": mock.Mock(bound=False)}
                with mock.patch.object(Path, "stat", stat), mock.patch.dict(rt.bindings, no_rar):
                    report = survey_game(rt, game).to_dict()
                cats = {c: v["files"] for c, v in report["categories"].items()}
                self.assertEqual(sum(cats.values()), sum(want.values()) + 3)  # +zip, rar, locked
                self.assertEqual(cats.get("asset", 0), want.get("asset", 0))
                self.assertEqual(cats.get("code", 0), want.get("code", 0))
                self.assertEqual(cats.get("small", 0), want.get("small", 0))
                self.assertEqual(cats.get("unknown-dense", 0), want.get("dense", 0))
                self.assertEqual(cats.get("unreadable"), 1)
                self.assertEqual((cats.get("container"), cats.get("container-no-tool")), (1, 1))
                self.assertIn("unarchive.rar (see `viwo slots`)", report["missingTools"])
                data = sum(
                    v["bytes"]
                    for c, v in report["categories"].items()
                    if c not in ("code", "small")
                )
                covered = sum(report["categories"].get(c, {"bytes": 0})["bytes"] for c in COVERED)
                self.assertAlmostEqual(
                    report["coverage"], round(covered / data, 3) if data else 1.0
                )

    def test_an_engine_without_its_exporter_is_named_and_a_cancel_stops(self) -> None:
        from viwo.contracts import CancelToken, ViwoError
        from viwo.core.survey import GameSurvey, _claimed, survey

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root, "[plugins]\ngeneric = on\nunity = on\n")
            report = GameSurvey(str(root), "unity", 0.9, ())
            unbound = mock.Mock(bound=False)
            with mock.patch.dict(rt.bindings, {"export.unity": unbound}):
                self.assertEqual(_claimed(rt, report, "unity"), frozenset())
            self.assertIn("export.unity exporter (see `viwo slots`)", report.missing)
            from tests.test_unity import fake_unitypy, make_unity_game
            from viwo.core.survey import _examine, _rel, games_in, survey_game

            bound = mock.Mock(bound=True)  # bound at boot only when UnityPy is installed
            with (
                mock.patch.dict("sys.modules", {"UnityPy": fake_unitypy()}),
                mock.patch.dict(rt.bindings, {"export.unity": bound}),
            ):
                unity = survey_game(rt, make_unity_game(root)).to_dict()
            self.assertIn("engine", unity["categories"])  # what its exporter decodes
            self.assertEqual(_rel(GameSurvey(None, "g", 0, ()), root / "x.bin"), "x.bin")
            gone = GameSurvey(str(root), "g", 0, ())
            _examine(gone, [(root / "vanished.bin", "", 9000)], False, CancelToken(), None)
            self.assertEqual(gone.sizes["unreadable"][0], 1)  # gone mid-survey: counted
            (root / "empty").mkdir()
            self.assertEqual(games_in(root / "empty", rt), [])
            lib = make_library(root)
            token = CancelToken()
            token.cancel()
            with self.assertRaises(ViwoError):
                _examine(gone, [(root / "x", "", 1)], False, token, None)
            with self.assertRaises(ViwoError) as err:
                survey(rt, lib, cancel=token)
            self.assertEqual(err.exception.code, "cancelled")


class SurveyTests(unittest.TestCase):
    def test_library_report_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lib = make_library(Path(tmp))
            before = tree_hashes(lib)
            rt = runtime(Path(tmp))
            self.assertEqual([g.name for g in games_in(lib, rt)], ["Doomish", "Odd"])
            self.assertEqual(games_in(lib / "Doomish", rt), [lib / "Doomish"])
            one = Path(tmp) / "one"  # one game whose files sit in folders (bin/, archive/)
            for sub in ("bin/x64/Game.exe", "archive/pc/a.archive", "r6/cache/x.bin"):
                (one / sub).parent.mkdir(parents=True, exist_ok=True)
                (one / sub).write_bytes(b"x")
            self.assertEqual(games_in(one, rt), [one])
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
