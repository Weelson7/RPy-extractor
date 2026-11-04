"""L3: DECODE stage: game audio/textures become WAV/PNG next to the originals (fake tools)."""

from __future__ import annotations

import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract

FAKE = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
src = Path(args[-1] if "{tool}" == "vgm" else args[args.index("-i") + 1])
if b"BROKEN" in src.read_bytes():
    sys.exit("cannot decode")
if "{tool}" == "vgm":
    out = Path(args[args.index("-o") + 1].replace("?f", src.name).replace("?s", "1"))
else:
    out = Path(args[-1])
out.write_bytes(b"decoded:" + src.read_bytes())
"""


def tools(folder: Path) -> str:
    lines = []
    for tool, dep in (("vgm", "vgmstream"), ("ff", "ffmpeg")):
        script = folder / f"fake_{tool}.py"
        script.write_text(FAKE.format(python=sys.executable, tool=tool))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        path = script
        if sys.platform == "win32":
            path = folder / f"fake_{tool}.cmd"
            path.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
        lines.append(f"{dep} = {path}")
    return "[tools]\n" + "\n".join(lines) + "\n"


class DecodeTests(unittest.TestCase):
    def test_audio_and_textures_are_decoded_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            (game / "music.wem").write_bytes(b"RIFF-wem")
            (game / "bad.wem").write_bytes(b"BROKEN")
            (game / "logo.dds").write_bytes(b"DDS-tex")
            rt = runtime(root, tools(root))
            events = []
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                events.append,
                CancelToken(),
            )
            # never silent: the failed file is one warning (result and event) naming its slot
            [warning] = [w for w in result.warnings if "could not be decoded" in w]
            self.assertTrue(warning.startswith("1 file(s)") and "decode.audio" in warning)
            self.assertIn("bad.wem", warning)
            self.assertNotIn("music.wem", warning)
            warned = [e for e in events if e.level == "warn" and e.message == warning]
            self.assertEqual(len(warned), 1)
            ws = root / "ws"
            self.assertEqual((ws / "wav" / "music.wem_1.wav").read_bytes(), b"decoded:RIFF-wem")
            self.assertEqual((ws / "png" / "logo.dds.png").read_bytes(), b"decoded:DDS-tex")
            self.assertTrue((ws / "wem" / "music.wem").is_file())  # originals stay
            self.assertEqual(result.copied_by_ext.get("wav"), 1)  # bad.wem: no output, no crash
            lines = (ws / ".extraction_metadata" / "provenance.jsonl").read_text().splitlines()
            origins = {json.loads(line)["origin"] for line in lines}
            self.assertIn("decode:vgmstream-cli:wem/music.wem:music.wem_1.wav", origins)
            off = ExtractionRequest(
                str(game), str(root / "ws2"), plugin_options={"core": {"decode": "off"}}
            )
            extract(rt, off, "j", lambda e: None, CancelToken())
            self.assertFalse((root / "ws2" / "wav").exists())


def _ctx(run, located=True):
    from types import SimpleNamespace

    tool = SimpleNamespace(argv_prefix=("tool",))
    host = SimpleNamespace(
        tools=SimpleNamespace(locate=lambda spec: tool if located else None),
        process=SimpleNamespace(run=run),
    )
    return SimpleNamespace(os=host, cancel=None)


class DecoderBackendTests(unittest.TestCase):
    def test_success_without_output_is_a_named_failure(self) -> None:
        from types import SimpleNamespace

        from viwo.contracts.types import OutcomeKind
        from viwo.core.decode import FfmpegVideo, VgmstreamCli

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for wrote, ok in ((0, True), (2, True), (1, False)):

                def run(argv, timeout=None, cancel=None, wrote=wrote, ok=ok):
                    for i in range(wrote):
                        (dest / f"out{i}.wav").write_bytes(b"RIFF")
                    return SimpleNamespace(ok=ok, stderr="codec unknown", stdout="")

                for f in dest.iterdir():
                    f.unlink()
                out = VgmstreamCli().decode(dest / "a.wem", dest, _ctx(run))
                if ok and wrote:
                    self.assertEqual((out.kind, out.files), (OutcomeKind.OK, wrote))
                else:  # "ok, 0 files" is never a success (never silent)
                    self.assertEqual(out.kind, OutcomeKind.FAILED)
                    self.assertIn("codec unknown", out.error)
            missing = FfmpegVideo().decode(dest / "a.bik", dest, _ctx(None, located=False))
            self.assertEqual(missing.kind, OutcomeKind.UNAVAILABLE)
            self.assertTrue(FfmpegVideo().argv(dest / "a.bik", dest)[-1].endswith("a.bik.mp4"))

    def test_probes_report_exactly_the_files_facts(self) -> None:
        import random
        from types import SimpleNamespace

        from PIL import Image

        from viwo.contracts.types import OutcomeKind
        from viwo.core.decode import FfprobeProbe, PillowProbe

        rng = random.Random(4)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(10):
                fmt = rng.choice(["PNG", "GIF", "BMP"])
                w, h = rng.randint(1, 64), rng.randint(1, 64)
                path = root / f"i{i}.{fmt.lower()}"
                Image.new("RGB", (w, h)).save(path, format=fmt)
                facts = PillowProbe().probe(path, None).notes
                self.assertEqual(facts, (f"format={fmt}", f"width={w}", f"height={h}"))
            (root / "junk.png").write_bytes(b"not an image")
            self.assertEqual(PillowProbe().probe(root / "junk.png", None).kind, OutcomeKind.FAILED)
            said = "format_name=ogg\nduration=1.5\ncodec_type=audio\n[junk]\n"
            answer = SimpleNamespace(ok=True, stdout=said, stderr="")
            out = FfprobeProbe().probe(root / "a.ogg", _ctx(lambda argv, timeout: answer))
            self.assertEqual(out.notes, ("format_name=ogg", "duration=1.5", "codec_type=audio"))
            bad = SimpleNamespace(ok=False, stdout="", stderr="Invalid data")
            out = FfprobeProbe().probe(root / "a.ogg", _ctx(lambda argv, timeout: bad))
            self.assertEqual((out.kind, out.error), (OutcomeKind.FAILED, "Invalid data"))
            gone = FfprobeProbe().probe(root / "a.ogg", _ctx(None, located=False))
            self.assertEqual(gone.kind, OutcomeKind.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
