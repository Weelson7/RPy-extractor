"""Extraction and curation API handlers."""
from pathlib import Path
from typing import Callable

from models import AppConfig
from extraction_core import detect_extensions_in_dir
from extraction_types import run_extraction
from sorting import (
    list_kept_files,
    get_summary,
    list_all_extensions,
    move_extension_to_trash,
    restore_extension_from_trash,
    delete_extension_from_trash,
    clear_all_trash,
)
from .common import assets_dir, set_session_asset_path, trash_operation_endpoint


def extract_repo(
    game_path: str,
    app_config: AppConfig,
    selected_exts: list[str] | None,
    extraction_type: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Extract from game path."""
    try:
        game_root = Path(game_path)
        if not game_root.exists() or not game_root.is_dir():
            return {
                "success": False,
                "error": f"Path does not exist or is not a folder: {game_path}",
                "details": "",
            }

        output_dir = assets_dir(app_config)
        selected_exts_set = set(selected_exts) if selected_exts else None

        result = run_extraction(
            game_root=game_root,
            output_dir=output_dir,
            selected_exts=selected_exts_set,
            temp_root=app_config.temp_path,
            requested_type=extraction_type,
            progress=progress_callback,
        )

        set_session_asset_path(output_dir)

        return {
            "success": True,
            "result": result,
            "assetPath": str(output_dir),
            "extractorType": result.get("extractorType", "generic"),
            "detection": result.get("detection", {}),
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "details": repr(exc),
        }


def scan_extensions(
    app_config: AppConfig,
    asset_path: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Scan assets directory for detected extensions with verbose logging."""
    try:
        out_dir = Path(asset_path) if asset_path else assets_dir(app_config)
        set_session_asset_path(out_dir)

        if progress_callback:
            progress_callback(f"[SCAN] Starting extension scan: {out_dir}")

        if not out_dir.exists():
            if progress_callback:
                progress_callback("[SCAN] Assets directory does not exist yet")
            return {
                "success": True,
                "detected": [],
            }

        detected = detect_extensions_in_dir(out_dir)

        if progress_callback:
            progress_callback(f"[SCAN] Found {len(detected)} extension type(s)")

        kept_files = list_kept_files(out_dir)
        if progress_callback and kept_files:
            progress_callback("[SCAN] File counts by extension:")
            for ext in sorted(kept_files.keys()):
                progress_callback(f"  .{ext}: {kept_files[ext]} file(s)")

        if progress_callback:
            progress_callback("[SCAN] Extension scan complete")

        return {
            "success": True,
            "detected": detected,
            "fileCounts": kept_files,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def get_extensions_list(app_config: AppConfig) -> dict:
    """Get list of all extensions (kept + trashed)."""
    try:
        out_dir = assets_dir(app_config)
        if not out_dir.exists():
            return {
                "success": True,
                "extensions": [],
            }

        exts = list_all_extensions(out_dir)
        return {
            "success": True,
            "extensions": exts,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "extensions": [],
        }


def get_sort_status(app_config: AppConfig, progress_callback: Callable[[str], None] | None = None) -> dict:
    """Get current sort status."""
    try:
        out_dir = assets_dir(app_config)
        if not out_dir.exists():
            if progress_callback:
                progress_callback("[STATUS] Assets directory does not exist yet")
            return {
                "success": True,
                "kept": {},
                "trashed": {},
                "totalKept": 0,
                "totalTrashed": 0,
                "allExtensions": [],
            }

        summary = get_summary(out_dir)
        exts = list_all_extensions(out_dir)

        return {
            "success": True,
            "kept": summary["kept"],
            "trashed": summary["trashed"],
            "totalKept": summary["totalKept"],
            "totalTrashed": summary["totalTrashed"],
            "allExtensions": exts,
        }
    except Exception as exc:
        if progress_callback:
            progress_callback(f"[STATUS] Error: {str(exc)}")
        return {
            "success": False,
            "error": str(exc),
        }


def keep_selected(
    app_config: AppConfig,
    selected_exts: list[str],
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Move all unselected extensions to trash."""
    try:
        out_dir = assets_dir(app_config)

        if not out_dir.exists():
            return {
                "success": True,
                "message": "No assets to manage",
                "summary": {"kept": {}, "trashed": {}, "totalKept": 0, "totalTrashed": 0},
            }

        kept_files = list_kept_files(out_dir)
        kept_exts_only = list(kept_files.keys())

        if not kept_exts_only:
            return {
                "success": True,
                "message": "No extensions to manage",
                "summary": get_summary(out_dir),
            }

        selected_set = set(ext[1:] if ext.startswith(".") else ext for ext in selected_exts)
        to_trash = [ext for ext in kept_exts_only if ext not in selected_set]

        if not to_trash:
            return {
                "success": True,
                "message": "No changes needed",
                "summary": get_summary(out_dir),
            }

        for ext in to_trash:
            move_extension_to_trash(out_dir, ext, progress_callback)

        summary = get_summary(out_dir)
        return {
            "success": True,
            "message": f"Kept {len(selected_set)} types, moved {len(to_trash)} types to trash",
            "summary": summary,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def move_to_trash_endpoint(
    app_config: AppConfig,
    ext_folder: str,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Move extension to trash."""
    return trash_operation_endpoint(
        "move_to_trash",
        app_config,
        ext_folder,
        move_extension_to_trash,
        progress_callback,
    )


def restore_from_trash_endpoint(
    app_config: AppConfig,
    ext_folder: str,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Restore extension from trash."""
    return trash_operation_endpoint(
        "restore_from_trash",
        app_config,
        ext_folder,
        restore_extension_from_trash,
        progress_callback,
    )


def delete_from_trash_endpoint(
    app_config: AppConfig,
    ext_folder: str,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Permanently delete from trash."""
    return trash_operation_endpoint(
        "delete_from_trash",
        app_config,
        ext_folder,
        delete_extension_from_trash,
        progress_callback,
    )


def clear_trash_endpoint(
    app_config: AppConfig,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Clear all trash."""
    try:
        out_dir = assets_dir(app_config)
        return clear_all_trash(out_dir, progress_callback)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "type": "clear_all_trash",
        }
