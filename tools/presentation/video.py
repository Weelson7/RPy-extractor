"""The demo video: the frames of `frames.py` as an MP4 with burned-in captions and no voice,
through ViWo's own pinned ffmpeg (installed by itself when missing). A title card opens it;
every frame stays for its `hold` seconds with its caption in a band under it.

Usage: python tools/presentation/video.py [--frames viwo-data/presentation/frames]
       [--out viwo-data/presentation/ViWo-demo-<version>.mp4] [--title "..."]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from viwo import __version__  # noqa: E402
from viwo.core import thirdparty  # noqa: E402
from viwo.os import select_os  # noqa: E402

FONTS = (
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
FPS, TITLE_SECONDS = 30, 4.0
BAND = 96  # a caption band under the frame: a caption never covers the UI


def ffmpeg() -> list[str]:
    """ViWo's pinned ffmpeg; installed into third_party/ by itself when it is not there."""
    argv = thirdparty.tool_argv("ffmpeg", ROOT)
    if argv is None:
        thirdparty.install_tool("ffmpeg", ROOT, select_os().process, print)
        argv = thirdparty.tool_argv("ffmpeg", ROOT)
    if argv is None:
        raise SystemExit("ffmpeg could not be installed")
    return list(argv)


def font() -> str:
    found = next((f for f in FONTS if Path(f).is_file()), None)
    if found is None:
        raise SystemExit("no font found for the captions")
    return found.replace(":", "\\:")  # a filter argument: the drive colon escaped


def concat_list(steps: list[dict], frames: Path) -> str:
    """The concat demuxer's list: every frame with its duration (the last one repeated, as
    the demuxer wants)."""
    lines = []
    for step in steps:
        lines += [f"file '{(frames / (step['file'] + '.png')).as_posix()}'"]
        lines += [f"duration {step.get('hold', 4.0):.2f}"]
    return "\n".join([*lines, lines[-2]]) + "\n"


def captions(steps: list[dict], work: Path, face: str) -> str:
    """One drawtext per caption, shown while its frame is; the text goes through files so no
    caption needs escaping."""
    filters, start = [], TITLE_SECONDS
    for n, step in enumerate(steps):
        text = work / f"caption{n}.txt"
        text.write_text(step["caption"], encoding="utf-8")
        end = start + step.get("hold", 4.0)
        filters.append(
            f"drawtext=fontfile='{face}':textfile='{text.as_posix().replace(':', chr(92) + ':')}'"
            f":fontsize=30:fontcolor=white:box=1:boxcolor=black@0.72:boxborderw=18"
            f":x=(w-text_w)/2:y=h-{BAND // 2}-th/2:enable='between(t,{start:.2f},{end:.2f})'"
        )
        start = end
    return ",".join(filters)


def title_card(work: Path, face: str, title: str, size: str) -> str:
    text = work / "title.txt"
    text.write_text(title, encoding="utf-8")
    path = text.as_posix().replace(":", "\\:")
    return (
        f"color=c=0x0b0b0f:s={size}:d={TITLE_SECONDS}:r={FPS},"
        f"drawtext=fontfile='{face}':textfile='{path}':fontsize=44:fontcolor=0xff3b3b"
        ":x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=18"
    )


def build(frames: Path, out: Path, title: str) -> Path:
    steps = json.loads((frames / "steps.json").read_text(encoding="utf-8"))
    if not steps:
        raise SystemExit(f"no frames in {frames}: run frames.py first")
    size = subprocess.run(  # every frame has the size of the first
        [*ffmpeg(), "-hide_banner", "-i", str(frames / (steps[0]["file"] + ".png"))],
        capture_output=True, text=True,
    ).stderr  # fmt: skip
    width, height = _size(size)
    face = font()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "frames.txt").write_text(concat_list(steps, frames), encoding="utf-8")
        graph = (
            f"{title_card(work, face, title, f'{width}x{height + BAND}')}[t];"
            f"[0:v]fps={FPS},pad=iw:ih+{BAND}:0:0:color=0x0b0b0f,format=yuv420p[f];"
            "[t]format=yuv420p[tt];"
            f"[tt][f]concat=n=2:v=1:a=0,{captions(steps, work, face)}[v]"
        )
        (work / "graph.txt").write_text(graph, encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        argv = [*ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
        argv += ["-f", "concat", "-safe", "0", "-i", str(work / "frames.txt")]
        argv += ["-filter_complex_script", str(work / "graph.txt"), "-map", "[v]"]
        argv += ["-c:v", "libx264", "-preset", "slow", "-crf", "20", "-movflags", "+faststart"]
        done = subprocess.run([*argv, str(out)], capture_output=True, text=True)
        if done.returncode:
            raise SystemExit(f"ffmpeg failed: {done.stderr[-1500:]}")
    return out


def _size(probe: str) -> tuple[int, int]:
    import re

    found = re.search(r", (\d{2,5})x(\d{2,5})", probe)
    if not found:
        raise SystemExit("could not read the frame size")
    return int(found.group(1)) // 2 * 2, int(found.group(2)) // 2 * 2  # even, for yuv420p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    base = ROOT / "viwo-data" / "presentation"
    ap.add_argument("--frames", type=Path, default=base / "frames")
    ap.add_argument("--out", type=Path, default=base / f"ViWo-demo-{__version__}.mp4")
    ap.add_argument("--title", default=f"ViWo // Vidya Wormhole\nv{__version__}")
    args = ap.parse_args(argv)
    print(
        f"video written: {build(args.frames, args.out, args.title.replace(chr(92) + 'n', chr(10)))}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
