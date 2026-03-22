"""HTTP request handlers for all API endpoints."""
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote

from models import AppConfig, SESSIONS
from extraction import detect_extensions, detect_extensions_in_dir, extract_assets, walk_files, SKIP_DIRS, tlog, log_append
from extraction_types import run_extraction
from sorting import (
    list_kept_files, get_summary, list_all_extensions, list_trash,
    move_extension_to_trash, restore_extension_from_trash,
    delete_extension_from_trash, clear_all_trash,
)


def assets_dir(app_config: AppConfig) -> Path:
    """Resolve active assets directory path.

    Preference order:
    1) Current resumed session asset path (if set and still exists)
    2) Default extraction output path
    """
    session = SESSIONS.get_current()
    if isinstance(session, dict):
        current_asset_path = session.get("assetPath")
        if isinstance(current_asset_path, str) and current_asset_path.strip():
            path = Path(current_asset_path)
            if path.exists() and path.is_dir():
                return path

    return app_config.temp_path / app_config.output_dir_name


def _set_session_asset_path(path: Path) -> None:
    """Persist active assets path in current session."""
    session = SESSIONS.get_current() or {}
    session["assetPath"] = str(path)
    SESSIONS.set_current(session)


def _resume_assets_candidate_paths(app_config: AppConfig) -> list[Path]:
    """Return ordered candidate paths for resume.

    Step 3 resume should prefer the project-level /assets folder, then fallback
    to the configured extraction output path.
    """
    project_assets = Path(__file__).resolve().parent / "assets"
    configured_assets = app_config.temp_path / app_config.output_dir_name

    # Preserve order while dropping duplicates.
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in (project_assets, configured_assets):
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)

    return unique


