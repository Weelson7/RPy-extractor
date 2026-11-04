"""L3: Cyberpunk 2077's compiled game scripts decompiled (decode.redscripts). The backend asks
redscript for one file per stored script, keeps everything it writes inside the run, counts what
came out and names a missing tool and a run that wrote nothing; end to end through a fake
redscript CLI the scripts land in the workspace, and `decompile = off` leaves the cache as it is.
Verified on real data: the game's `r6/cache/final.redscripts` (1786 scripts)."""

from __future__ import annotations

import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime
from tests.test_redengine import rdar
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts.types import OutcomeKind
from viwo.core.pipeline.runner import extract
from viwo.plugins.redengine.scripts import RedscriptDecompile

FAKE = """import sys
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index("-o") + 1])
for i in range(3):
    (out / "core" / f"m{i}").mkdir(parents=True, exist_ok=True)
    (out / "core" / f"m{i}" / f"Thing{i}.script").write_text("public class Thing {}")
print("INFO [redscript_cli] Output successfully saved")
"""


def fake_redscript(folder: Path) -> Path:
    script = folder / "fake_redscript.py"
    script.write_text(FAKE)
    if sys.platform != "win32":
        script.write_text(f"#!{sys.executable}\n" + FAKE)
        script.chmod(0o755)
        return script
    wrapper = folder / "fake_redscript.cmd"
    wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
    return wrapper


def ctx(run, located: bool = True):
    tool = SimpleNamespace(argv_prefix=("redscript-cli",))
    host = SimpleNamespace(
        tools=SimpleNamespace(locate=lambda s: tool if located else None),
        process=SimpleNamespace(run=run),
    )
    return SimpleNamespace(os=host, cancel=None)


class BackendTests(unittest.TestCase):
    def test_every_script_written_is_counted_and_stays_in_the_run(self) -> None:
        rng = random.Random(9)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "final.redscripts"
            src.write_bytes(b"\0" * 64)
            for n in range(8):
                dest = Path(tmp) / f"out{n}"
                dest.mkdir()
                count = rng.randint(1, 40)

                def run(argv, cwd=None, timeout=None, cancel=None, count=count, dest=dest):
                    self.assertEqual(cwd, str(dest))  # nothing lands beside ViWo
                    self.assertEqual(argv[1:4], ["decompile", "-i", str(src)])
                    self.assertIn("-f", argv)  # one file per stored script
                    out = Path(argv[argv.index("-o") + 1])
                    self.assertEqual(out.parent, dest)
                    for i in range(count):
                        (out / f"d{i % 3}").mkdir(parents=True, exist_ok=True)
                        (out / f"d{i % 3}" / f"s{i}.script").write_text("x")
                    (out / "index.txt").write_text("not a script")
                    return SimpleNamespace(ok=True, stdout="", stderr="")

                got = RedscriptDecompile().decode(src, dest, ctx(run))
                self.assertEqual((got.kind, got.files), (OutcomeKind.OK, count))
                self.assertIn(f"{count} script file(s)", got.notes[0])

    def test_a_missing_tool_and_an_empty_run_are_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "final.redscripts", Path(tmp)
            gone = RedscriptDecompile().decode(src, dest, ctx(None, located=False))
            self.assertEqual(gone.kind, OutcomeKind.UNAVAILABLE)
            self.assertIn("viwo install redscript", gone.error)
            broke = SimpleNamespace(ok=False, stdout="", stderr="ERROR invalid file\n")
            out = RedscriptDecompile().decode(src, dest, ctx(lambda *a, **k: broke))
            self.assertEqual((out.kind, out.error), (OutcomeKind.FAILED, "ERROR invalid file"))
            quiet = SimpleNamespace(ok=True, stdout="", stderr="")
            out = RedscriptDecompile().decode(src, dest, ctx(lambda *a, **k: quiet))
            self.assertEqual(out.error, "redscript wrote nothing")


class PipelineTests(unittest.TestCase):
    def run_game(self, root: Path, extra: str = ""):
        game = root / "cp"
        (game / "archive" / "pc" / "content").mkdir(parents=True)
        (game / "r6" / "cache").mkdir(parents=True)
        (game / "REDprelauncher.exe").write_bytes(b"MZ")
        (game / "archive" / "pc" / "content" / "basegame_1.archive").write_bytes(
            rdar({0x99: [b"KB2jvideo"]})
        )
        (game / "r6" / "cache" / "final.redscripts").write_bytes(b"compiled")
        body = f"[tools]\nredscript = {fake_redscript(root)}\n" + extra
        request = ExtractionRequest(str(game), str(root / "ws"))
        return extract(runtime(root, body), request, "j", lambda e: None, CancelToken())

    def test_the_scripts_land_in_the_workspace_beside_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.run_game(Path(tmp))
            ws = Path(tmp) / "ws"
            self.assertTrue((ws / "redscripts" / "final.redscripts").is_file())  # as shipped
            names = sorted(p.name for p in (ws / "script").iterdir())
            self.assertEqual(names, ["Thing0.script", "Thing1.script", "Thing2.script"])

    def test_decompile_off_leaves_the_cache_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.run_game(Path(tmp), "[options.redengine]\ndecompile = off\n")
            ws = Path(tmp) / "ws"
            self.assertTrue((ws / "redscripts" / "final.redscripts").is_file())
            self.assertFalse((ws / "script").exists())


if __name__ == "__main__":
    unittest.main()
