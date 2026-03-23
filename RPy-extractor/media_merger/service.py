"""Core media merger service for listing candidates and building merged videos."""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from models import AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS


EXTRA_VIDEO_EXTS = {".avi", ".mkv", ".flv", ".3gp", ".ts", ".m2ts"}
EXTRA_IMAGE_EXTS = {".tif", ".tiff", ".heic", ".avif"}
EXTRA_AUDIO_EXTS = {".wma", ".aiff", ".aif", ".mid", ".midi"}

MERGE_VIDEO_EXTS = {ext.lower() for ext in (VIDEO_EXTS | EXTRA_VIDEO_EXTS)}
MERGE_IMAGE_EXTS = {ext.lower() for ext in (IMAGE_EXTS | EXTRA_IMAGE_EXTS)}
MERGE_AUDIO_EXTS = {ext.lower() for ext in (AUDIO_EXTS | EXTRA_AUDIO_EXTS)}
MERGE_MEDIA_EXTS = MERGE_VIDEO_EXTS | MERGE_IMAGE_EXTS


def _natural_parts(value: str) -> list[Any]:
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r"(\d+)", value)]


def _infer_media_type(ext: str) -> str:
    ext_lower = ext.lower()
    if ext_lower in MERGE_IMAGE_EXTS:
        return "image"
    if ext_lower in MERGE_VIDEO_EXTS:
        return "video"
    if ext_lower in MERGE_AUDIO_EXTS:
        return "audio"
    return "other"


def _extract_group(stem: str, pattern: str) -> tuple[str, str]:
    trimmed = stem.strip()
    if not trimmed:
        return "untitled", ""

    if pattern == "number-to-name":
        match = re.match(r"^(?P<idx>\d+)[\s._-]*(?P<name>.+)$", trimmed)
    else:
        match = re.match(r"^(?P<name>.+?)[\s._-]*(?P<idx>\d+)$", trimmed)

    if not match:
        return trimmed, ""

    name = str(match.groupdict().get("name", "")).strip(" _.-")
    idx = str(match.groupdict().get("idx", "")).strip()
    if not name:
        name = trimmed
    return name, idx


def _ffprobe_duration_seconds(path: Path) -> float:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return 0.0

    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return 0.0
        return max(float(result.stdout.strip() or "0"), 0.0)
    except Exception:
        return 0.0


def _find_ffmpeg() -> tuple[str | None, str | None]:
    return shutil.which("ffmpeg"), shutil.which("ffprobe")


