"""ffmpeg backend for the media.encode slot: probing, filtergraph, encoding."""

from dataclasses import dataclass
from pathlib import Path

from viwo.contracts.slots import Backend
from viwo.contracts.types import DependencySpec
from viwo.core.pipeline.failover import run_with_failover

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
    backend_id, license, isolation = "ffmpeg", "GPL-3.0-or-later", "subprocess"
    families = frozenset({"media.encode"})

    requires = (FFMPEG, FFPROBE)


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


def probe(rt, path: Path, ctx) -> tuple[float, bool]:
    """(duration in seconds, has an audio stream) through the `media.probe` slot (doc 8.5);
    (0, False) when the slot is unbound or the backend cannot tell."""
    binding = rt.bindings.get("media.probe")
    if binding is None or not binding.bound:
        return 0.0, False
    outcome, _ = run_with_failover(binding, rt.backends, lambda b: b.probe(path, ctx))
    if not outcome.ok:
        return 0.0, False
    facts = [str(n).strip() for n in outcome.notes]
    seconds = 0.0
    for fact in facts:
        if fact.startswith("duration="):
            try:
                seconds = max(float(fact.split("=", 1)[1] or 0), 0.0)
            except ValueError:
                seconds = 0.0
    return seconds, "codec_type=audio" in facts


def _inputs(t: Timeline) -> list[str]:
    lines = []
    for i, d in enumerate(t.durations):
        # the trailing fps restores a constant frame rate after setpts: xfade (ffmpeg 7+) needs one
        lines.append(f"[{i}:v]{VIDEO_CHAIN},trim=duration={d:.3f},setpts=PTS-STARTPTS,fps=30[v{i}]")
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
