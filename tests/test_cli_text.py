"""L1/L3: never silent in text mode: for real runs of every command with its own text form, the
text says what the --json envelope carries (counts, failures, warnings, the error), the exit
code is the same in both modes, and no traceback ever reaches the user."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import ROOT, make_game, make_zip, runtime, write_ini
from tests.test_cli import run
from tests.test_renpy import make_rpa
from tests.test_sanitizer import make_workspace
from tests.test_survey import make_library
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract


class TextTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ini = str(write_ini(self.root))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def both(self, argv: list[str], fresh=None) -> tuple[dict, str]:
        """The envelope (--json) and the text of one command; `fresh` rebuilds what a run
        consumes (an output folder, an applied plan) between the two runs."""
        code_j, out_j, _ = run(["--json", "--ini", self.ini, *argv])
        if fresh:
            fresh()
        code_t, out_t, err_t = run(["--ini", self.ini, *argv])
        env, text = json.loads(out_j), out_t + err_t
        self.assertEqual(code_j, code_t, argv)
        self.assertNotIn("Traceback", text)
        for warning in env["warnings"]:
            self.assertIn(str(warning), text)
        if not env["ok"]:
            self.assertIn(env["error"]["message"], text)
        return env, text

    def test_unpack_says_every_count_backend_and_failure(self) -> None:
        game = make_game(self.root)
        out = self.root / "u"
        env, text = self.both(
            ["unpack", str(game / "outer.zip"), "--out", str(out)],
            fresh=lambda: __import__("shutil").rmtree(out),
        )
        data = env["data"]
        self.assertIn(str(data["files"]), text)
        for backend, n in data["byBackend"].items():
            self.assertIn(f"{backend} x{n}", text)
        for failure in data["failures"]:
            self.assertIn(failure, text)
        bad = self.root / "bad.zip"
        bad.write_bytes(b"not a zip")
        env, _ = self.both(["unpack", str(bad), "--out", str(self.root / "b")])
        self.assertFalse(env["ok"])

    def test_survey_names_every_game_engine_and_the_coverage_total(self) -> None:
        lib = make_library(self.root)
        env, text = self.both(["survey", str(lib)])
        games = env["data"]["games"]
        for g in games:
            self.assertIn(g["path"], text)
            self.assertIn(g["engine"], text)
            for u in g["unknown"]:
                self.assertIn(u["file"], text)
            for missing in g["missingTools"]:
                self.assertIn(missing, text)
        covered = sum(1 for g in games if g["coverage"] >= 0.99)
        self.assertIn(f"{covered}/{len(games)} game(s) fully covered", text)
        (self.root / "empty").mkdir()
        _, text = self.both(["survey", str(self.root / "empty")])
        self.assertIn("No games found", text)

    def test_sanitize_plan_apply_undo_say_each_finding_and_the_undo_token(self) -> None:
        ws = make_workspace(self.root)
        env, text = self.both(["sanitize", str(ws)])
        for f in env["data"]["findings"]:
            self.assertIn(f["path"], text)
        code, out, _ = run(["--ini", self.ini, "sanitize", str(ws), "--apply"])
        self.assertEqual(code, 0)
        token = out.rsplit("--undo ", 1)[1].split()[0]  # the text names how to undo it
        code, out, _ = run(["--ini", self.ini, "sanitize", str(ws), "--undo", token])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"Restored \d+ file")

    def test_repack_plan_and_build_say_every_container_and_the_verdict(self) -> None:
        game = self.root / "vn"
        (game / "game").mkdir(parents=True)
        (game / "renpy").mkdir()
        make_rpa(game / "game" / "archive.rpa", {"images/bg.png": b"old-bg"}, prefix_len=2)
        ws = self.root / "ws"
        rt = runtime(self.root)
        extract(rt, ExtractionRequest(str(game), str(ws)), "j", lambda e: None, CancelToken())
        (ws / "png" / "bg.png").write_bytes(b"NEW-BG")
        env, text = self.both(["repack", str(ws), "--plan"])
        for item in env["data"]["plan"]:
            self.assertIn(item["container"] or "loose files", text)
            self.assertIn(item["slot"], text)
        out = self.root / "patched"
        env, text = self.both(
            ["repack", str(ws), "--out", str(out)],
            fresh=lambda: __import__("shutil").rmtree(out),
        )
        self.assertTrue(env["data"]["verified"])
        self.assertIn("verified", text)
        env, _ = self.both(["repack", str(ws)])  # neither --out nor --plan
        self.assertEqual(env["error"]["code"], "invalid_request")

    def test_slots_check_has_one_row_per_check(self) -> None:
        env, text = self.both(["slots", "--check"])
        if env["ok"]:
            rows = [x for x in text.splitlines() if x.split()[:1] and "." in x.split()[0]]
            self.assertEqual(len(rows), len(env["data"]["checks"]))
            self.assertIn(f"{len(env['data']['checks'])} backend(s) checked", text)

    def test_config_check_and_generate(self) -> None:
        env, _ = self.both(["config", "check", str(ROOT / "startup.ini")])
        self.assertTrue(env["ok"], env)
        env, text = self.both(["config", "check", self.ini])  # not named <os>-<profile>.ini
        self.assertIn("<os>-<profile>", text)
        broken = self.root / "broken.ini"
        broken.write_text("[startup]\nfeatures = nonsense\n[plugins]\nnope = maybe\n")
        env, text = self.both(["config", "check", str(broken)])
        self.assertFalse(env["ok"])
        self.assertIn(env["error"]["hint"].split(";")[0][:40], text)  # the first problem said
        out = self.root / "distros"
        env, _ = self.both(["config", "generate", str(out)])
        self.assertTrue(env["ok"])
        self.assertEqual(sorted(p.name for p in out.iterdir()), env["data"]["written"])

    def test_install_names_unknown_ids_and_every_failure(self) -> None:
        env, text = self.both(["install", "no-such-tool"])
        self.assertFalse(env["ok"])
        self.assertIn("no-such-tool", text)
        env, _ = self.both(["install"])  # nothing asked
        self.assertFalse(env["ok"])
        from viwo.core import preflight

        def install(rt, dep, note, cancel=None):
            if dep.startswith("a"):
                raise preflight.ViwoError("failed", f"{dep} broke", hint="why")
            return {"installed": dep}

        items = [{"id": i, "available": False, "installable": True} for i in ("ab", "cd")]
        with (
            mock.patch.object(preflight, "check", lambda rt, note: items),
            mock.patch.object(preflight, "install", install),
        ):
            env, text = self.both(["install", "--all"])
        self.assertEqual(env["data"]["installed"], ["cd"])
        self.assertEqual(env["data"]["failed"], {"ab": "ab broke (why)"})
        self.assertIn("ab broke", text)

    def test_replay_of_a_broken_record_and_diag(self) -> None:
        record = self.root / "run.json"
        record.write_text("{not json")
        env, text = self.both(["replay", str(record), "--workspace", str(self.root / "w")])
        self.assertEqual(env["error"]["code"], "invalid_request")
        self.assertIn("not a ViWo run record", text)
        out = self.root / "diag.zip"
        env, text = self.both(["diag", "--out", str(out)])
        self.assertTrue(env["ok"])
        self.assertTrue(out.is_file())
        self.assertIn(str(out), text)

    def test_indexes_update_says_where_it_went(self) -> None:
        done = {"tag": "v1.2.0", "where": str(self.root / "indexes")}
        with mock.patch("viwo.core.indexes.update_indexes", return_value=done):
            env, text = self.both(["indexes", "update"])
        self.assertEqual(env["data"]["tag"], "v1.2.0")
        self.assertIn("v1.2.0", text)

    def test_unpack_not_a_known_archive_is_named(self) -> None:
        plain = make_zip(self.root / "x.zip", {"a.txt": b"a"})
        plain.write_bytes(b"plain text, no archive")
        env, text = self.both(["unpack", str(plain), "--out", str(self.root / "o")])
        self.assertFalse(env["ok"])
        missing = self.root / "gone.zip"
        env, _ = self.both(["unpack", str(missing), "--out", str(self.root / "o2")])
        self.assertEqual(env["error"]["code"], "invalid_request")


class ExtractReplayTests(unittest.TestCase):
    def test_a_replay_rebuilds_the_same_workspace_and_asks_for_its_secrets(self) -> None:
        """Whatever the mode and the extension filter, the run record replays into the same
        files; a secret is never stored, so a replay without it is refused, never run blind."""
        import random

        from tests.helpers import tree_hashes

        rng = random.Random(6)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ini = str(write_ini(root, "[plugins]\ngeneric = on\ngodot = on\n"))
            game = make_game(root)
            for i in range(4):
                exts = rng.sample([".png", ".ogg", ".md", ".txt"], rng.randint(1, 3))
                mode = rng.choice([[], ["--plugin", "generic"], ["--mixed", "generic, godot"]])
                secret = ["--option", "godot.encryption_key=" + "ab" * 16]
                ws, again = root / f"ws{i}", root / f"again{i}"
                argv = ["--quiet", "--ini", ini, "extract", str(game), "--workspace", str(ws)]
                code, _, err = run([*argv, "--exts", ",".join(exts), *mode, *secret])
                self.assertEqual(code, 0, err)
                kept = {Path(p).suffix for p in tree_hashes(ws, skip_reserved=True)}
                self.assertLessEqual(kept, set(exts))  # only the selected extensions
                record = next((ws / ".extraction_metadata" / "runs").glob("*.json"))
                self.assertNotIn("abab", record.read_text(encoding="utf-8"))
                replay = ["--quiet", "--ini", ini, "replay", str(record), "--workspace", str(again)]
                code, _, err = run(replay)
                self.assertNotEqual(code, 0)
                self.assertIn("godot.encryption_key", err)  # it says which secret to pass
                code, _, err = run([*replay, *secret])
                self.assertEqual(code, 0, err)
                self.assertEqual(
                    tree_hashes(again, skip_reserved=True), tree_hashes(ws, skip_reserved=True)
                )

    def test_queries_and_the_verbose_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ini = str(write_ini(root))
            rt = runtime(root)
            code, out, err = run(["--verbose", "--ini", ini, "info"])
            self.assertEqual(code, 0)
            for slot, b in rt.bindings.items():  # every binding in the verbose header
                self.assertIn(f"[CLI] {slot}: {b.main or '-'} / {b.spare or '-'}", err)
            code, out, _ = run(["--json", "--ini", ini, "slots"])
            deps = json.loads(out)["data"]["dependencies"]
            self.assertEqual(len({d["id"] for d in deps}), len(deps))  # each tool once
            game = make_game(root)
            code, out, _ = run(["--json", "--ini", ini, "detect", str(game)])
            scores = json.loads(out)["data"]
            self.assertIn("generic", scores)
            code, _, err = run(["--ini", ini, "detect", str(root / "nowhere")])
            self.assertEqual(code, 2)
            self.assertIn("not found", err)


if __name__ == "__main__":
    unittest.main()
