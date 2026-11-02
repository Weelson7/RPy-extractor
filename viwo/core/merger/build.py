"""Merger builds (v1 /api/media-merger/build semantics), run through the media.encode slot."""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from viwo.contracts.errors import ViwoError
from viwo.contracts.types import ProgressEvent
from viwo.core.curation.trash import trash_files

from .ffmpeg import FFMPEG, Timeline, filtergraph, probe
from .media import AUDIO, PATTERNS, expand, list_entries, media_type

ENCODE = [
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-crf",
    "20",
    "-c:a",
    "aac",
    "-b:a",
    "192k",
    "-movflags",
    "+faststart",
]


@dataclass
class Settings:
    transition: str = "diapo"
    delay: float = 3.0
    cross: float = 0.7
    overlay: str = ""
    volume: float = 0.35
    fadeout: float = 0.0
    hold_last: float = 0.0
    trash_after: bool = False

    @classmethod
    def from_payload(cls, p: dict[str, Any]) -> "Settings":
        def num(key: str, default: float, low: float, high: float = 1e9) -> float:
            try:
                return min(high, max(low, float(p.get(key, default))))
            except (TypeError, ValueError):
                return default

        transition = str(p.get("transitionType", "diapo")).lower()
        return cls(
            "fade" if transition == "fade" else "diapo",
            num("diapoDelay", 3.0, 0.2),
            num("fadeCrossTime", 0.7, 0.05),
            str(p.get("overlaySound", "")).strip(),
            num("overlayVolume", 0.35, 0.0, 1.0),
            num("endFadeoutTime", 0.0, 0.0),
            num("endLastImageTime", 0.0, 0.0),
            bool(p.get("trashAfterBuild", False)),
        )


def output_name(raw: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-") or time.strftime(
        "merged_%Y%m%d_%H%M%S"
    )
    return name if name.lower().endswith(".mp4") else f"{name}.mp4"


def _inputs(workdir: Path, rels: list[str]) -> list[Path]:
    if not rels:
        raise ViwoError("invalid_request", "No selected media files to merge")
    root, files = workdir.resolve(), []
    for rel in rels:
        path = (root / rel).resolve()
        if root not in path.parents:
            raise ViwoError("invalid_request", f"Invalid selected path: {rel}")
        if not path.is_file():
            raise ViwoError("not_found", f"Selected file not found: {rel}")
        if media_type(path.suffix) not in ("image", "video"):
            raise ViwoError(
                "invalid_request", f"Unsupported media type for merge timeline: {path.name}"
            )
        files.append(path)
    return files


def _timeline(os, files: list[Path], s: Settings, overlay: Path | None) -> Timeline:
    durations, audio = [], []
    for path in files:
        seconds, has_audio = (0.0, False) if media_type(path.suffix) == "image" else probe(os, path)
        durations.append(seconds if seconds > 0 else s.delay)
        audio.append(has_audio)
    return Timeline(
        durations,
        audio,
        s.transition,
        s.cross,
        len(files) if overlay else None,
        s.volume,
        s.fadeout,
        s.hold_last,
    )


def _argv(ffmpeg: list[str], files: list[Path], t: Timeline, overlay: Path | None) -> list[str]:
    argv = [*ffmpeg, "-y"]
    for path, seconds in zip(files, t.durations):
        image = media_type(path.suffix) == "image"
        argv += (["-loop", "1", "-t", f"{seconds:.3f}"] if image else []) + ["-i", str(path)]
    return argv + (["-stream_loop", "-1", "-i", str(overlay)] if overlay else [])


def _overlay(s: Settings) -> Path | None:
    if not s.overlay:
        return None
    path = Path(s.overlay).resolve()
    if not path.is_file() or path.suffix.lower() not in AUDIO:
        raise ViwoError("invalid_request", f"Overlay sound must be an audio file: {s.overlay}")
    return path


def _say(sink, message: str) -> None:
    if sink:
        sink(ProgressEvent(message, "info", "core:merger", "merge"))


@dataclass
class Target:
    """Where a build runs: runtime, source folder, output folder and progress sink."""

    rt: Any
    workdir: Path
    outdir: Path
    sink: Any = None


