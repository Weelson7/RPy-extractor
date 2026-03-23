"""API handlers for media merger workspace panel."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from models import AppConfig
from startup import tlog
from .common import assets_dir
from media_merger.service import (
    MERGE_AUDIO_EXTS,
    MERGE_MEDIA_EXTS,
    build_candidates,
    build_merged_video,
    expand_selected_paths_from_candidates,
    list_media_entries,
    summarize_extensions,
)


def _resolve_working_dir(app_config: AppConfig, incoming: str) -> Path:
    if incoming:
        path = Path(incoming).expanduser()
        if path.exists() and path.is_dir():
            return path.resolve()
    return assets_dir(app_config).resolve()


def get_media_merger_state(app_config: AppConfig) -> dict[str, Any]:
    working_dir = assets_dir(app_config)
    if not working_dir.exists():
        working_dir.mkdir(parents=True, exist_ok=True)

    app_config.merger_dir.mkdir(parents=True, exist_ok=True)

    return {
        "success": True,
        "workingDir": str(working_dir.resolve()),
        "mergerDir": str(app_config.merger_dir.resolve()),
        "defaultPattern": "number-to-name",
        "defaultTransition": "diapo",
        "defaultDiapoDelay": 3.0,
        "defaultFadeCrossTime": 0.7,
        "defaultEndFadeoutTime": 0.0,
        "defaultEndLastImageTime": 0.0,
        "supportedOverlayAudioExts": sorted(MERGE_AUDIO_EXTS),
    }


def browse_overlay_sound(initial_path: str = "") -> dict[str, Any]:
    try:
        import tkinter as tk
        from tkinter import filedialog

        initial_target = Path(initial_path).expanduser() if initial_path else Path.home()
        if initial_target.is_file():
            initial_dir = initial_target.parent
        else:
            initial_dir = initial_target if initial_target.exists() else Path.home()

        file_types = [
            (
                "Audio files",
                " ".join(f"*{ext}" for ext in sorted(MERGE_AUDIO_EXTS)),
            ),
            ("All files", "*.*"),
        ]

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        selected = filedialog.askopenfilename(
            initialdir=str(initial_dir),
            title="Select Overlay Sound",
            filetypes=file_types,
        )
        root.destroy()

        if not selected:
            return {
                "success": False,
                "cancelled": True,
                "error": "Audio file selection cancelled",
            }

        selected_path = Path(selected)
        if selected_path.suffix.lower() not in MERGE_AUDIO_EXTS:
            return {
                "success": False,
                "cancelled": False,
                "error": "Selected file type is not a supported audio format",
            }

        return {
            "success": True,
            "path": str(selected_path.resolve()),
        }
    except Exception as exc:
        return {
            "success": False,
            "cancelled": False,
            "error": f"Could not open audio file dialog: {exc}",
        }


def list_media_merger_candidates(
    app_config: AppConfig,
    working_dir_raw: str,
    naming_pattern: str,
    allowed_exts_raw: list[Any] | None,
    offset: int = 0,
    limit: int = 120,
) -> dict[str, Any]:
    working_dir = _resolve_working_dir(app_config, working_dir_raw)
    if not working_dir.exists() or not working_dir.is_dir():
        return {
            "success": False,
            "error": f"Working directory not found: {working_dir}",
        }

    allowed_exts = None
    if isinstance(allowed_exts_raw, list):
        allowed_exts = {
            str(ext).strip().lower() if str(ext).strip().startswith(".") else f".{str(ext).strip().lower()}"
            for ext in allowed_exts_raw
            if str(ext).strip()
        }

    all_entries = list_media_entries(working_dir, allowed_exts=MERGE_MEDIA_EXTS)
    extension_summary = summarize_extensions(all_entries)
    entries = list_media_entries(working_dir, allowed_exts=allowed_exts if allowed_exts is not None else MERGE_MEDIA_EXTS)
    candidates = build_candidates(entries, naming_pattern=naming_pattern, include_files=False)
    total_count = len(candidates)
    safe_offset = max(0, int(offset))
    safe_limit = max(1, min(300, int(limit)))
    window = candidates[safe_offset : safe_offset + safe_limit]
    truncated = safe_offset + len(window) < total_count

    tlog(
        "[MERGER] Listed candidates: "
        f"{len(window)} of {total_count} groups in {working_dir} "
        f"(offset={safe_offset}, limit={safe_limit})"
    )

    return {
        "success": True,
        "workingDir": str(working_dir),
        "namingPattern": naming_pattern,
        "extensions": extension_summary,
        "candidates": window,
        "fileCount": len(entries),
        "offset": safe_offset,
        "limit": safe_limit,
        "totalCount": total_count,
        "truncated": truncated,
        "supportedMediaExts": sorted(MERGE_MEDIA_EXTS),
    }


def build_media_merger_output(app_config: AppConfig, payload: dict[str, Any]) -> dict[str, Any]:
    working_dir = _resolve_working_dir(app_config, str(payload.get("workingDir", "")))
    selected_paths = payload.get("selectedPaths", [])
    selected_candidates = payload.get("selectedCandidates", [])

    naming_pattern = str(payload.get("namingPattern", "number-to-name")).strip().lower()
    if naming_pattern not in {"number-to-name", "name-to-number"}:
        naming_pattern = "number-to-name"

    if selected_candidates and not isinstance(selected_candidates, list):
        return {
            "success": False,
            "error": "selectedCandidates must be an array",
        }

    if not selected_candidates and not isinstance(selected_paths, list):
        return {
            "success": False,
            "error": "selectedPaths must be an array",
        }

    if isinstance(selected_candidates, list) and selected_candidates:
        entries = list_media_entries(working_dir, allowed_exts=MERGE_MEDIA_EXTS)
        selected_paths = expand_selected_paths_from_candidates(
            entries=entries,
            naming_pattern=naming_pattern,
            selected_candidates=selected_candidates,
        )

    transition_type = str(payload.get("transitionType", "diapo")).strip().lower()
    if transition_type not in {"diapo", "fade"}:
        transition_type = "diapo"

    try:
        diapo_delay = float(payload.get("diapoDelay", 3.0))
    except Exception:
        diapo_delay = 3.0

    try:
        fade_cross_time = float(payload.get("fadeCrossTime", 0.7))
    except Exception:
        fade_cross_time = 0.7

    try:
        overlay_volume = float(payload.get("overlayVolume", 0.35))
    except Exception:
        overlay_volume = 0.35

    try:
        end_fadeout_time = float(payload.get("endFadeoutTime", 0.0))
    except Exception:
        end_fadeout_time = 0.0

    try:
        end_last_image_time = float(payload.get("endLastImageTime", 0.0))
    except Exception:
        end_last_image_time = 0.0

    result = build_merged_video(
        working_dir=working_dir,
        merger_dir=app_config.merger_dir,
        selected_paths=[str(item) for item in selected_paths if str(item).strip()],
        transition_type=transition_type,
        diapo_delay=max(0.2, diapo_delay),
        fade_cross_time=max(0.05, fade_cross_time),
        overlay_sound_path=str(payload.get("overlaySound", "")).strip(),
        overlay_volume=max(0.0, min(1.0, overlay_volume)),
        end_fadeout_time=max(0.0, end_fadeout_time),
        end_last_image_time=max(0.0, end_last_image_time),
        output_name=str(payload.get("outputName", "")).strip(),
        trash_after_build=bool(payload.get("trashAfterBuild", False)),
    )

    if result.get("success"):
        tlog(
            "[MERGER] Build complete: "
            f"{result.get('outputName', 'unknown')} "
            f"({result.get('mergedCount', 0)} inputs, trashed={result.get('trashedCount', 0)})"
        )
    else:
        tlog(f"[MERGER] Build failed: {result.get('error', 'unknown error')}")

    return result
