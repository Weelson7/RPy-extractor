"""capture.audio (D2): the system's sound output recorded to WAV while a game plays, through the
soundcard package (BSD; WASAPI loopback on Windows, the PulseAudio monitor on Linux)."""

from __future__ import annotations

import time
import warnings
import wave
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.slots import Backend
from viwo.contracts.types import DependencySpec

from .runtime import _enabled

SOUNDCARD = DependencySpec(
    "soundcard",
    "soundcard (audio loopback)",
    kind="python",
    import_name="soundcard",
    hint="install soundcard: `viwo install soundcard`",
)
RATE = 48000


class LoopbackRecorder(Backend):
    """capture.audio: owns the soundcard dependency (preflight, 05 SYSTEM)."""

    backend_id, license, isolation = "soundcard-loopback", "BSD-3-Clause", "inprocess"
    families = frozenset({"capture"})

    def dependencies(self):
        return (SOUNDCARD,)


def record(rt, workspace: Path, seconds: float) -> dict:
    """`seconds` of what the default output device plays, as 16-bit stereo WAV."""
    _enabled(rt)
    try:
        import numpy
        import soundcard
    except ImportError as exc:
        raise ViwoError(
            "unavailable", "audio capture needs soundcard", hint=SOUNDCARD.hint
        ) from exc
    speaker = soundcard.default_speaker()
    loop = soundcard.get_microphone(id=str(speaker.name), include_loopback=True)
    with warnings.catch_warnings():  # "data discontinuity": a dropped buffer, not an error
        warnings.simplefilter("ignore")
        frames = loop.record(samplerate=RATE, numframes=int(RATE * seconds))
    out = workspace.resolve() / ".runtime" / "audio"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"loopback-{time.strftime('%Y%m%d-%H%M%S')}.wav"
    pcm = (numpy.clip(frames, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(pcm.shape[1] if pcm.ndim > 1 else 1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(pcm.tobytes())
    peak = float(numpy.abs(frames).max()) if frames.size else 0.0
    return {
        "wav": str(path),
        "seconds": seconds,
        "device": str(speaker.name),
        "peak": round(peak, 4),
    }