def build_one(tg: Target, rels: list[str], s: Settings, name: str) -> dict:
    rt, workdir, outdir, sink = tg.rt, tg.workdir, tg.outdir, tg.sink
    tool = rt.os.tools.locate(FFMPEG)
    if tool is None or not rt.bindings.get("media.encode") or not rt.bindings["media.encode"].bound:
        raise ViwoError(
            "unavailable", "ffmpeg/ffprobe are required for merger builds", hint=FFMPEG.hint
        )
    files, overlay = _inputs(workdir, rels), _overlay(s)
    _say(sink, f"Probing {len(files)} input(s) for {output_name(name)}")
    timeline = _timeline(rt.os, files, s, overlay)
    graph, video, audio, total = filtergraph(timeline)
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / output_name(name)
    argv = _argv(list(tool.argv_prefix), files, timeline, overlay)
    tail = ["-map", f"[{video}]", "-map", f"[{audio}]", *ENCODE, "-t", f"{total:.3f}", str(target)]
    with tempfile.TemporaryDirectory(dir=rt.temp_root) as tmp:
        if (
            sum(len(a) + 1 for a in argv + tail) + len(graph)
            > rt.os.process.max_command_length // 2
        ):
            script = Path(tmp) / "graph.txt"  # long graphs (v1 WinError 206) go to a file
            script.write_text(graph, encoding="utf-8")
            argv += ["-filter_complex_script", str(script)]
        else:
            argv += ["-filter_complex", graph]
        _say(sink, f"Encoding {total:.1f} s of video with ffmpeg")
        result = rt.os.process.run(argv + tail, timeout=6 * 3600)
    if not result.ok:
        raise ViwoError("failed", f"Merge failed: {(result.stderr or result.stdout)[-800:]}")
    _say(sink, f"Wrote {target.name}")
    trashed = trash_files(workdir, files, "merger") if s.trash_after else 0
    return {
        "success": True,
        "outputPath": str(target),
        "outputName": target.name,
        "mergedCount": len(files),
        "totalDuration": round(total, 3),
        "trashedCount": trashed,
    }


def _per_candidate(tg: Target, payload: dict, s: Settings) -> tuple:
    pattern = str(payload.get("namingPattern", PATTERNS[0])).lower()
    pattern = pattern if pattern in PATTERNS else PATTERNS[0]
    name = str(payload.get("outputName", "")).strip()
    stem, suffix = (Path(name).stem, Path(name).suffix or ".mp4") if name else ("", ".mp4")
    entries, outputs, failures = list_entries(tg.workdir), [], []
    for spec in payload.get("selectedCandidates") or []:
        label = str(spec.get("name", "")).strip()
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("._-") or "candidate"
        try:
            rels = expand(entries, pattern, [spec])
            done = build_one(tg, rels, s, f"{stem}_{safe}{suffix}" if stem else safe)
            outputs.append(
                {"candidateName": label, **{k: v for k, v in done.items() if k != "success"}}
            )
        except ViwoError as exc:
            failures.append({"candidateName": label, "error": exc.message})
    return outputs, failures


def build(rt, workdir: Path, outdir: Path, payload: dict, sink=None) -> dict:
    """selectedPaths -> one output; selectedCandidates -> one output per candidate."""
    tg, s = Target(rt, workdir, outdir, sink), Settings.from_payload(payload)
    if s.transition == "fade" and s.cross >= s.delay:
        raise ViwoError(
            "invalid_request",
            "The crossfade must be shorter than the image hold",
            hint=f"crossfade {s.cross:g} s >= hold {s.delay:g} s",
        )
    if not payload.get("selectedCandidates"):
        rels = [str(p) for p in payload.get("selectedPaths") or []]
        return build_one(tg, rels, s, str(payload.get("outputName", "")).strip())
    outputs, failures = _per_candidate(tg, payload, s)
    if not outputs:
        return {
            "success": False,
            "error": "All selected candidates failed to build",
            "failures": failures,
        }
    result = {
        "success": True,
        "outputs": outputs,
        "builtCount": len(outputs),
        "mergedCount": sum(o["mergedCount"] for o in outputs),
        "trashedCount": sum(o["trashedCount"] for o in outputs),
    }
    if failures:
        result.update(partial=True, failures=failures)
    if len(outputs) == 1:
        result.update({k: outputs[0][k] for k in ("outputPath", "outputName", "totalDuration")})
    return result