def browse_folder(initial_path: str = "") -> dict:
    """Open native folder picker and return selected path."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        # Resolve initial path to nearest existing directory to avoid falling
        # back to root/home when a nested path does not exist yet.
        initial_dir = Path(initial_path).expanduser() if initial_path else Path.home()
        if not initial_dir.exists() or not initial_dir.is_dir():
            probe = initial_dir
            while True:
                parent = probe.parent
                if probe.exists() and probe.is_dir():
                    break
                if parent == probe:
                    probe = Path.home()
                    break
                probe = parent
            initial_dir = probe

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        selected = filedialog.askdirectory(
            initialdir=str(initial_dir),
            title="Select Game Folder",
            mustexist=True,
        )
        root.destroy()

        if not selected:
            return {
                "success": False,
                "cancelled": True,
                "error": "Folder selection cancelled",
            }

        return {
            "success": True,
            "path": selected,
        }
    except Exception as exc:
        return {
            "success": False,
            "cancelled": False,
            "error": f"Could not open folder dialog: {exc}",
        }


def get_initial_state(app_config: AppConfig) -> dict:
    """Get initial UI state."""
    return {
        "step1": {
            "gamePath": "",
            "status": "idle",
        },
        "step2": {
            "extensions": [],
            "status": "scan_first",
            "detectedExtensions": [],
        },
        "step3": {
            "keptByExt": {},
            "trashedByExt": {},
            "allExtensions": [],
            "status": "no_extraction",
        },
        "logs": [],
        "appConfig": {
            "host": app_config.host,
            "port": app_config.port,
            "tempPath": str(app_config.temp_path),
        },
    }


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

        # Keep active assets path in session for subsequent Step 3 operations.
        _set_session_asset_path(output_dir)

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


def scan_extensions(app_config: AppConfig, asset_path: str | None = None, progress_callback: Callable[[str], None] | None = None) -> dict:
    """Scan assets directory for detected extensions with verbose logging."""
    try:
        # Use provided path or default to configured assets directory
        if asset_path:
            out_dir = Path(asset_path)
        else:
            out_dir = assets_dir(app_config)

        # When a concrete assets path is scanned, keep it active for Step 3.
        _set_session_asset_path(out_dir)
        
        if progress_callback:
            progress_callback(f"[SCAN] Starting extension scan: {out_dir}")
        
        if not out_dir.exists():
            if progress_callback:
                progress_callback("[SCAN] Assets directory does not exist yet")
            return {
                "success": True,
                "detected": [],
            }
        
        # Use detect_extensions_in_dir to get ONLY actual extensions in assets folder (not default list)
        detected = detect_extensions_in_dir(out_dir)
        
        if progress_callback:
            progress_callback(f"[SCAN] Found {len(detected)} extension type(s)")
        
        # Get detailed file counts
        kept_files = list_kept_files(out_dir)
        if progress_callback:
            if kept_files:
                progress_callback("[SCAN] File counts by extension:")
                for ext in sorted(kept_files.keys()):
                    count = kept_files[ext]
                    progress_callback(f"  .{ext}: {count} file(s)")
            
        if progress_callback:
            progress_callback(f"[SCAN] Extension scan complete")
        
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
    """Get list of all extensions (kept + trashed) with logging."""
    try:
        out_dir = assets_dir(app_config)
        if not out_dir.exists():
            tlog("[API] Extensions list: assets directory not created yet")
            return {
                "success": True,
                "extensions": [],
            }

        exts = list_all_extensions(out_dir)
        tlog(f"[API] Extensions list: {len(exts)} extension types")
        return {
            "success": True,
            "extensions": exts,
        }
    except Exception as exc:
        tlog(f"[ERROR] Failed to get extensions list: {exc}")
        return {
            "success": False,
            "error": str(exc),
            "extensions": [],
        }


def get_sort_status(app_config: AppConfig, progress_callback: Callable[[str], None] | None = None) -> dict:
    """Get current sort status with verbose logging."""
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

        if progress_callback:
            progress_callback(f"[STATUS] Retrieving sort status from: {out_dir}")

        summary = get_summary(out_dir)
        exts = list_all_extensions(out_dir)
        
        if progress_callback:
            progress_callback(f"[STATUS] Current state:")
            progress_callback(f"  Kept extensions: {len(summary['kept'])} types, {summary['totalKept']} files")
            if summary["kept"]:
                for ext in sorted(summary["kept"].keys()):
                    count = summary["kept"][ext]
                    progress_callback(f"    .{ext}: {count} file(s)")
            
            progress_callback(f"  Trashed extensions: {len(summary['trashed'])} types, {summary['totalTrashed']} files")
            if summary["trashed"]:
                for ext in sorted(summary["trashed"].keys()):
                    count = summary["trashed"][ext]
                    progress_callback(f"    .{ext}: {count} file(s) [trashed]")

        tlog(f"[STATUS] Sort status retrieved: {len(summary['kept'])} kept, {len(summary['trashed'])} trashed")
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
        tlog(f"[ERROR] Failed to get sort status: {exc}")
        return {
            "success": False,
            "error": str(exc),
        }


def _trash_operation_endpoint(
    operation: str,
    app_config: AppConfig,
    ext_folder: str,
    operation_func: Callable,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Generic helper for trash operations (move, restore, delete) with logging."""
    if not operation or not ext_folder:
        return {
            "success": False,
            "error": f"Missing {operation} or folder parameter",
            "type": operation,
            "folder": ext_folder,
        }
    
    try:
        out_dir = assets_dir(app_config)
        tlog(f"[TRASH] {operation} operation on: {ext_folder}")
        result = operation_func(out_dir, ext_folder, progress_callback)
        return result
    except Exception as exc:
        tlog(f"[ERROR] {operation} failed for {ext_folder}: {exc}")
        return {
            "success": False,
            "error": str(exc),
            "type": operation,
            "folder": ext_folder,
        }


