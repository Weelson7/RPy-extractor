"""L3: media merger (ported from v1; filtergraph parity verified against v1 before removal)."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import make_png, runtime
from viwo.contracts import ViwoError
from viwo.core.merger import media
from viwo.core.merger.build import Settings, build
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


class FakeEncodeTests(unittest.TestCase):
    """Builds over random frame sets with the encoder faked: what is built, what failed and
    why, and the command ffmpeg would get, all follow from the request."""

    def setUp(self) -> None:
        from types import SimpleNamespace

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.work = self.root / "ws"
        self.rt = runtime(self.root)
        self.calls, self.fail = [], False

        def run(argv, timeout=None):
            self.calls.append(argv)
            if not self.fail:
                Path(argv[-1]).write_bytes(b"mp4")
            return SimpleNamespace(ok=not self.fail, stderr="encoder broke", stdout="")

        tool = SimpleNamespace(argv_prefix=("ffmpeg",), path="ffmpeg")
        bound = SimpleNamespace(bound=True, main="ffmpeg", spare="")
        for patcher in (
            mock.patch.object(self.rt.os.tools, "locate", return_value=tool),
            mock.patch.dict(self.rt.bindings, {"media.encode": bound}),
            mock.patch.object(self.rt.os.process, "run", run),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_one_output_per_candidate_and_every_failure_named(self) -> None:
        import random

        rng = random.Random(7)
        names = ["hero", "bg", "intro", "end"]
        for name in names:
            for i in range(1, rng.randint(2, 4)):
                make_png(self.work / f"{i:02d}_{name}.png")
        for _ in range(12):  # noqa: B007  (the round names its output folder)
            picked = rng.sample([*names, "ghost"], rng.randint(1, 4))  # ghost: no such frames
            specs = [{"name": n} for n in picked]
            payload = {"selectedCandidates": specs, "diapoDelay": 0.5, "outputName": "reel.mp4"}
            out = build(self.rt, self.work, self.root / f"out{_}", payload)  # earlier videos stay
            real = [n for n in picked if n != "ghost"]
            if not real:
                self.assertFalse(out["success"])
                self.assertEqual([f["candidateName"] for f in out["failures"]], picked)
                continue
            self.assertEqual([o["candidateName"] for o in out["outputs"]], real)
            self.assertEqual(
                [o["outputName"] for o in out["outputs"]], [f"reel_{n}.mp4" for n in real]
            )
            self.assertEqual(out.get("partial", False), "ghost" in picked)
            self.assertEqual("outputPath" in out, len(real) == 1)

    def test_the_command_settings_and_refusals(self) -> None:
        import random

        rng = random.Random(2)
        for i in range(30):  # junk settings never escape their ranges
            junk = lambda: rng.choice([None, "x", -5, 0, 0.1, 3, 99, "2.5", [1]])  # noqa: E731
            s = Settings.from_payload(
                {"diapoDelay": junk(), "fadeCrossTime": junk(), "overlayVolume": junk()}
            )
            self.assertGreaterEqual(s.delay, 0.2)
            self.assertGreaterEqual(s.cross, 0.05)
            self.assertTrue(0.0 <= s.volume <= 1.0)
        for n in range(3):
            make_png(self.work / f"f{n}.png")
        (self.work / "notes.txt").write_text("x")
        sound = self.root / "music.ogg"
        sound.write_bytes(b"OggS")
        rels = [f"f{n}.png" for n in range(3)]
        build(
            self.rt, self.work, self.root / "o", {"selectedPaths": rels, "overlaySound": str(sound)}
        )
        self.assertIn(str(sound.resolve()), self.calls[-1])  # the overlay loops under the video
        with mock.patch.object(type(self.rt.os.process), "max_command_length", 40):
            build(self.rt, self.work, self.root / "o", {"selectedPaths": rels})
        self.assertIn("-filter_complex_script", self.calls[-1])  # long graphs go to a file
        refusals = (
            ({"selectedPaths": []}, "invalid_request"),
            ({"selectedPaths": ["notes.txt"]}, "invalid_request"),
            ({"selectedPaths": ["gone.png"]}, "not_found"),
            ({"selectedPaths": rels, "overlaySound": str(self.root / "x.png")}, "invalid_request"),
        )
        for payload, code in refusals:
            with self.assertRaises(ViwoError) as err:
                build(self.rt, self.work, self.root / "o", payload)
            self.assertEqual(err.exception.code, code, payload)
        self.fail = True
        with self.assertRaises(ViwoError) as err:
            build(self.rt, self.work, self.root / "o", {"selectedPaths": rels})
        self.assertIn("encoder broke", err.exception.message)
        with mock.patch.object(self.rt.os.tools, "locate", return_value=None):
            with self.assertRaises(ViwoError) as err:
                build(self.rt, self.work, self.root / "o", {"selectedPaths": rels})
        self.assertEqual(err.exception.code, "unavailable")


if __name__ == "__main__":
    unittest.main()
