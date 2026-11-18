"""L2: the holes a review found in the local server and the tool runner (2026-11-18).
Properties: a request path is refused before it is resolved, so a UNC or drive name never
makes Windows open a connection; a workspace file is served as inert data (sandboxed, never
sniffed) and ViWo's own page is never framed and runs only its own scripts; a batch tool's
arguments are never cmd's syntax, whatever a game file is called; the options of an owner
the runtime does not know are all masked in the run record."""

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.core.curation import sorting
from viwo.core.pipeline import runner

OUTSIDE = (
    r"\\evil\share\x.js", "//evil/share/x.js", "/etc/passwd", "../x", "a/../../x", "..",
    r"a\..\..\x", "", ".", "/", r"\x",
)  # fmt: skip


class PathTests(unittest.TestCase):
    def test_a_name_is_refused_before_anything_resolves_it(self) -> None:
        rng = random.Random(72)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ws"
            (root / "png").mkdir(parents=True)
            (root / "png" / "a b.png").write_bytes(b"x")
            touched = []
            real = Path.resolve

            def resolve(self, *args, **kwargs):
                touched.append(str(self))
                return real(self, *args, **kwargs)

            names = [*OUTSIDE, *(("C:x", "C:/Windows/win.ini") if os.name == "nt" else ())]
            for name in names:
                self.assertIsNone(ws.relative(name), name)
                touched.clear()
                with mock.patch.object(Path, "resolve", resolve), self.assertRaises(ViwoError):
                    sorting.resolve(root, name)
                self.assertFalse([t for t in touched if "evil" in t or t.startswith("\\\\")], name)
            for _ in range(30):  # what stays inside is found as before, any separators
                parts = [
                    rng.choice(("png", "a b", "x.y", "ü", "q?z")) for _ in range(rng.randint(1, 4))
                ]
                kept = ws.relative(rng.choice(("/", "\\")).join(parts))
                self.assertEqual(kept.parts, tuple(parts))
            self.assertEqual(
                sorting.resolve(root, "png/a%20b.png"), (root / "png" / "a b.png").resolve()
            )

    def test_the_static_route_never_joins_an_unchecked_name(self) -> None:
        from viwo.api import server

        handler = SimpleNamespace(send_error=mock.Mock(), send_file=mock.Mock())
        handler.client_address, handler.token = ("127.0.0.1", 1), "t"
        names = (r"/\\evil\share\x.js", "/../pyproject.toml", "/a/../../x", r"/..\x", "/C:/x")
        with mock.patch.object(Path, "joinpath", side_effect=AssertionError("joined")):
            for name in names:
                handler.send_error.reset_mock()
                server.Handler._static(handler, name)
                handler.send_error.assert_called_once_with(404)
        handler.send_file.assert_not_called()


class HeaderTests(unittest.TestCase):
    def test_workspace_files_are_inert_and_the_page_is_never_framed(self) -> None:
        from viwo.api import peers as server

        self.assertEqual(server.UNTRUSTED["Content-Security-Policy"], "sandbox")  # no script
        self.assertEqual(server.UNTRUSTED["X-Content-Type-Options"], "nosniff")
        page = server.OURS["Content-Security-Policy"]
        for needed in ("frame-ancestors 'none'", "object-src 'none'", "script-src 'self'"):
            self.assertIn(needed, page)
        self.assertNotIn("'unsafe-inline'", page.split("script-src")[1].split(";")[0])
        self.assertNotIn("'unsafe-eval'", page.replace("'wasm-unsafe-eval'", ""))
        self.assertEqual(server.OURS["X-Frame-Options"], "DENY")


@unittest.skipUnless(sys.platform == "win32", "cmd is Windows'")
class BatchTests(unittest.TestCase):
    def test_a_file_name_is_never_cmds_syntax(self) -> None:
        from viwo.os.windows import _batch_line

        with tempfile.TemporaryDirectory() as tmp:
            tool, seen = Path(tmp) / "my tool.bat", Path(tmp) / "seen.json"
            show = Path(tmp) / "show.py"
            show.write_text(
                "import json, sys\nopen(sys.argv[1], 'w').write(json.dumps(sys.argv[2:]))\n"
            )
            tool.write_text(f'@"{sys.executable}" "{show}" "{seen}" %*\r\n')  # as Ghidra's does
            marker = Path(tmp) / "ran.txt"
            hostile = [f"x&echo hit>{marker}&.dll", f"a|echo hit>{marker}", "(b)^c", "d e\\"]
            hostile += ["100%.dll", f"x&&echo hit>{marker}", "plain"]
            line = _batch_line(["cmd", "/c", "call", str(tool), *hostile])
            subprocess.run(line, capture_output=True, text=True, timeout=60)
            self.assertFalse(marker.exists())  # nothing in a name ran
            got = json.loads(seen.read_text())
            self.assertEqual(
                [g for g, h in zip(got, hostile) if "^" not in h],
                [h for h in hostile if "^" not in h],
            )
            self.assertEqual(len(got), len(hostile))  # (`call` doubles a caret: cmd's own quirk)
            with self.assertRaises(ViwoError):
                _batch_line(["cmd", "/c", "call", str(tool), 'a"&calc&"'])
            self.assertEqual(_batch_line(["tool.exe", "a&b"]), ["tool.exe", "a&b"])  # not cmd's


class RecordTests(unittest.TestCase):
    def test_an_unknown_owners_options_are_all_masked(self) -> None:
        option = SimpleNamespace(key="aes_key", kind="secret")
        plain = SimpleNamespace(key="mode", kind="string")
        known = SimpleNamespace(manifest=SimpleNamespace(options=(option, plain)))
        given = {
            "unreal": {"aes_key": "0xSECRET", "mode": "fast"},
            "ue": {"aes_key": "0xSECRET", "anything": "0xALSO"},  # off, or misspelled
        }
        run = SimpleNamespace(
            rt=SimpleNamespace(plugins={"unreal": known}),
            request=SimpleNamespace(plugin_options=given),
        )
        masked = runner._masked_options(run)
        self.assertEqual(masked["unreal"], {"aes_key": runner.SECRET, "mode": "fast"})
        self.assertEqual(set(masked["ue"].values()), {runner.SECRET})
        self.assertNotIn("0x", str(masked))


if __name__ == "__main__":
    unittest.main()
