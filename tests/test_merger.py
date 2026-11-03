"""L3: media merger (ported from v1; filtergraph parity verified against v1 before removal)."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_png, runtime
from viwo.contracts import ViwoError
from viwo.core.merger import media
from viwo.core.merger.build import build
from viwo.core.merger.ffmpeg import Timeline, filtergraph


def media_folder(root: Path) -> Path:
    folder = root / "ws"
    for name in ("01_hero.png", "01_hero.mp4", "02_hero.png", "bg 1.png", "bg 2.png"):
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(b"x")
    (folder / ".trash" / "03_hero.png").parent.mkdir(parents=True)
    (folder / ".trash" / "03_hero.png").write_bytes(b"x")
    return folder


class MergerLogicTests(unittest.TestCase):
    def test_candidates_conflicts_and_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entries = media.list_entries(media_folder(Path(tmp)))
            self.assertEqual(len(entries), 5)  # reserved folders are ignored
            hero = next(
                c for c in media.candidates(entries, "number-to-name") if c["name"] == "hero"
            )
            self.assertEqual([c["index"] for c in hero["conflicts"]], ["01"])
            spec = {
                "name": "hero",
                "entiretyTimes": 2,
                "partLoops": [{"indexes": "02", "times": 2}],
                "conflictResolutions": {"01": ["01_hero.png", "01_hero.mp4"]},
            }
            once = ["01_hero.png", "01_hero.mp4", "02_hero.png", "02_hero.png"]
            self.assertEqual(media.expand(entries, "number-to-name", [spec]), once * 2)
            bg = media.candidates(entries, "name-to-number")
            self.assertIn("bg", [c["name"] for c in bg])

    def test_filtergraph_shape(self) -> None:
        graph, video, audio, total = filtergraph(
            Timeline([2.0, 3.0], [False, True], "fade", 0.5, 2, 0.35, 1.0, 0.5)
        )
        self.assertEqual((video, audio, round(total, 3)), ("vend_fade", "aend_fade", 5.0))
        self.assertIn("xfade=transition=fade:duration=0.500:offset=1.500", graph)
        self.assertIn("[2:a]aformat", graph)
        self.assertIn("tpad=stop_mode=clone:stop_duration=0.500", graph)


class ProbeSlotTests(unittest.TestCase):
    def test_probe_goes_through_the_media_probe_slot(self) -> None:
        """Doc 8.5: the merger reads duration and audio from whatever `media.probe` binds."""
        from viwo.contracts import Outcome, OutcomeKind, SlotBinding
        from viwo.contracts.slots import Prober
        from viwo.core.merger.build import _probe_ctx, output_name
        from viwo.core.merger.ffmpeg import probe

        class FakeProbe(Prober):
            backend_id, owner, license = "fake-probe", "core", "MIT"

            def dependencies(self):
                return ()

            def available(self, os):
                return True, ""

            def probe(self, path, ctx):
                facts = ("format_name=mov", "duration=2.5", "codec_type=video", "codec_type=audio")
                return Outcome(OutcomeKind.OK, 1, notes=facts)

        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime(Path(tmp))
            rt.backends["fake-probe"] = FakeProbe()
            rt.bindings["media.probe"] = SlotBinding("media.probe", "fake-probe")
            ctx = _probe_ctx(rt, Path(tmp), None)
            self.assertEqual(probe(rt, Path(tmp) / "a.mp4", ctx), (2.5, True))
            rt.bindings["media.probe"] = SlotBinding("media.probe", "")
            self.assertEqual(probe(rt, Path(tmp) / "a.mp4", ctx), (0.0, False))
            self.assertEqual(output_name("re:el?", rt.os.fs).endswith(".mp4"), True)
            self.assertTrue(rt.os.fs.is_valid_filename(output_name("a<b>c", rt.os.fs)))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg + ffprobe")
class MergerBuildTests(unittest.TestCase):
    def test_build_from_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "ws"
            make_png(work / "01_frame.png")
            make_png(work / "02_frame.png", rgb=(62, 242, 224))
            rt = runtime(root)
            payload = {
                "selectedPaths": ["01_frame.png", "02_frame.png"],
                "diapoDelay": 0.5,
                "transitionType": "fade",
                "fadeCrossTime": 0.2,
                "outputName": "reel",
                "trashAfterBuild": True,
            }
            result = build(rt, work, root / "out", payload)
            self.assertTrue(Path(result["outputPath"]).stat().st_size > 0)
            self.assertEqual((result["outputName"], result["mergedCount"]), ("reel.mp4", 2))
            self.assertEqual(result["trashedCount"], 2)
            self.assertTrue((work / ".trash/merger/01_frame.png").exists())
            with self.assertRaises(ViwoError):
                build(rt, work, root / "out", {"selectedPaths": ["../escape.png"]})

    def test_progress_events_and_timing_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "ws"
            make_png(work / "01_frame.png")
            rt, events = runtime(root), []
            payload = {"selectedPaths": ["01_frame.png"], "diapoDelay": 0.4, "outputName": "one"}
            build(rt, work, root / "out", payload, events.append)
            self.assertEqual([e.stage for e in events], ["merge"] * 3)
            bad = {**payload, "transitionType": "fade", "fadeCrossTime": 0.5}
            with self.assertRaises(ViwoError) as err:
                build(rt, work, root / "out", bad)
            self.assertIn("crossfade", err.exception.message)


if __name__ == "__main__":
    unittest.main()
