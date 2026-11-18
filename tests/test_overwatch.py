"""L3: Overwatch plugin (tos-sensitive): auto-picked with a reminder, run via a fake DataTool,
reminder in every result, repack and capture refused. Real-game tests: independent operator."""

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionMode, ExtractionRequest, ViwoError
from viwo.core.capture import CaptureRequest, capture
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract

FAKE = """#!{python}
import sys
from pathlib import Path
game, mode, out = sys.argv[1:4]
Path(out).mkdir(parents=True, exist_ok=True)
(Path(out) / (mode + ".png")).write_bytes(b"png from " + mode.encode())
"""


class OverwatchTests(unittest.TestCase):
    def test_explicit_only_with_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "Overwatch"
            (game / "data" / "casc").mkdir(parents=True)
            (game / "Overwatch.exe").write_bytes(b"MZ")
            (game / ".build.info").write_text("x")
            tool = root / "fake_datatool.py"
            tool.write_text(FAKE.format(python=sys.executable))
            tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
            if sys.platform == "win32":
                (root / "fake_datatool.cmd").write_text(f'@"{sys.executable}" "{tool}" %*\r\n')
                tool = root / "fake_datatool.cmd"
            ini = "[startup]\nfeatures = extraction, capture\n"
            rt = runtime(
                root,
                ini + f"[tools]\ndatatool = {tool}\n[options.overwatch]\nmodes = extract-maps\n",
            )
            before = tree_hashes(game)
            auto = extract(
                rt,
                ExtractionRequest(str(game), str(root / "a")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertIn("overwatch", [r.plugin_id for r in auto.runs])
            single = ExtractionRequest(
                str(game), str(root / "b"), mode=ExtractionMode.SINGLE, plugins=("overwatch",)
            )
            result = extract(rt, single, "j", lambda e: None, CancelToken())
            self.assertEqual(
                (root / "b" / "png" / "extract-maps.png").read_bytes(), b"png from extract-maps"
            )
            self.assertTrue(any("respect Blizzard" in w for w in result.warnings))
            bad = ExtractionRequest(
                str(game),
                str(root / "d"),
                mode=ExtractionMode.SINGLE,
                plugins=("overwatch",),
                plugin_options={"overwatch": {"modes": "extract-maps,rm -rf /"}},
            )
            rejected = extract(rt, bad, "j", lambda e: None, CancelToken())
            self.assertFalse((root / "d" / "png").exists())
            self.assertTrue(
                any("unknown DataTool mode" in w for w in rejected.warnings), rejected.warnings
            )
            self.assertEqual(tree_hashes(game), before)
            with self.assertRaises(ViwoError) as err:  # no capture backend here: not a refusal
                capture(
                    rt, CaptureRequest(game, game / "Overwatch.exe", root / "c", confirmed=True)
                )
            self.assertEqual(err.exception.code, "unavailable")


class QueryTests(unittest.TestCase):
    def test_each_query_is_one_argument_as_given_and_only_for_extract_modes(self) -> None:
        from viwo.plugins.overwatch import DataToolExporter

        with tempfile.TemporaryDirectory() as tmp:
            for asked in ("", "Tracer|skin=Classic", " A|skin=* ; B b|x=(y) & del ;; "):
                seen = []

                def run(argv, timeout=None, cancel=None, on_line=None, seen=seen):
                    seen.append(argv)
                    return SimpleNamespace(ok=True)

                tool = SimpleNamespace(argv_prefix=("DataTool",))
                ctx = SimpleNamespace(
                    os=SimpleNamespace(
                        tools=SimpleNamespace(locate=lambda spec: tool),
                        process=SimpleNamespace(run=run),
                    ),
                    options={"modes": "list-heroes,extract-unlocks", "query": asked},
                    staging=Path(tmp) / "s",
                    game_root=Path(tmp) / "g",
                    cancel=None,
                    log=lambda *a, **k: None,
                    tool_output=lambda stage, every=0.5: None,
                )
                DataToolExporter().export(ctx)
                want = [q.strip() for q in asked.split(";") if q.strip()]
                self.assertEqual([a[2] for a in seen], ["list-heroes", "extract-unlocks"])
                self.assertEqual((seen[0][4:], seen[1][4:]), ([], want))

    def test_the_steam_layout_is_detected_like_the_battle_net_one(self) -> None:
        from viwo.plugins.overwatch import OverwatchPlugin

        with tempfile.TemporaryDirectory() as tmp:
            steam = Path(tmp) / "Overwatch"
            (steam / "data").mkdir(parents=True)
            for name in ("Overwatch.exe", "data/.build.config", "data/data.000.001"):
                (steam / name).write_bytes(b"x")
            found = OverwatchPlugin().detect(FolderProbe(steam))
            self.assertEqual((found.confidence, len(found.evidence)), (0.95, 2))


if __name__ == "__main__":
    unittest.main()