def list_media_entries(working_dir: Path, allowed_exts: set[str] | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not working_dir.exists() or not working_dir.is_dir():
        return entries

    normalized_exts = {ext.lower() for ext in (allowed_exts or MERGE_MEDIA_EXTS)}

    for file_path in working_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if ".trash" in {part.lower() for part in file_path.parts}:
            continue

        ext = file_path.suffix.lower()
        if ext not in normalized_exts:
            continue

        rel = file_path.relative_to(working_dir).as_posix()
        entries.append(
            {
                "path": rel,
                "name": file_path.name,
                "stem": file_path.stem,
                "ext": ext,
                "type": _infer_media_type(ext),
            }
        )

    entries.sort(key=lambda item: _natural_parts(str(item.get("path", ""))))
    return entries


def summarize_extensions(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for entry in entries:
        ext = str(entry.get("ext", "")).lower()
        if not ext:
            continue
        counts[ext] = counts.get(ext, 0) + 1

    summary = [{"ext": ext, "count": count} for ext, count in counts.items()]
    summary.sort(key=lambda item: _natural_parts(str(item["ext"])))
    return summary


def build_candidates(entries: list[dict[str, Any]], naming_pattern: str, include_files: bool = True) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}

    for entry in entries:
        stem = str(entry.get("stem", ""))
        group_name, index = _extract_group(stem, naming_pattern)
        key = group_name.lower()

        if key not in groups:
            groups[key] = {
                "name": group_name,
                "indexes": [],
                "files": [],
            }

        groups[key]["files"].append(entry)
        if index and index not in groups[key]["indexes"]:
            groups[key]["indexes"].append(index)

    candidates: list[dict[str, Any]] = []
    for _, group in sorted(groups.items(), key=lambda item: _natural_parts(item[1]["name"])):
        files = sorted(group["files"], key=lambda item: _natural_parts(str(item.get("name", ""))))
        indexes = sorted(group["indexes"], key=_natural_parts)

        index_buckets: dict[str, list[dict[str, Any]]] = {}
        for file_entry in files:
            parsed_name, parsed_index = _extract_group(str(file_entry.get("stem", "")), naming_pattern)
            if parsed_index:
                index_buckets.setdefault(parsed_index, []).append(file_entry)

        conflicts: list[dict[str, Any]] = []
        for idx in sorted(index_buckets.keys(), key=_natural_parts):
            indexed_files = index_buckets[idx]
            media_types = {str(item.get("type", "")) for item in indexed_files}
            if len(indexed_files) <= 1 or len(media_types) <= 1:
                continue

            conflicts.append(
                {
                    "index": idx,
                    "options": [
                        {
                            "path": str(item["path"]),
                            "ext": str(item.get("ext", "")),
                            "type": str(item.get("type", "")),
                        }
                        for item in sorted(indexed_files, key=lambda file_item: _natural_parts(str(file_item.get("name", ""))))
                    ],
                }
            )

        files_payload = [
            {
                "path": f["path"],
                "ext": f["ext"],
                "type": f["type"],
                "parsedIndex": _extract_group(str(f.get("stem", "")), naming_pattern)[1],
            }
            for f in files
        ]

        candidates.append(
            {
                "name": group["name"],
                "indexes": indexes,
                "files": files_payload if include_files else [],
                "conflicts": conflicts,
                "count": len(files),
            }
        )

    return candidates


def _sanitize_loop_times(raw_value: Any) -> int:
    try:
        parsed = int(str(raw_value).strip())
        return parsed if parsed >= 1 else 1
    except Exception:
        return 1


def _parse_loop_indexes(raw_indexes: Any) -> set[str]:
    parts = [chunk.strip() for chunk in re.split(r"[\s,;]+", str(raw_indexes or "")) if chunk.strip()]
    return set(parts)


def expand_selected_paths_from_candidates(
    entries: list[dict[str, Any]],
    naming_pattern: str,
    selected_candidates: list[dict[str, Any]],
) -> list[str]:
    all_candidates = build_candidates(entries, naming_pattern=naming_pattern, include_files=True)
    by_name = {str(candidate.get("name", "")).lower(): candidate for candidate in all_candidates}

    output_paths: list[str] = []

    for spec in selected_candidates:
        candidate_name = str(spec.get("name", "")).strip()
        if not candidate_name:
            continue

        candidate = by_name.get(candidate_name.lower())
        if not candidate:
            continue

        files = candidate.get("files", []) if isinstance(candidate.get("files"), list) else []
        conflicts = candidate.get("conflicts", []) if isinstance(candidate.get("conflicts"), list) else []
        conflict_by_index = {str(item.get("index", "")): item for item in conflicts}

        emitted: set[str] = set()
        buckets: dict[str, list[str]] = {}
        parsed_index_by_path: dict[str, str] = {}

        for file_item in files:
            rel_path = str(file_item.get("path", "")).strip()
            if not rel_path:
                continue

            parsed_index = str(file_item.get("parsedIndex", "")).strip()
            bucket_key = parsed_index if parsed_index else f"__single__{rel_path}"
            parsed_index_by_path[rel_path] = parsed_index
            buckets.setdefault(bucket_key, []).append(rel_path)

        base_candidate_paths: list[str] = []
        conflict_resolutions = spec.get("conflictResolutions", {})
        if not isinstance(conflict_resolutions, dict):
            conflict_resolutions = {}

        for bucket_key in buckets.keys():
            bucket_paths = buckets.get(bucket_key, [])
            conflict = conflict_by_index.get(bucket_key)

            if conflict:
                requested_order = conflict_resolutions.get(bucket_key, [])
                if not isinstance(requested_order, list):
                    requested_order = []

                resolved_order = [str(path) for path in requested_order if str(path) in bucket_paths]
                for rel_path in resolved_order:
                    if rel_path not in emitted:
                        base_candidate_paths.append(rel_path)
                        emitted.add(rel_path)

                for rel_path in bucket_paths:
                    if rel_path not in emitted:
                        base_candidate_paths.append(rel_path)
                        emitted.add(rel_path)
            else:
                for rel_path in bucket_paths:
                    if rel_path not in emitted:
                        base_candidate_paths.append(rel_path)
                        emitted.add(rel_path)

        part_multiplier: dict[str, int] = {}
        raw_part_loops = spec.get("partLoops", [])
        if isinstance(raw_part_loops, list):
            for row in raw_part_loops:
                if not isinstance(row, dict):
                    continue
                indexes = _parse_loop_indexes(row.get("indexes", ""))
                if not indexes:
                    continue
                times = _sanitize_loop_times(row.get("times", 1))
                for idx in indexes:
                    part_multiplier[idx] = times

        expanded_by_parts: list[str] = []
        for rel_path in base_candidate_paths:
            idx = parsed_index_by_path.get(rel_path, "")
            multiplier = part_multiplier.get(idx, 1)
            for _ in range(multiplier):
                expanded_by_parts.append(rel_path)

        entirety_times = _sanitize_loop_times(spec.get("entiretyTimes", 1))
        for _ in range(entirety_times):
            output_paths.extend(expanded_by_parts)

    return output_paths


def _safe_output_name(raw_name: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._-")
    if not candidate:
        candidate = f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if not candidate.lower().endswith(".mp4"):
        candidate = f"{candidate}.mp4"
    return candidate


def _safe_move_to_trash(working_dir: Path, source_paths: list[Path]) -> int:
    trash_root = working_dir / ".trash" / "media-merger"
    trash_root.mkdir(parents=True, exist_ok=True)

    moved = 0
    for src in source_paths:
        if not src.exists() or not src.is_file():
            continue

        base_name = src.name
        target = trash_root / base_name
        suffix = 1
        while target.exists():
            target = trash_root / f"{src.stem}_{suffix}{src.suffix}"
            suffix += 1

        src.rename(target)
        moved += 1

    return moved


def _stage_media_for_ffmpeg(temp_root: Path, media_files: list[Path], overlay_file: Path | None) -> tuple[list[Path], Path | None]:
    staged_inputs: list[Path] = []
    for idx, src in enumerate(media_files):
        dst = temp_root / f"i{idx:04d}{src.suffix.lower()}"
        shutil.copy2(src, dst)
        staged_inputs.append(dst)

    staged_overlay: Path | None = None
    if overlay_file is not None:
        staged_overlay = temp_root / f"overlay{overlay_file.suffix.lower()}"
        shutil.copy2(overlay_file, staged_overlay)

    return staged_inputs, staged_overlay


def _build_ffmpeg_filter(
    durations: list[float],
    has_native_audio: list[bool],
    transition_type: str,
    fade_cross_time: float,
    overlay_input_idx: int | None,
    overlay_volume: float,
    end_fadeout_time: float,
    end_last_image_time: float,
) -> tuple[str, str, str, float]:
    lines: list[str] = []

    for idx, duration in enumerate(durations):
        lines.append(
            f"[{idx}:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,format=yuv420p,setsar=1,trim=duration={duration:.3f},setpts=PTS-STARTPTS[v{idx}]"
        )
        if has_native_audio[idx]:
            lines.append(
                f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,aresample=48000,atrim=duration={duration:.3f},asetpts=N/SR/TB[a{idx}]"
            )
        else:
            lines.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.3f}[a{idx}]")

    total_duration = sum(durations)
    video_out = ""
    audio_out = ""

    if len(durations) == 1:
        video_out = "v0"
        audio_out = "a0"
    elif transition_type == "fade":
        current_video = "v0"
        current_audio = "a0"
        current_len = durations[0]

        for idx in range(1, len(durations)):
            safe_cross = min(
                max(0.05, fade_cross_time),
                max(0.05, durations[idx - 1] - 0.05),
                max(0.05, durations[idx] - 0.05),
            )
            offset = max(0.0, current_len - safe_cross)
            next_video = f"vx{idx}"
            next_audio = f"ax{idx}"

            lines.append(
                f"[{current_video}][v{idx}]xfade=transition=fade:duration={safe_cross:.3f}:offset={offset:.3f}[{next_video}]"
            )
            lines.append(
                f"[{current_audio}][a{idx}]acrossfade=d={safe_cross:.3f}:c1=tri:c2=tri[{next_audio}]"
            )

            current_video = next_video
            current_audio = next_audio
            current_len = current_len + durations[idx] - safe_cross

        video_out = current_video
        audio_out = current_audio
        total_duration = current_len
    else:
        concat_inputs = "".join(f"[v{idx}][a{idx}]" for idx in range(len(durations)))
        lines.append(f"{concat_inputs}concat=n={len(durations)}:v=1:a=1[vcat][acat]")
        video_out = "vcat"
        audio_out = "acat"

    if overlay_input_idx is not None:
        lines.append(
            f"[{overlay_input_idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,aresample=48000,volume={overlay_volume:.3f},atrim=duration={total_duration:.3f},asetpts=N/SR/TB[bgm]"
        )
        lines.append(f"[{audio_out}][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        audio_out = "aout"

    if end_last_image_time > 0:
        lines.append(f"[{video_out}]tpad=stop_mode=clone:stop_duration={end_last_image_time:.3f}[vend_hold]")
        video_out = "vend_hold"
        total_duration += end_last_image_time

    safe_fadeout = min(max(0.0, end_fadeout_time), max(0.0, total_duration))
    if safe_fadeout > 0:
        fade_start = max(0.0, total_duration - safe_fadeout)
        lines.append(f"[{video_out}]fade=t=out:st={fade_start:.3f}:d={safe_fadeout:.3f}[vend_fade]")
        lines.append(f"[{audio_out}]afade=t=out:st={fade_start:.3f}:d={safe_fadeout:.3f}[aend_fade]")
        video_out = "vend_fade"
        audio_out = "aend_fade"

    return ";".join(lines), video_out, audio_out, total_duration


def build_merged_video(
    working_dir: Path,
    merger_dir: Path,
    selected_paths: list[str],
    transition_type: str,
    diapo_delay: float,
    fade_cross_time: float,
    overlay_sound_path: str,
    overlay_volume: float,
    end_fadeout_time: float,
    end_last_image_time: float,
    output_name: str,
    trash_after_build: bool,
) -> dict[str, Any]:
    ffmpeg_bin, ffprobe_bin = _find_ffmpeg()
    if not ffmpeg_bin or not ffprobe_bin:
        return {
            "success": False,
            "error": "ffmpeg/ffprobe is required for media merge build but was not found in PATH",
        }

    if not selected_paths:
        return {
            "success": False,
            "error": "No selected media files to merge",
        }

    media_files: list[Path] = []
    media_types: list[str] = []
    for rel in selected_paths:
        resolved = (working_dir / rel).resolve()
        try:
            resolved.relative_to(working_dir.resolve())
        except Exception:
            return {
                "success": False,
                "error": f"Invalid selected path: {rel}",
            }

        if not resolved.exists() or not resolved.is_file():
            return {
                "success": False,
                "error": f"Selected file not found: {rel}",
            }

        ext = resolved.suffix.lower()
        media_type = _infer_media_type(ext)
        if media_type not in {"image", "video"}:
            return {
                "success": False,
                "error": f"Unsupported media type for merge timeline: {resolved.name}",
            }

        media_files.append(resolved)
        media_types.append(media_type)

    overlay_file: Path | None = None
    if overlay_sound_path:
        overlay_file = Path(overlay_sound_path).resolve()
        if not overlay_file.exists() or not overlay_file.is_file():
            return {
                "success": False,
                "error": f"Overlay sound file not found: {overlay_sound_path}",
            }
        if overlay_file.suffix.lower() not in MERGE_AUDIO_EXTS:
            return {
                "success": False,
                "error": "Overlay file must be a supported audio type",
            }

    merger_dir.mkdir(parents=True, exist_ok=True)
    output_file = merger_dir / _safe_output_name(output_name)

    durations: list[float] = []
    has_native_audio: list[bool] = []
    for media_path, media_type in zip(media_files, media_types):
        if media_type == "image":
            durations.append(max(0.2, diapo_delay))
            has_native_audio.append(False)
            continue

        duration = _ffprobe_duration_seconds(media_path)
        if duration <= 0:
            duration = max(0.2, diapo_delay)
        durations.append(duration)
        has_native_audio.append(True)

    try:
        with TemporaryDirectory(prefix="media_merge_") as tmp:
            temp_root = Path(tmp)
            staged_media_files, staged_overlay_file = _stage_media_for_ffmpeg(temp_root, media_files, overlay_file)

            cmd: list[str] = [ffmpeg_bin, "-y"]
            for media_path, media_type, duration in zip(staged_media_files, media_types, durations):
                if media_type == "image":
                    cmd.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", str(media_path)])
                else:
                    cmd.extend(["-i", str(media_path)])

            overlay_input_idx: int | None = None
            if staged_overlay_file:
                overlay_input_idx = len(staged_media_files)
                cmd.extend(["-stream_loop", "-1", "-i", str(staged_overlay_file)])

            transition = "fade" if transition_type == "fade" else "diapo"
            filter_complex, video_label, audio_label, total_duration = _build_ffmpeg_filter(
                durations=durations,
                has_native_audio=has_native_audio,
                transition_type=transition,
                fade_cross_time=max(0.05, fade_cross_time),
                overlay_input_idx=overlay_input_idx,
                overlay_volume=max(0.0, min(1.0, overlay_volume)),
                end_fadeout_time=max(0.0, end_fadeout_time),
                end_last_image_time=max(0.0, end_last_image_time),
            )

            filter_script = temp_root / "filter_complex.txt"
            filter_script.write_text(filter_complex, encoding="utf-8")

            cmd.extend(
                [
                    "-filter_complex_script",
                    str(filter_script),
                    "-map",
                    f"[{video_label}]",
                    "-map",
                    f"[{audio_label}]",
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
                    "-t",
                    f"{total_duration:.3f}",
                    str(output_file),
                ]
            )

            run = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if run.returncode != 0:
                error_text = (run.stderr or run.stdout or "ffmpeg failed").strip()
                return {
                    "success": False,
                    "error": f"Merge failed: {error_text[-800:]}",
                }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Merge failed: {exc}",
        }

    trashed_count = 0
    if trash_after_build:
        trashed_count = _safe_move_to_trash(working_dir, media_files)

    return {
        "success": True,
        "outputPath": str(output_file),
        "outputName": output_file.name,
        "mergedCount": len(media_files),
        "totalDuration": round(total_duration, 3),
        "trashedCount": trashed_count,
    }
