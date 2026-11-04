"""DECODE (after COLLECT): game media into files anything can open (D21, rung 5).

Wwise/FMOD/CRI/XACT/console audio -> WAV (vgmstream, ffmpeg spare), DDS -> PNG (ffmpeg),
Bink -> MP4 (ffmpeg, opt-in: slow). Originals stay; outputs are collected next to them
with provenance "decode:<backend>:<source>". Options: core.decode=off, core.decode_video=on.
A file no backend could decode is counted per slot in one warning (never silent).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from viwo.contracts.plugin import option_bool
from viwo.contracts.slots import Decoder, Prober, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from .merger.ffmpeg import FFMPEG, FFPROBE
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
    SlotDefinition("media.probe", "probe", "core", "ffprobe-probe", "pillow-probe"),
)
PILLOW = DependencySpec(
    "pillow", "Pillow", kind="python", import_name="PIL", hint="pip install pillow"
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
    backend_id, license, spec, suffix = "ffmpeg-decode", "GPL-3.0-or-later", FFMPEG, ".wav"

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


class FfprobeProbe(Prober):
    """media.probe main: ffprobe reports the stream facts (doc 8.3)."""

    backend_id, license, isolation = "ffprobe-probe", "GPL-3.0-or-later", "subprocess"
    self_check_args = ("-version",)

    requires = (FFPROBE,)

    def probe(self, path, ctx) -> Outcome:
        tool = ctx.os.tools.locate(FFPROBE)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=FFPROBE.hint)
        argv = [
            *tool.argv_prefix,
            "-v",
            "error",
            "-show_entries",
            "format=format_name,duration:stream=codec_type",
        ]
        result = ctx.os.process.run(argv + ["-of", "default=nw=1", str(path)], timeout=60)
        if not result.ok:
            return Outcome(OutcomeKind.FAILED, error=(result.stderr or "")[-300:])
        facts = tuple(line.strip() for line in result.stdout.splitlines() if "=" in line)
        return Outcome(OutcomeKind.OK, 1, notes=facts)


class PillowProbe(Prober):
    """media.probe spare: Pillow opens images only (format, width, height)."""

    backend_id, license, parses_untrusted_in_process = "pillow-probe", "HPND", True

    requires = (PILLOW,)

    def probe(self, path, ctx) -> Outcome:
        from PIL import Image

        try:
            with Image.open(path) as image:
                facts = (f"format={image.format}", f"width={image.width}", f"height={image.height}")
        except Exception as exc:  # noqa: BLE001  (any unreadable image)
            return Outcome(OutcomeKind.FAILED, error=str(exc)[-200:])
        return Outcome(OutcomeKind.OK, 1, notes=facts)


def decoders() -> list:
    """Every core decode/probe backend (doc 8.4)."""
    return [
        VgmstreamCli(),
        FfmpegDecode(),
        FfmpegImage(),
        FfmpegVideo(),
        FfprobeProbe(),
        PillowProbe(),
    ]


def _wanted(run, options: dict) -> dict[str, str]:
    """suffix -> bound decode slot: core slots (video opt-in) and plugin-owned decompilers
    (switched by the plugin's `decompile` option, default on)."""
    rt, wanted = run.rt, {}
    video = option_bool(options, "decode_video")
    for sid, slot in rt.slots.items():
        if slot.family != "decode" or not (sid in rt.bindings and rt.bindings[sid].bound):
            continue
        if sid == "decode.video" and not video:
            continue
        if slot.owner != "core":
            if not option_bool(run.ctx(slot.owner).options, "decompile", True):
                continue
        wanted.update(dict.fromkeys(slot.suffixes, sid))
    return wanted


def _decode_one(run, ctx, workspace: Path, rel: str, slot: str) -> tuple[Source | None, str]:
    """(source of the decoded files, "") or (None, why it failed; "" when cancelled)."""
    if run.cancel.cancelled:
        return None, ""
    rt = run.rt
    dest = Path(tempfile.mkdtemp(prefix="dec-", dir=run.work))
    outcome, used = run_with_failover(
        rt.bindings[slot], rt.backends, lambda b: b.decode(workspace / rel, dest, ctx)
    )
    if outcome.fallback:
        run.log(f"{rel}: {outcome.fallback}", "decode", "warn")
    if outcome.ok:
        return Source(dest, True, f"decode:{used}:{rel}"), ""
    shutil.rmtree(dest, ignore_errors=True)
    return None, f"{rel}: {(outcome.error or outcome.kind.value).strip()[-200:]}"


def decode_all(run, workspace: Path, collected) -> None:
    """Decode collected files in place; the new files join the `collected` report, and the
    files no backend could decode become one warning per slot there."""
    ctx = run.ctx("core")
    if not option_bool(ctx.options, "decode", True):
        return
    wanted = _wanted(run, ctx.options)
    todo = [p["path"] for p in collected.provenance if Path(p["path"]).suffix.lower() in wanted]
    if not todo:
        return
    run.log(f"Decoding {len(todo)} file(s) into WAV / PNG / MP4 / RPY", "decode")
    slots = [wanted[Path(rel).suffix.lower()] for rel in todo]
    ticker = Ticker(lambda m: run.log(m, "decode"), "Decoded files:", len(todo))
    sources, failed = [], {}
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as pool:
        done = pool.map(lambda job: _decode_one(run, ctx, workspace, *job), zip(todo, slots))
        for slot, (source, error) in zip(slots, done):  # in order; a tick per finished file
            ticker.tick()
            if source is not None:
                sources.append(source)
            elif error:
                failed.setdefault(slot, []).append(error)
    for slot, errors in failed.items():
        text = f"{len(errors)} file(s) could not be decoded by {slot}: e.g. {errors[0]}"
        run.log(text, "decode", "warn")
        collected.warnings.append(text)
    if sources:
        decoded = collect(sources, workspace, None, set(), run.cancel)
        collected.by_ext.update(decoded.by_ext)
        collected.provenance += decoded.provenance
