"""L3/L6: full pipeline on synthetic games, determinism, CLI, LoC caps (L0)."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.helpers import ROOT, make_game, runtime, tree_hashes, write_ini
from viwo.cli import main as cli_main
from viwo.contracts import LEGACY_RESULT_KEYS, CancelToken, ExtractionRequest, OnExisting, ViwoError
from viwo.contracts import workspace as ws
from viwo.core.pipeline import collect
from viwo.core.pipeline.runner import extract


def run_extract(rt, game: Path, workspace: Path, **kw):
    request = ExtractionRequest(str(game), str(workspace), **kw)
    return extract(rt, request, "job-test", lambda e: None, kw.pop("cancel", CancelToken()))


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.game = make_game(self.root)
        self.rt = runtime(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_extract_keeps_game_untouched_and_blocks_traversal(self) -> None:
        before = tree_hashes(self.game)
        result = run_extract(self.rt, self.game, self.root / "ws")
        self.assertEqual(tree_hashes(self.game), before)
        self.assertFalse((self.root / "escape.txt").exists())
        files = tree_hashes(self.root / "ws", skip_reserved=True)
        self.assertIn("ogg/hello.ogg", files)  # from a zip nested in a zip
        self.assertIn("md/readme.md", files)
        self.assertEqual(result.archives_found, 3)
        payload = result.to_legacy_dict()
        self.assertLessEqual(LEGACY_RESULT_KEYS, set(payload))
        self.assertTrue(Path(result.run_record).exists())
        lines = (self.root / "ws" / ws.PROVENANCE_FILE).read_text().splitlines()
        self.assertEqual(len(lines), result.copied_files)
        self.assertTrue(all(json.loads(line)["sha256"] for line in lines))

    def test_unreadable_file_is_a_warning_not_a_crash(self) -> None:
        real = collect.sha256

        def refuse(path):  # what Windows raises for a file the antivirus holds (WinError 225)
            if path.name == "readme.md":
                raise OSError(22, "the file contains a virus or potentially unwanted software")
            return real(path)

        with mock.patch("viwo.core.pipeline.collect.sha256", refuse):
            result = run_extract(self.rt, self.game, self.root / "ws")
        self.assertTrue(any("could not be read" in w and "readme.md" in w for w in result.warnings))
        self.assertNotIn("md/readme.md", tree_hashes(self.root / "ws", skip_reserved=True))

    def test_tar_links_and_devices_are_never_written(self) -> None:
        """Doc 17.3: symlinks, hard links and device members are filtered, regular files kept."""
        game = self.root / "nasty"
        game.mkdir()
        with tarfile.open(game / "nasty.tar", "w") as tf:
            for name, kind, link in (
                ("sym", tarfile.SYMTYPE, "../../escape"),
                ("hard", tarfile.LNKTYPE, "../x"),
                ("dev", tarfile.CHRTYPE, ""),
            ):
                info = tarfile.TarInfo(name)
                info.type, info.linkname = kind, link
                tf.addfile(info)
            info = tarfile.TarInfo("ok.txt")
            info.size = 2
            tf.addfile(info, io.BytesIO(b"ok"))
        result = run_extract(self.rt, game, self.root / "ws-nasty")
        files = tree_hashes(self.root / "ws-nasty", skip_reserved=True)
        self.assertIn("txt/ok.txt", files)
        self.assertFalse([n for n in files if n.rsplit("/", 1)[-1] in ("sym", "hard", "dev")])
        self.assertFalse((self.root / "escape").exists())
        self.assertEqual(result.archives_extracted, 1)

    def test_nesting_deeper_than_ten_is_reported(self) -> None:
        """Doc 17.3: the depth bomb stops at MAX_DEPTH and is reported, the run still succeeds."""
        game = self.root / "deep"
        game.mkdir()
        data = b"leaf"
        for level in range(13):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr(f"l{level}.zip" if level else "leaf.txt", data)
            data = buf.getvalue()
        (game / "bomb.zip").write_bytes(data)
        result = run_extract(self.rt, game, self.root / "ws-deep")
        warnings = result.to_legacy_dict()["checks"]["warnings"]
        self.assertTrue(any("nesting deeper than 10" in w for w in warnings), warnings)
        self.assertTrue(result.success)

    def test_rerun_needs_decision_and_replace_is_deterministic(self) -> None:
        run_extract(self.rt, self.game, self.root / "ws")
        first = tree_hashes(self.root / "ws", skip_reserved=True)
        with self.assertRaises(ViwoError) as err:
            run_extract(self.rt, self.game, self.root / "ws")
        self.assertEqual(err.exception.code, "needs_decision")
        run_extract(self.rt, self.game, self.root / "ws", on_existing=OnExisting.REPLACE)
        self.assertEqual(tree_hashes(self.root / "ws", skip_reserved=True), first)

    def test_selected_extensions_and_cancel(self) -> None:
        result = run_extract(
            self.rt, self.game, self.root / "ws", selected_exts=frozenset({".ogg"})
        )
        self.assertEqual(dict(result.copied_by_ext), {"ogg": 1})
        token = CancelToken()
        token.cancel()
        with self.assertRaises(ViwoError) as err:
            request = ExtractionRequest(str(self.game), str(self.root / "ws2"))
            extract(self.rt, request, "job-c", lambda e: None, token)
        self.assertEqual(err.exception.code, "cancelled")


class CliTests(unittest.TestCase):
    def cli(self, *args: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli_main(list(args))
        return code, json.loads(out.getvalue())

    def test_info_extract_and_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, ini = make_game(root), str(write_ini(root))
            code, env = self.cli("--ini", ini, "--json", "info")
            self.assertEqual((code, env["ok"]), (0, True))
            code, env = self.cli(
                "--ini", ini, "--json", "extract", str(game), "--workspace", str(root / "ws")
            )
            self.assertEqual((code, env["data"]["extractorType"]), (0, "generic"))
            code, env = self.cli(
                "--ini", ini, "--json", "extract", str(game), "--workspace", str(root / "ws")
            )
            self.assertEqual((code, env["error"]["code"]), (2, "needs_decision"))
            code, env = self.cli(
                "--ini",
                ini,
                "--json",
                "extract",
                str(root / "missing"),
                "--workspace",
                str(root / "ws3"),
            )
            self.assertEqual((code, env["error"]["code"]), (2, "invalid_request"))


class CapsTests(unittest.TestCase):
    def test_loc_caps(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "loc_count.py")], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)


if __name__ == "__main__":
    unittest.main()


class ReplayAndUnpackTests(unittest.TestCase):
    def cli(self, *args: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli_main(list(args))
        return code, json.loads(out.getvalue())

    def test_replay_reproduces_the_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, ini = make_game(root), str(write_ini(root))
            code, env = self.cli(
                "--ini",
                ini,
                "--json",
                "extract",
                str(game),
                "--workspace",
                str(root / "ws"),
                "--option",
                "godot.encryption_key=" + "ab" * 32,
                "--option",
                "generic.level=2",
            )
            self.assertEqual(code, 0)
            record = env["data"]["runRecord"]
            stored = json.loads(Path(record).read_text())["request"]["options"]
            self.assertEqual(
                stored, {"godot": {"encryption_key": "<secret>"}, "generic": {"level": "2"}}
            )
            code, env = self.cli(
                "--ini", ini, "--json", "replay", record, "--workspace", str(root / "again")
            )
            self.assertEqual((code, env["error"]["code"]), (1, "needs_key"))
            code, env = self.cli(
                "--ini",
                ini,
                "--json",
                "replay",
                record,
                "--workspace",
                str(root / "again"),
                "--option",
                "godot.encryption_key=" + "ab" * 32,
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                tree_hashes(root / "again", skip_reserved=True),
                tree_hashes(root / "ws", skip_reserved=True),
            )

    def test_unpack_one_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, ini = make_game(root), str(write_ini(root))
            code, env = self.cli(
                "--ini",
                ini,
                "--json",
                "unpack",
                str(game / "outer.zip"),
                "--out",
                str(root / "out"),
            )
            self.assertEqual((code, env["data"]["archives"]), (0, 2))
            files = tree_hashes(root / "out")
            self.assertTrue(any(k.endswith("voice/hello.ogg") for k in files), files)
            code, env = self.cli(
                "--ini",
                ini,
                "--json",
                "unpack",
                str(game / "outer.zip"),
                "--out",
                str(root / "out"),
            )
            self.assertEqual(env["error"]["code"], "refused")


class HumanOutputTests(unittest.TestCase):
    def test_readable_output_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, ini = make_game(root), str(write_ini(root))
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                cli_main(["--ini", ini, "detect", str(game)])
                cli_main(["--ini", ini, "extract", str(game), "--workspace", str(root / "ws")])
                code = cli_main(
                    ["--ini", ini, "extract", str(game), "--workspace", str(root / "ws")]
                )
            text = out.getvalue()
            self.assertIn("ENGINE", text)
            self.assertIn("Run record", text)
            self.assertEqual(code, 2)
            self.assertIn("--on-existing", err.getvalue())