def keep_selected(
    app_config: AppConfig,
    selected_exts: list[str],
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Move all unselected extensions to trash with verbose logging."""
    try:
        out_dir = assets_dir(app_config)
        
        if progress_callback:
            progress_callback(f"[MANAGE] Starting extension curation - {len(selected_exts)} types selected")
        
        if not out_dir.exists():
            tlog("[MANAGE] Assets directory not created yet")
            return {
                "success": True,
                "message": "No assets to manage",
                "summary": {
                    "kept": {}, "trashed": {}, "totalKept": 0, "totalTrashed": 0
                },
            }

        # Get ONLY kept extensions (not trashed)
        kept_files = list_kept_files(out_dir)
        kept_exts_only = list(kept_files.keys())
        
        if not kept_exts_only:
            if progress_callback:
                progress_callback("[MANAGE] No kept extensions found")
            tlog("[MANAGE] No kept extensions found")
            return {
                "success": True,
                "message": "No extensions to manage",
                "summary": get_summary(out_dir),
            }
        
        if progress_callback:
            progress_callback(f"[MANAGE] Current kept extensions: {', '.join(sorted(kept_exts_only))}")
        
        # Normalize selected_exts: convert ".ext" to "ext" to match folder names
        selected_set = set()
        for ext in selected_exts:
            normalized = ext[1:] if ext.startswith(".") else ext
            selected_set.add(normalized)
        
        if progress_callback:
            progress_callback(f"[MANAGE] User selected types: {', '.join(sorted(selected_set))}")
        
        # Find extensions to trash: kept types that are NOT selected
        to_trash = [ext for ext in kept_exts_only if ext not in selected_set]
        
        if not to_trash:
            if progress_callback:
                progress_callback(f"[MANAGE] All {len(selected_set)} kept types are already selected - no changes needed")
            return {
                "success": True,
                "message": "No changes needed",
                "summary": get_summary(out_dir),
            }

        if progress_callback:
            progress_callback(f"[MANAGE] Will move to trash: {', '.join(sorted(to_trash))}")

        # Move unselected extensions to trash
        trash_count = 0
        for ext in to_trash:
            if progress_callback:
                count = kept_files.get(ext, 0)
                progress_callback(f"[MANAGE] Moving {ext} ({count} file(s)) to trash...")
            move_extension_to_trash(out_dir, ext, progress_callback)
            trash_count += 1

        summary = get_summary(out_dir)
        if progress_callback:
            progress_callback(f"[MANAGE] Complete: Kept {summary['totalKept']} files, Trashed {summary['totalTrashed']} files")

        return {
            "success": True,
            "message": f"Kept {len(selected_set)} types, moved {trash_count} types to trash",
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
    """Move extension to trash with logging."""
    return _trash_operation_endpoint(
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
    """Restore extension from trash with logging."""
    return _trash_operation_endpoint(
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
    """Permanently delete from trash with logging."""
    return _trash_operation_endpoint(
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
        result = clear_all_trash(out_dir, progress_callback)
        return result
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "type": "clear_all_trash",
        }


def get_assets_for_preview(app_config: AppConfig, ext_folder: str) -> dict:
    """Get preview data for extension folder."""
    try:
        out_dir = assets_dir(app_config)
        folder_path = out_dir / ext_folder

        if not folder_path.exists() or not folder_path.is_dir():
            return {
                "success": False,
                "error": f"Folder not found: {ext_folder}",
                "assets": [],
            }

        assets_list = []
        for file_path in walk_files(folder_path, SKIP_DIRS):
            if file_path.is_file():
                rel = file_path.relative_to(out_dir)
                encoded_path = "/".join(quote(part, safe="") for part in rel.parts)
                assets_list.append({
                    "name": file_path.name,
                    "path": encoded_path,
                    "size": file_path.stat().st_size,
                })

        return {
            "success": True,
            "assets": sorted(assets_list, key=lambda x: x["name"])[:100],
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "assets": [],
        }


def get_asset_preview_url(app_config: AppConfig, encoded_path: str) -> str:
    """Get direct URL for asset preview."""
    try:
        decoded = unquote(encoded_path)
        asset_path = assets_dir(app_config) / decoded
        
        if asset_path.exists() and asset_path.is_file():
            return f"/preview/{quote(decoded, safe='/')}"
        
        return ""
    except Exception:
        return ""


def list_assets_for_sorting_window(app_config: AppConfig, max_assets: int = 100, offset: int = 0) -> dict:
    """List assets for the sorting window.

    To keep UI latency low, this endpoint indexes at most ``max_assets`` files.
    """
    try:
        out_dir = assets_dir(app_config)
        safe_offset = max(0, int(offset))
        safe_limit = max(1, int(max_assets))
        if not out_dir.exists() or not out_dir.is_dir():
            return {
                "success": True,
                "assets": [],
                "assetPath": str(out_dir),
                "indexedCount": 0,
                "indexedLimit": safe_limit,
                "offset": safe_offset,
                "truncated": False,
            }

        assets: list[dict[str, Any]] = []
        truncated = False
        seen_count = 0
        for file_path in walk_files(out_dir, SKIP_DIRS):
            if not file_path.is_file():
                continue
            # Hide internal trash folders from the sorting window.
            if any(part.startswith(".trash") for part in file_path.parts):
                continue

            if seen_count < safe_offset:
                seen_count += 1
                continue

            if len(assets) >= safe_limit:
                truncated = True
                break

            rel = file_path.relative_to(out_dir)
            encoded_path = "/".join(quote(part, safe="") for part in rel.parts)
            ext = file_path.suffix.lower()

            asset_type = "binary"
            if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg", ".ico"}:
                asset_type = "image"
            elif ext in {".mp3", ".ogg", ".wav", ".m4a", ".aac", ".opus", ".flac"}:
                asset_type = "audio"
            elif ext in {".mp4", ".webm", ".mov", ".m4v", ".mpeg", ".mpg", ".avi", ".mkv"}:
                asset_type = "video"
            elif ext in {".txt", ".json", ".xml", ".csv", ".md", ".rpy", ".rpym", ".ini", ".log", ".py", ".js", ".css", ".html"}:
                asset_type = "text"

            assets.append(
                {
                    "name": file_path.name,
                    "path": encoded_path,
                    "ext": ext or ".noext",
                    "size": file_path.stat().st_size,
                    "type": asset_type,
                }
            )

            seen_count += 1

        return {
            "success": True,
            "assets": assets,
            "assetPath": str(out_dir),
            "indexedCount": len(assets),
            "indexedLimit": safe_limit,
            "offset": safe_offset,
            "truncated": truncated,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "assets": []}


def _get_sort_history_session() -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Get session and mutable sort history list."""
    session = SESSIONS.get_current() or {}
    history = session.get("sortingHistory")
    if not isinstance(history, list):
        history = []
    session["sortingHistory"] = history
    return session, history


def _resolve_asset_path_for_action(out_dir: Path, encoded_path: str) -> tuple[Path | None, str | None]:
    """Resolve and validate encoded asset path under active assets root."""
    if not encoded_path:
        return None, "Missing asset path"

    decoded = unquote(encoded_path)
    candidate = (out_dir / decoded).resolve()
    try:
        candidate.relative_to(out_dir.resolve())
    except Exception:
        return None, "Invalid asset path"

    if not candidate.exists() or not candidate.is_file():
        return None, f"Asset not found: {decoded}"

    return candidate, None


def sort_keep_asset(app_config: AppConfig, encoded_path: str) -> dict:
    """Mark one asset as kept and record action for undo."""
    try:
        out_dir = assets_dir(app_config)
        asset_path, err = _resolve_asset_path_for_action(out_dir, encoded_path)
        if err:
            return {"success": False, "error": err}

        assert asset_path is not None
        session, history = _get_sort_history_session()
        history.append(
            {
                "action": "keep",
                "path": str(asset_path),
            }
        )
        SESSIONS.set_current(session)

        return {
            "success": True,
            "action": "keep",
            "path": encoded_path,
            "name": asset_path.name,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def sort_trash_asset(app_config: AppConfig, encoded_path: str) -> dict:
    """Move one asset into hidden sorting trash and record action for undo."""
    try:
        out_dir = assets_dir(app_config)
        asset_path, err = _resolve_asset_path_for_action(out_dir, encoded_path)
        if err:
            return {"success": False, "error": err}

        assert asset_path is not None
        rel = asset_path.relative_to(out_dir)
        trash_root = out_dir / ".trash"
        target = trash_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)

        # Keep unique name when same file has been trashed multiple times.
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            idx = 1
            while True:
                candidate = target.with_name(f"{stem}__{idx}{suffix}")
                if not candidate.exists():
                    target = candidate
                    break
                idx += 1

        shutil.move(str(asset_path), str(target))

        session, history = _get_sort_history_session()
        history.append(
            {
                "action": "trash",
                "source": str(asset_path),
                "target": str(target),
            }
        )
        SESSIONS.set_current(session)

        return {
            "success": True,
            "action": "trash",
            "path": encoded_path,
            "name": rel.name,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def sort_undo_last_action(app_config: AppConfig) -> dict:
    """Undo the most recent keep/trash sorting action."""
    try:
        out_dir = assets_dir(app_config)
        session, history = _get_sort_history_session()
        if not history:
            return {"success": False, "error": "No actions to undo"}

        last = history.pop()
        action = str(last.get("action", ""))

        if action == "keep":
            SESSIONS.set_current(session)
            return {"success": True, "undone": "keep"}

        if action == "trash":
            source_raw = str(last.get("source", ""))
            target_raw = str(last.get("target", ""))
            source = Path(source_raw)
            target = Path(target_raw)

            if not target.exists():
                SESSIONS.set_current(session)
                return {"success": False, "error": "Cannot undo trash: file no longer in sorting trash"}

            source.parent.mkdir(parents=True, exist_ok=True)
            restore_target = source
            if restore_target.exists():
                stem = restore_target.stem
                suffix = restore_target.suffix
                idx = 1
                while True:
                    candidate = restore_target.with_name(f"{stem}__undo{idx}{suffix}")
                    if not candidate.exists():
                        restore_target = candidate
                        break
                    idx += 1

            shutil.move(str(target), str(restore_target))
            SESSIONS.set_current(session)

            rel = restore_target.relative_to(out_dir)
            encoded = "/".join(quote(part, safe="") for part in rel.parts)
            return {
                "success": True,
                "undone": "trash",
                "path": encoded,
            }

        # Unknown action type.
        SESSIONS.set_current(session)
        return {"success": False, "error": f"Unsupported undo action: {action}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def sort_rename_asset(app_config: AppConfig, encoded_path: str, new_name: str) -> dict:
    """Rename an asset file in the sorting window."""
    try:
        out_dir = assets_dir(app_config)
        asset_path, err = _resolve_asset_path_for_action(out_dir, encoded_path)
        if err:
            return {"success": False, "error": err}

        assert asset_path is not None
        
        # Validate new name
        new_name = new_name.strip()
        if not new_name:
            return {"success": False, "error": "New name cannot be empty"}
        
        # Prevent path traversal and invalid characters
        if "/" in new_name or "\\" in new_name or ":" in new_name or new_name == ".":
            return {"success": False, "error": "Invalid filename"}
        
        # Get parent directory and create new path
        parent = asset_path.parent
        new_path = parent / new_name
        
        # Check if target already exists
        if new_path.exists() and new_path != asset_path:
            return {"success": False, "error": f"File already exists: {new_name}"}
        
        # Rename the file
        asset_path.rename(new_path)
        
        # Record in history for potential undo
        session, history = _get_sort_history_session()
        history.append(
            {
                "action": "rename",
                "old_path": str(asset_path),
                "new_path": str(new_path),
            }
        )
        SESSIONS.set_current(session)
        
        # Return encoded path for the new file
        rel = new_path.relative_to(out_dir)
        new_encoded = "/".join(quote(part, safe="") for part in rel.parts)
        
        return {
            "success": True,
            "action": "rename",
            "oldPath": encoded_path,
            "newPath": new_encoded,
            "name": new_path.name,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def save_remaining_assets(app_config: AppConfig, encoded_paths: list[str], destination_path: str) -> dict:
    """Move remaining sorting assets to a user-selected destination folder."""
    try:
        out_dir = assets_dir(app_config).resolve()
        destination = Path(destination_path).expanduser().resolve()

        if not destination_path.strip():
            return {"success": False, "error": "Destination path is required"}
        if not destination.exists() or not destination.is_dir():
            return {"success": False, "error": f"Destination folder does not exist: {destination}"}

        moved = 0
        skipped = 0
        failures: list[str] = []

        for encoded in encoded_paths:
            decoded = unquote(encoded)
            src = (out_dir / decoded).resolve()

            try:
                src.relative_to(out_dir)
            except Exception:
                skipped += 1
                failures.append(f"Invalid path: {decoded}")
                continue

            if not src.exists() or not src.is_file():
                skipped += 1
                continue

            rel = src.relative_to(out_dir)
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)

            if target.exists():
                stem = target.stem
                suffix = target.suffix
                idx = 1
                while True:
                    candidate = target.with_name(f"{stem}__{idx}{suffix}")
                    if not candidate.exists():
                        target = candidate
                        break
                    idx += 1

            try:
                shutil.move(str(src), str(target))
                moved += 1
            except Exception as exc:
                failures.append(f"{decoded}: {exc}")

        return {
            "success": True,
            "moved": moved,
            "skipped": skipped,
            "failures": failures,
            "destinationPath": str(destination),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_asset_preview_content(app_config: AppConfig, encoded_path: str, max_lines: int = 50) -> dict:
    """Get preview payload for one asset.

    Media files are served by URL. Text-like files return first max_lines lines.
    """
    try:
        out_dir = assets_dir(app_config)
        decoded = unquote(encoded_path)
        asset_path = out_dir / decoded

        if not asset_path.exists() or not asset_path.is_file():
            return {"success": False, "error": f"Asset not found: {decoded}"}

        rel = asset_path.relative_to(out_dir)
        safe_rel = "/".join(quote(part, safe="") for part in rel.parts)
        ext = asset_path.suffix.lower()

        image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg", ".ico"}
        audio_exts = {".mp3", ".ogg", ".wav", ".m4a", ".aac", ".opus", ".flac"}
        video_exts = {".mp4", ".webm", ".mov", ".m4v", ".mpeg", ".mpg", ".avi", ".mkv"}

        if ext in image_exts:
            return {"success": True, "type": "image", "url": f"/preview/{safe_rel}", "name": asset_path.name}
        if ext in audio_exts:
            return {"success": True, "type": "audio", "url": f"/preview/{safe_rel}", "name": asset_path.name}
        if ext in video_exts:
            return {"success": True, "type": "video", "url": f"/preview/{safe_rel}", "name": asset_path.name}

        # For non-media types, try UTF-8 text preview with first N lines.
        try:
            lines: list[str] = []
            with asset_path.open("r", encoding="utf-8", errors="replace") as fh:
                for idx, line in enumerate(fh):
                    if idx >= max_lines:
                        break
                    lines.append(line.rstrip("\n"))

            return {
                "success": True,
                "type": "text",
                "name": asset_path.name,
                "lineCount": len(lines),
                "content": "\n".join(lines),
                "truncated": asset_path.stat().st_size > len("\n".join(lines).encode("utf-8")),
            }
        except Exception:
            return {
                "success": True,
                "type": "binary",
                "name": asset_path.name,
                "message": "Binary file preview is not supported for this extension.",
            }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def list_all_logs(app_config: AppConfig) -> dict:
    """Get all logs from current session."""
    session = SESSIONS.get_current()
    if not session:
        return {"logs": []}
    
    return {"logs": session.get("logs", [])}


def clear_all_logs(app_config: AppConfig) -> dict:
    """Clear in-memory session logs used by Activity Log polling."""
    try:
        session = SESSIONS.get_current() or {}
        session["logs"] = []
        SESSIONS.set_current(session)
        return {"success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def load_log_file_entries(app_config: AppConfig, max_lines: int = 800) -> dict:
    """Load persisted log lines from the newest log file in configured logDir."""
    try:
        log_dir = app_config.log_dir.resolve()
        if not log_dir.exists() or not log_dir.is_dir():
            return {"success": False, "error": f"Log directory not found: {log_dir}"}

        candidates = sorted(
            (path for path in log_dir.glob("*.log") if path.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return {"success": True, "logs": [], "source": ""}

        source = candidates[0]
        with source.open("r", encoding="utf-8", errors="replace") as fh:
            lines = [line.rstrip("\n") for line in fh]

        if max_lines > 0:
            lines = lines[-max_lines:]

        return {
            "success": True,
            "logs": lines,
            "source": str(source),
            "count": len(lines),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _open_folder_in_explorer(path: Path) -> tuple[bool, str]:
    """Open folder in the system file explorer."""
    if not path.exists() or not path.is_dir():
        return False, f"Folder not found: {path}"

    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True, ""

        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return True, ""

        subprocess.Popen(["xdg-open", str(path)])
        return True, ""
    except Exception as exc:
        return False, str(exc)


def open_log_dir(app_config: AppConfig) -> dict:
    """Open configured logDir in file explorer."""
    try:
        log_dir = app_config.log_dir.resolve()
        ok, err = _open_folder_in_explorer(log_dir)
        if not ok:
            return {"success": False, "error": err}
        return {"success": True, "path": str(log_dir)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def open_folder_path(path_str: str) -> dict:
    """Open arbitrary folder path in file explorer."""
    try:
        if not path_str.strip():
            return {"success": False, "error": "Folder path is required"}
        path = Path(path_str).expanduser().resolve()
        ok, err = _open_folder_in_explorer(path)
        if not ok:
            return {"success": False, "error": err}
        return {"success": True, "path": str(path)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_session_state(app_config: AppConfig) -> dict:
    """Get current session state."""
    session = SESSIONS.get_current()
    if not session:
        return {
            "hasSession": False,
            "step1": {"gamePath": "", "status": "idle"},
            "step2": {"extensions": [], "status": "scan_first", "detectedExtensions": []},
            "step3": {"status": "no_extraction"},
        }

    return {
        "hasSession": True,
        "step1": session.get("step1", {}),
        "step2": session.get("step2", {}),
        "step3": session.get("step3", {}),
    }


def resume_session(app_config: AppConfig, game_path: str) -> dict:
    """Resume extraction with new or existing path."""
    try:
        # Prefer project /assets for resume, then fallback to configured output.
        for candidate in _resume_assets_candidate_paths(app_config):
            if candidate.exists() and candidate.is_dir():
                _set_session_asset_path(candidate)
                summary = get_summary(candidate)
                all_exts = list_all_extensions(candidate)
                return {
                    "success": True,
                    "assets_exist": True,
                    "gamePath": game_path,
                    "assetPath": str(candidate),
                    "summary": summary,
                    "allExtensions": all_exts,
                }

        # If no assets were found, only validate game_path when provided.
        if game_path:
            game_root = Path(game_path)
            if not game_root.exists():
                return {
                    "success": False,
                    "error": f"Path does not exist: {game_path}",
                }

        fallback_path = app_config.temp_path / app_config.output_dir_name
        return {
            "success": True,
            "assets_exist": False,
            "gamePath": game_path,
            "assetPath": str(fallback_path),
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }
