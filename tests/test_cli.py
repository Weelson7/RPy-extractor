"""L1: CLI UX: help and welcome, error surface (no tracebacks), exit codes, slots columns."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.helpers import make_zip, write_ini
from viwo import cli, cli_format


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class HelpTests(unittest.TestCase):
    def test_welcome_and_epilog_name_every_entry_point(self) -> None:
        code, out, _ = run([])
        self.assertEqual(code, 0)
        for text in (
            "viwo serve",
            "install --all",
            "--game SLUG",
            "indexes update",
            "diag",
            "capture",
            "config check",
        ):
            self.assertIn(text, out)
        help_text = cli._parser().format_help()
        self.assertIn("exit codes: 0 ok", help_text)
        self.assertIn("130 cancelled", help_text)
        self.assertNotIn("policy-checked", help_text)

    def test_every_positional_argument_has_help(self) -> None:
        parser = cli._parser()
        subparsers = next(a for a in parser._actions if a.dest == "command")
        for name, sub in subparsers.choices.items():
            for action in sub._actions:
                if action.option_strings or action.dest == "help":
                    continue
                self.assertTrue(action.help, f"{name}: positional {action.dest} has no help")


class ErrorSurfaceTests(unittest.TestCase):
    def test_unexpected_exception_is_an_internal_error_not_a_traceback(self) -> None:
        with mock.patch.object(cli, "_run", side_effect=RuntimeError("boom")):
            code, out, err = run(["slots"])
        self.assertEqual(code, 1)
        self.assertIn("viwo: internal: RuntimeError: boom", err)
        self.assertIn("viwo diag", err)
        self.assertNotIn("Traceback", err)

    def test_ctrl_c_is_a_clean_cancel(self) -> None:
        with mock.patch.object(cli, "_run", side_effect=KeyboardInterrupt):
            code, _, err = run(["slots"])
        self.assertEqual(code, 130)
        self.assertIn("viwo: cancelled", err)

    def test_missing_folders_are_not_found_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ini = str(write_ini(Path(tmp), ""))
            missing = str(Path(tmp) / "nowhere")
            for argv in (
                ["sanitize", missing],
                ["survey", missing],
                ["capture", missing, "--exe", "x", "--workspace", tmp],
            ):
                code, _, err = run(["--ini", ini, *argv])
                self.assertEqual(code, 1, argv)
                self.assertIn("viwo: not_found:", err)
                self.assertNotIn("Traceback", err)

    def test_needs_decision_keeps_its_own_hint(self) -> None:
        kept = cli_format.error(
            {"code": "needs_decision", "message": "confirm", "hint": "my hint", "owner": ""}
        )
        self.assertIn("my hint", kept)
        default = cli_format.error(
            {"code": "needs_decision", "message": "exists", "hint": "", "owner": ""}
        )
        self.assertIn("--on-existing", default)


class SlotsFormatTests(unittest.TestCase):
    def test_where_column(self) -> None:
        deps = [
            {
                "id": "repak",
                "available": True,
                "kind": "executable",
                "location": "C:\\x\\third_party\\repak\\repak.exe",
                "hint": "",
                "version": "0.2.3",
            },
            {
                "id": "ffmpeg",
                "available": True,
                "kind": "executable",
                "location": "/usr/bin/ffmpeg",
                "hint": "",
                "version": "7.1",
            },
            {
                "id": "py7zr",
                "available": True,
                "kind": "python",
                "location": "",
                "hint": "pip",
                "version": "1.1.4",
            },
            {
                "id": "unrar",
                "available": False,
                "kind": "executable",
                "location": "",
                "hint": "install unrar",
                "installable": True,
            },
            {
                "id": "ghidra",
                "available": False,
                "kind": "executable",
                "location": "",
                "hint": "install ghidra",
                "installable": False,
            },
        ]
        text = cli_format.slots({"bindings": {}, "dependencies": deps})
        self.assertIn("third_party", text.splitlines()[3])
        self.assertIn("PATH or ini", text)
        self.assertIn("python ", text)
        self.assertIn("pinned: viwo install unrar", text)
        self.assertIn("manual", text)
        self.assertIn("0.2.3", text)


HELLO = Path(__file__).resolve().parent.parent / "examples" / "plugins" / "hello"
PLUGIN_SRC = """
from viwo.contracts.plugin import CliCommand, EnginePlugin, PluginManifest
from viwo.contracts.types import DetectionResult

MANIFEST = PluginManifest("{id}", "{id}", "0.1.0", engine_type="{id}", builtin=False)


class Plugin(EnginePlugin):
    manifest = property(lambda self: MANIFEST)

    def detect(self, probe):
        return DetectionResult("{id}", 0.0, (), "{id}")

    def cli_commands(self):
        return (
            CliCommand(
                "detect",
                "overridden detect",
                lambda p: p.add_argument("game"),
                lambda rt, a: {{"who": "{id}"}},
                override={override},
            ),
        )
"""


def dropin(root: Path, plugin_id: str, override: bool) -> Path:
    folder = root / "user_plugins" / plugin_id
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text(PLUGIN_SRC.format(id=plugin_id, override=override))
    meta = {"id": plugin_id, "module": "__init__", "class": "Plugin", "cli": True, "enabled": True}
    (folder / "plugin.json").write_text(json.dumps(meta))
    return folder.parent


class PluginCommandTests(unittest.TestCase):
    def test_plugin_command_in_help_runs_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom = root / "user_plugins"
            shutil.copytree(HELLO, custom / "hello")
            ini = str(
                write_ini(root, f"[plugins]\ncustom_dirs = {custom.as_posix()}\nhello = on\n")
            )
            archive = make_zip(root / "x.hello", {"a.txt": b"a", "b/c.txt": b"c"})
            with mock.patch.object(cli.sys, "argv", ["viwo", "--ini", ini]):
                self.assertIn(
                    "hello-list", cli._parser(cli.boot_for_cli(["--ini", ini])).format_help()
                )
            code, out, _ = run(["--ini", ini, "hello-list", str(archive)])
            self.assertEqual((code, out.strip().splitlines()), (0, ["a.txt", "b/c.txt"]))
            code, out, _ = run(["--ini", ini, "--json", "hello-list", str(archive)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["data"]["members"], ["a.txt", "b/c.txt"])
            code, _, err = run(["--ini", ini, "hello-list", str(root / "missing.hello")])
            self.assertEqual(code, 1)
            self.assertIn("viwo: not_found", err)

    def test_core_command_clash_and_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            custom = dropin(root / "a", "clasher", override=False)
            ini = str(write_ini(root / "a", f"[plugins]\ncustom_dirs = {custom.as_posix()}\n"))
            code, out, _ = run(["--ini", ini, "--json", "info"])
            self.assertEqual(code, 0)
            self.assertTrue(
                any("command 'detect' exists" in w for w in json.loads(out)["warnings"])
            )
            code, out, _ = run(["--ini", ini, "--json", "detect", str(game)])
            self.assertEqual(code, 0)
            self.assertIn("generic", json.loads(out)["data"])  # the core command still runs
            custom = dropin(root / "b", "overrider", override=True)
            ini = str(write_ini(root / "b", f"[plugins]\ncustom_dirs = {custom.as_posix()}\n"))
            code, out, _ = run(["--ini", ini, "--json", "detect", str(game)])
            self.assertEqual((code, json.loads(out)["data"]), (0, {"who": "overrider"}))
            self.assertIn(
                "overridden detect [overrider]",
                cli._parser(cli.boot_for_cli(["--ini", ini])).format_help(),
            )


if __name__ == "__main__":
    unittest.main()
