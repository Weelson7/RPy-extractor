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
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
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


if __name__ == "__main__":
    unittest.main()
