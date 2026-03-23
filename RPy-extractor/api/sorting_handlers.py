"""Sorting and preview API handlers."""
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from models import AppConfig, SESSIONS
from extraction_core import walk_files, SKIP_DIRS
from .common import assets_dir, get_sort_history_session, resolve_asset_path_for_action


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
                assets_list.append({"name": file_path.name, "path": encoded_path, "size": file_path.stat().st_size})

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


def list_assets_for_sorting_window(app_config: AppConfig, max_assets: int = 100, offset: int = 0) -> dict:
    """List assets for the sorting window."""
    try:
        out_dir = assets_dir(app_config)
        safe_offset = max(0, int(offset))
        safe_limit = max(1, int(max_assets))
        if not out_dir.exists() or not out_dir.is_dir():
            return {
                "success": True,
                "assets": [],
                "assetPath": str(out_dir),
                "totalCount": 0,
                "indexedCount": 0,
                "indexedLimit": safe_limit,
                "offset": safe_offset,
                "truncated": False,
            }

        assets: list[dict[str, Any]] = []
        truncated = False
        total_count = 0
        seen_count = 0
        for file_path in walk_files(out_dir, SKIP_DIRS):
            if not file_path.is_file():
                continue
            if any(part.startswith(".trash") for part in file_path.parts):
                continue

            total_count += 1

            if seen_count < safe_offset:
                seen_count += 1
                continue

            if len(assets) >= safe_limit:
                truncated = True
                seen_count += 1
                continue

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
            "totalCount": total_count,
            "indexedCount": len(assets),
            "indexedLimit": safe_limit,
            "offset": safe_offset,
            "truncated": truncated,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "assets": []}


def sort_keep_asset(app_config: AppConfig, encoded_path: str) -> dict:
    """Mark one asset as kept and record action for undo."""
    try:
        out_dir = assets_dir(app_config)
        asset_path, err = resolve_asset_path_for_action(out_dir, encoded_path)
        if err:
            return {"success": False, "error": err}

        assert asset_path is not None
        session, history = get_sort_history_session()
        history.append({"action": "keep", "path": str(asset_path)})
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
        asset_path, err = resolve_asset_path_for_action(out_dir, encoded_path)
        if err:
            return {"success": False, "error": err}

        assert asset_path is not None
        rel = asset_path.relative_to(out_dir)
        trash_root = out_dir / ".trash"
        target = trash_root / rel
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

        shutil.move(str(asset_path), str(target))

        session, history = get_sort_history_session()
        history.append({"action": "trash", "source": str(asset_path), "target": str(target)})
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
    """Undo the most recent keep/trash/rename sorting action."""
    try:
        out_dir = assets_dir(app_config)
        session, history = get_sort_history_session()
        if not history:
            return {"success": False, "error": "No actions to undo"}

        last = history.pop()
        action = str(last.get("action", ""))

        if action == "keep":
            SESSIONS.set_current(session)
            return {"success": True, "undone": "keep"}

        if action == "trash":
            source = Path(str(last.get("source", "")))
            target = Path(str(last.get("target", "")))

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
            return {"success": True, "undone": "trash", "path": encoded}

        if action == "rename":
            old_path = Path(str(last.get("old_path", "")))
            new_path = Path(str(last.get("new_path", "")))

            if not new_path.exists():
                SESSIONS.set_current(session)
                return {"success": False, "error": "Cannot undo rename: renamed file no longer exists"}

            old_path.parent.mkdir(parents=True, exist_ok=True)
            restore_target = old_path
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

            shutil.move(str(new_path), str(restore_target))
            SESSIONS.set_current(session)

            rel = restore_target.relative_to(out_dir)
            encoded = "/".join(quote(part, safe="") for part in rel.parts)
            prev_rel = new_path.relative_to(out_dir)
            prev_encoded = "/".join(quote(part, safe="") for part in prev_rel.parts)
            return {
                "success": True,
                "undone": "rename",
                "path": encoded,
                "previousPath": prev_encoded,
            }

        SESSIONS.set_current(session)
        return {"success": False, "error": f"Unsupported undo action: {action}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def sort_rename_asset(app_config: AppConfig, encoded_path: str, new_name: str) -> dict:
    """Rename an asset file in the sorting window."""
    try:
        out_dir = assets_dir(app_config)
        asset_path, err = resolve_asset_path_for_action(out_dir, encoded_path)
        if err:
            return {"success": False, "error": err}

        assert asset_path is not None
        new_name = new_name.strip()
        if not new_name:
            return {"success": False, "error": "New name cannot be empty"}

        if "/" in new_name or "\\" in new_name or ":" in new_name or new_name == ".":
            return {"success": False, "error": "Invalid filename"}

        parent = asset_path.parent
        new_path = parent / new_name

        if new_path.exists() and new_path != asset_path:
            return {"success": False, "error": f"File already exists: {new_name}"}

        asset_path.rename(new_path)

        session, history = get_sort_history_session()
        history.append({"action": "rename", "old_path": str(asset_path), "new_path": str(new_path)})
        SESSIONS.set_current(session)

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
    """Get preview payload for one asset."""
    try:
        out_dir = assets_dir(app_config).resolve()
        decoded = unquote(encoded_path)
        asset_path = (out_dir / decoded).resolve()

        try:
            asset_path.relative_to(out_dir)
        except Exception:
            return {"success": False, "error": "Invalid asset path"}

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
