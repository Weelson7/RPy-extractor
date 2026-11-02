"""DECODE (after COLLECT): game media into files anything can open (D21, rung 5).

Wwise/FMOD/CRI/XACT/console audio -> WAV (vgmstream, ffmpeg spare), DDS -> PNG (ffmpeg),
Bink -> MP4 (ffmpeg, opt-in: slow). Originals stay; outputs are collected next to them
with provenance "decode:<backend>:<source>". Options: core.decode=off, core.decode_video=on.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from .merger.ffmpeg import FFMPEG
from .pipeline.collect import Source, collect
from .pipeline.failover import run_with_failover
from .pipeline.ticker import Ticker

AUDIO = (".wem", ".fsb", ".bnk", ".xwm", ".xma", ".at3", ".at9", ".adx", ".hca", ".vag", ".awb")
AUDIO += (".acb", ".bfstm", ".bcstm", ".brstm", ".bfwav", ".lopus", ".xwb", ".sab", ".msf")
SLOTS = (
    SlotDefinition(
        "decode.audio", "decode", "core", "vgmstream-cli", "ffmpeg-decode", suffixes=AUDIO
    ),
    SlotDefinition("decode.image", "decode", "core", "ffmpeg-image", suffixes=(".dds",)),
    SlotDefinition("decode.video", "decode", "core", "ffmpeg-video", suffixes=(".bik",)),
)
VGMSTREAM = DependencySpec(
    "vgmstream",
    "vgmstream-cli",
    env_var="VIWO_VGMSTREAM",
    executables=("vgmstream-cli", "vgmstream_cli"),
    install_dirs=("vgmstream", "vgmstream-cli"),
    hint="install vgmstream-cli (ISC) to turn game audio (Wwise, FMOD, CRI...) into WAV",
)


def _count(dest: Path) -> int:
    return sum(1 for p in dest.iterdir() if p.is_file()) if dest.is_dir() else 0


class _CliDecoder(Decoder):
    spec: DependencySpec
    isolation = "subprocess"

    def dependencies(self):
        return (self.spec,)

    def argv(self, path: Path, dest: Path) -> list[str]:
        raise NotImplementedError

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        tool = ctx.os.tools.locate(self.spec)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=self.spec.hint)
        result = ctx.os.process.run(
            [*tool.argv_prefix, *self.argv(path, dest)], timeout=1800, cancel=ctx.cancel
        )
        if not result.ok or not _count(dest):
            return Outcome(OutcomeKind.FAILED, error=(result.stderr or result.stdout)[-300:])
        return Outcome(OutcomeKind.OK, _count(dest))


class VgmstreamCli(_CliDecoder):
    backend_id, license, spec = "vgmstream-cli", "ISC", VGMSTREAM

    def argv(self, path, dest):
        return ["-i", "-S", "0", "-o", str(dest / "?f_?s.wav"), str(path)]


class FfmpegDecode(_CliDecoder):
    backend_id, license, spec, suffix = "ffmpeg-decode", "LGPL-2.1-or-later", FFMPEG, ".wav"

    def argv(self, path, dest):
        return [
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(path),
            str(dest / f"{path.name}{self.suffix}"),
        ]


class FfmpegImage(FfmpegDecode):
    backend_id, suffix = "ffmpeg-image", ".png"


class FfmpegVideo(FfmpegDecode):
    backend_id, suffix = "ffmpeg-video", ".mp4"


def decoders() -> list[Decoder]:
    return [VgmstreamCli(), FfmpegDecode(), FfmpegImage(), FfmpegVideo()]


def decode_all(run, workspace: Path, provenance: list[dict]):
    """Decode collected files in place; returns the collect report of the new files."""
    ctx, rt = run.ctx("core"), run.rt
    if str(ctx.options.get("decode", "on")).lower() in ("off", "false", "0", "no"):
        return None
    video = str(ctx.options.get("decode_video", "off")).lower() in ("on", "true", "1", "yes")
    wanted: dict[str, str] = {}
    for sid in ("decode.audio", "decode.image") + (("decode.video",) if video else ()):
        if sid in rt.bindings and rt.bindings[sid].bound:
            wanted.update(dict.fromkeys(rt.slots[sid].suffixes, sid))
    todo = [p["path"] for p in provenance if Path(p["path"]).suffix.lower() in wanted]
    if not todo:
        return None
    run.log(f"Decoding {len(todo)} file(s) into WAV / PNG / MP4", "decode")

    def one(rel: str) -> Source | None:
        if run.cancel.cancelled:
            return None
        dest = Path(tempfile.mkdtemp(prefix="dec-", dir=run.work))
        binding = rt.bindings[wanted[Path(rel).suffix.lower()]]
        outcome, used = run_with_failover(
            binding, rt.backends, lambda b: b.decode(workspace / rel, dest, ctx)
        )
        if outcome.ok:
            return Source(dest, True, f"decode:{used}:{rel}")
        shutil.rmtree(dest, ignore_errors=True)
        return None

    ticker = Ticker(lambda m: run.log(m, "decode"), "Decoded files:", len(todo))
    sources = []
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as pool:
        for source in pool.map(one, todo):  # in order; a tick per finished file
            ticker.tick()
            if source is not None:
                sources.append(source)
    return collect(sources, workspace, None, set(), run.cancel) if sources else None
