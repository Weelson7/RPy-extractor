"""L3: Bink 2 video through the game's own Bink DLL (decode.bink2). The helper, against a fake
DLL with random sizes and frame counts, feeds the encoder every frame whole and names a refused
file, an encoder that will not start and one that fails; the backend finds the game's DLL, names
a missing DLL or ffmpeg and a run that wrote nothing, and the slot is opt-in like all video.
Verified on real data: Cyberpunk 2077's basegame_5_video.archive (500x500, 299 frames)."""

from __future__ import annotations

import importlib.util
import io
import json
import random
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.contracts.types import OutcomeKind
from viwo.core import decode

spec = importlib.util.spec_from_file_location("decode_bink", decode.BINK_HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class FakeBink:
    """The five Bink calls the helper makes, over a header of width, height and frames."""

    def __init__(self, width: int, height: int, frames: int, opens: bool = True) -> None:
        self.header = struct.pack("<7I", width, height, frames, 1, 0, 30, 1)
        self.opens, self.closed, self.done = opens, 0, 0
        for name in ("BinkOpen", "BinkDoFrame", "BinkNextFrame", "BinkClose", "BinkCopyToBuffer"):
            setattr(self, name, mock.Mock(wraps=getattr(self, f"_{name}")))

    def _BinkOpen(self, name, flags):
        return 1 if self.opens else 0

    def _BinkDoFrame(self, h):
        self.done += 1

    def _BinkNextFrame(self, h):
        pass

    def _BinkClose(self, h):
        self.closed += 1

    def _BinkCopyToBuffer(self, h, buf, pitch, height, x, y, flags):
        return 0


class FakeEncoder:
    def __init__(self, code: int = 0) -> None:
        self.stdin, self.stderr, self.code = io.BytesIO(), io.BytesIO(b"x264 broke"), code
        self.stdin.close = lambda: None

    def wait(self):
        return self.code


class HelperTests(unittest.TestCase):
    def run_helper(self, fake: FakeBink, encoder):
        out = io.StringIO()
        with (
            mock.patch.object(helper.ctypes, "CDLL", return_value=fake),
            mock.patch.object(helper.ctypes, "string_at", return_value=fake.header),
            mock.patch.object(helper, "encoder", side_effect=encoder),
            redirect_stdout(out),
        ):
            code = helper.main("bink2w64.dll", "in.bk2", "out.mp4", ["ffmpeg"])
        return code, json.loads(out.getvalue())

    def test_every_frame_reaches_the_encoder_whole(self) -> None:
        rng = random.Random(4)
        for _ in range(10):
            width, height, frames = rng.randint(1, 64), rng.randint(1, 64), rng.randint(0, 20)
            fake, enc = FakeBink(width, height, frames), FakeEncoder()
            code, said = self.run_helper(fake, lambda *a, e=enc: e)
            self.assertEqual(code, 0)
            self.assertEqual(len(enc.stdin.getvalue()), frames * width * height * 4)
            self.assertEqual((said["frames"], said["width"], said["fps"]), (frames, width, 30.0))
            self.assertEqual((fake.done, fake.closed), (frames, 1))  # the DLL handle is released

    def test_every_failure_has_its_code_and_says_why(self) -> None:
        code, said = self.run_helper(FakeBink(4, 4, 2, opens=False), lambda *a: FakeEncoder())
        self.assertEqual(code, 2)
        self.assertIn("could not open", said["error"])
        fake = FakeBink(4, 4, 2)
        code, said = self.run_helper(fake, OSError("no ffmpeg"))
        self.assertEqual((code, fake.closed), (3, 1))
        self.assertIn("did not start", said["error"])
        code, said = self.run_helper(FakeBink(4, 4, 2), lambda *a: FakeEncoder(code=1))
        self.assertEqual(code, 3)
        self.assertIn("x264 broke", said["error"])

    def test_the_encoder_command_and_a_pipe_ffmpeg_closed(self) -> None:
        with mock.patch.object(helper.subprocess, "Popen") as popen:
            helper.encoder(["ffmpeg"], 499, 301, "30/1", "o.mp4")
        argv = popen.call_args[0][0]
        self.assertEqual(argv[argv.index("-s") + 1], "499x301")
        self.assertIn("pad=ceil(iw/2)*2:ceil(ih/2)*2", argv)  # x264 needs even sizes
        self.assertEqual(argv[-1], "o.mp4")
        enc = FakeEncoder(code=1)
        enc.stdin.write = mock.Mock(side_effect=BrokenPipeError)  # ffmpeg stopped reading
        code, said = self.run_helper(FakeBink(4, 4, 5), lambda *a: enc)
        self.assertEqual(code, 3)  # its exit code and message say why


class BackendTests(unittest.TestCase):
    def test_the_games_dll_is_found_and_every_missing_piece_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "game"
            (game / "bin" / "x64").mkdir(parents=True)
            clip = Path(tmp) / "intro.bk2"
            clip.write_bytes(b"KB2j")
            dest = Path(tmp) / "out"
            dest.mkdir()
            tool = SimpleNamespace(argv_prefix=("ffmpeg",))

            def ctx(run, located=True, root=game):
                host = SimpleNamespace(
                    tools=SimpleNamespace(locate=lambda s: tool if located else None),
                    process=SimpleNamespace(run=run),
                )
                return SimpleNamespace(os=host, game_root=root, cancel=None)

            decode.bink_dll.cache_clear()
            out = decode.BinkGame().decode(clip, dest, ctx(None))
            self.assertIn("no Bink 2 DLL", out.error)
            decode.bink_dll.cache_clear()
            (game / "bin" / "x64" / "bink2w64.dll").write_bytes(b"MZ")
            self.assertEqual(
                decode.BinkGame().decode(clip, dest, ctx(None, False)).kind, OutcomeKind.UNAVAILABLE
            )
            seen = []

            def run(argv, timeout=None, cancel=None, wrote=True):
                seen.append(argv)
                if wrote:
                    Path(argv[5]).write_bytes(b"mp4")
                return SimpleNamespace(
                    ok=wrote, stdout='{"frames": 3}\n' if wrote else "", stderr="crashed"
                )

            ok = decode.BinkGame().decode(clip, dest, ctx(run))
            self.assertEqual((ok.kind, ok.files), (OutcomeKind.OK, 1))
            self.assertEqual(Path(seen[0][3]).name, "bink2w64.dll")  # the game's own decoder
            self.assertIn("video only", ok.notes[0])
            (dest / "intro.bk2.mp4").unlink()
            bad = decode.BinkGame().decode(
                clip, dest, ctx(lambda *a, **k: run(*a, wrote=False, **k))
            )
            self.assertEqual((bad.kind, bad.error), (OutcomeKind.FAILED, "crashed"))

    def test_bink2_is_opt_in_like_all_video(self) -> None:
        from tests.helpers import runtime

        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime(Path(tmp))
            run = SimpleNamespace(rt=rt, ctx=lambda owner: SimpleNamespace(options={}))
            self.assertNotIn(".bk2", decode._wanted(run, {}))
            if rt.bindings["decode.bink2"].bound:
                self.assertEqual(
                    decode._wanted(run, {"decode_video": "on"}).get(".bk2"), "decode.bink2"
                )


if __name__ == "__main__":
    unittest.main()
