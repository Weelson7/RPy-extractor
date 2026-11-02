"""ffmpeg backend for the media.encode slot: probing, filtergraph, encoding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from viwo.contracts.slots import Backend
from viwo.contracts.types import DependencySpec

FFMPEG = DependencySpec(
    "ffmpeg",
    "ffmpeg",
    executables=("ffmpeg",),
    install_dirs=("ffmpeg", "ffmpeg/bin", "Microsoft/WinGet/Links"),  # winget portable links
    hint="install ffmpeg (with ffprobe)",
)
FFPROBE = DependencySpec(
    "ffprobe",
    "ffprobe",
    executables=("ffprobe",),
    install_dirs=("ffmpeg", "ffmpeg/bin", "Microsoft/WinGet/Links"),  # winget portable links
    hint="install ffmpeg (with ffprobe)",
)
VIDEO_CHAIN = (
    "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:"
    "(oh-ih)/2:color=black,fps=30,format=yuv420p,setsar=1"
)
AUDIO_FMT = "aformat=sample_rates=48000:channel_layouts=stereo,aresample=48000"


class FfmpegBackend(Backend):
    backend_id, license, isolation = "ffmpeg", "LGPL-2.1-or-later", "subprocess"
    families = frozenset({"media.encode"})

    def dependencies(self):
        return (FFMPEG, FFPROBE)


@dataclass
class Timeline:
    durations: list[float]
    has_audio: list[bool]
    transition: str = "diapo"  # diapo | fade
    cross: float = 0.7
    overlay_index: int | None = None
    overlay_volume: float = 0.35
    fadeout: float = 0.0
    hold_last: float = 0.0


def probe(os, path: Path) -> tuple[float, bool]:
    """(duration in seconds, has an audio stream) via ffprobe; (0, False) when unknown."""
    tool = os.tools.locate(FFPROBE)
    if tool is None:
        return 0.0, False
    base = [*tool.argv_prefix, "-v", "error", "-of", "default=noprint_wrappers=1:nokey=1"]
    duration = os.process.run([*base, "-show_entries", "format=duration", str(path)], timeout=60)
    audio = os.process.run(
        [*base, "-select_streams", "a:0", "-show_entries", "stream=codec_type", str(path)],
        timeout=60,
    )
    try:
        seconds = max(float(duration.stdout.strip() or 0), 0.0) if duration.ok else 0.0
    except ValueError:
        seconds = 0.0
    return seconds, audio.ok and "audio" in audio.stdout.lower()


def _inputs(t: Timeline) -> list[str]:
    lines = []
    for i, d in enumerate(t.durations):
        lines.append(f"[{i}:v]{VIDEO_CHAIN},trim=duration={d:.3f},setpts=PTS-STARTPTS[v{i}]")
        lines.append(
            f"[{i}:a]{AUDIO_FMT},atrim=duration={d:.3f},asetpts=N/SR/TB[a{i}]"
            if t.has_audio[i]
            else f"anullsrc=r=48000:cl=stereo,atrim=duration={d:.3f}[a{i}]"
        )
    return lines


def _join(t: Timeline, lines: list[str]) -> tuple[str, str, float]:
    n = len(t.durations)
    if n == 1:
        return "v0", "a0", t.durations[0]
    if t.transition != "fade":
        lines.append(
            "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vcat][acat]"
        )
        return "vcat", "acat", sum(t.durations)
    video, audio, length = "v0", "a0", t.durations[0]
    for i in range(1, n):
        cross = min(
            max(0.05, t.cross),
            max(0.05, t.durations[i - 1] - 0.05),
            max(0.05, t.durations[i] - 0.05),
        )
        lines.append(
            f"[{video}][v{i}]xfade=transition=fade:duration={cross:.3f}:"
            f"offset={max(0.0, length - cross):.3f}[vx{i}]"
        )
        lines.append(f"[{audio}][a{i}]acrossfade=d={cross:.3f}:c1=tri:c2=tri[ax{i}]")
        video, audio, length = f"vx{i}", f"ax{i}", length + t.durations[i] - cross
    return video, audio, length


def filtergraph(t: Timeline) -> tuple[str, str, str, float]:
    """(graph, video label, audio label, total duration) -- same output as v1."""
    lines = _inputs(t)
    video, audio, total = _join(t, lines)
    if t.overlay_index is not None:
        lines.append(
            f"[{t.overlay_index}:a]{AUDIO_FMT},volume={t.overlay_volume:.3f},"
            f"atrim=duration={total:.3f},asetpts=N/SR/TB[bgm]"
        )
        lines.append(f"[{audio}][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        audio = "aout"
    if t.hold_last > 0:
        lines.append(f"[{video}]tpad=stop_mode=clone:stop_duration={t.hold_last:.3f}[vend_hold]")
        video, total = "vend_hold", total + t.hold_last
    fade = min(max(0.0, t.fadeout), total)
    if fade > 0:
        start = max(0.0, total - fade)
        lines.append(f"[{video}]fade=t=out:st={start:.3f}:d={fade:.3f}[vend_fade]")
        lines.append(f"[{audio}]afade=t=out:st={start:.3f}:d={fade:.3f}[aend_fade]")
        video, audio = "vend_fade", "aend_fade"
    return ";".join(lines), video, audio, total
