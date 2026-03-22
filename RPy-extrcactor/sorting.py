"""Sort state management and asset keep/delete operations."""
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable
from models import TRASH_DIR_NAME


def tlog(message: str) -> None:
    """Log with timestamp."""
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def log_append(logs: list[str], message: str, progress: Callable[[str], None] | None = None) -> None:
    """Add to log and call progress callback."""
    logs.append(message)
    tlog(message)
    if progress:
        progress(message)


def _find_trashed_folder(assets_dir: Path, ext_folder: str) -> Path | None:
    """Find the most recently trashed folder matching ext_folder pattern.
    
    Returns the highest-numbered variant if multiple exist (for restore to get most recent).
    """
    trash_dir = assets_dir / TRASH_DIR_NAME
    if not trash_dir.exists():
        return None

    candidates = []
    for item in trash_dir.iterdir():
        if item.is_dir():
            base = item.name
            if base == ext_folder or base.startswith(f"{ext_folder}_"):
                candidates.append(item)

    if not candidates:
        return None

    # Return most recently modified (most recently trashed)
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def move_to_trash(assets_dir: Path, ext_folder: str) -> tuple[bool, str]:
    """Move asset folder to trash with increment suffix for uniqueness and logging."""
    if not assets_dir.exists():
        return False, f"Assets directory does not exist: {assets_dir}"

    src_folder = assets_dir / ext_folder
    if not src_folder.exists():
        return False, f"Folder does not exist: {src_folder}"

    trash_dir = assets_dir / TRASH_DIR_NAME
    trash_dir.mkdir(parents=True, exist_ok=True)

    # Find the target trash name (with numeric suffix if needed for uniqueness)
    trash_folder = trash_dir / ext_folder
    idx = 1
    target = trash_folder
    while target.exists():
        target = trash_dir / f"{ext_folder}_{idx}"
        idx += 1

    try:
        file_count = sum(1 for _ in src_folder.rglob("*") if _.is_file())
        shutil.move(str(src_folder), str(target))
        msg = f"Moved {ext_folder} to trash as {target.name} ({file_count} files)"
        tlog(f"[TRASH] {msg}")
        return True, msg
    except Exception as exc:
        return False, f"Failed to move {ext_folder}: {exc}"


def restore_from_trash(assets_dir: Path, ext_folder: str) -> tuple[bool, str]:
    """Restore asset folder from trash - restores the most recently trashed version."""
    if not assets_dir.exists():
        return False, f"Assets directory does not exist: {assets_dir}"

    trash_dir = assets_dir / TRASH_DIR_NAME
    if not trash_dir.exists():
        return False, f"Trash directory does not exist: {trash_dir}"

    trashed = _find_trashed_folder(assets_dir, ext_folder)
    if not trashed:
        return False, f"No trashed folder for {ext_folder}"

    target = assets_dir / ext_folder
    idx = 1
    while target.exists():
        target = assets_dir / f"{ext_folder}__{idx}"
        idx += 1

    try:
        shutil.move(str(trashed), str(target))
        tlog(f"[RESTORE] {trashed.name} -> {target.name}")
        return True, f"Restored {trashed.name} from trash as {target.name}"
    except Exception as exc:
        return False, f"Failed to restore {trashed.name}: {exc}"


def clear_trash(assets_dir: Path) -> tuple[int, list[str]]:
    """Clear all trash with detailed logging."""
    logs: list[str] = []
    if not assets_dir.exists():
        logs.append(f"Assets directory does not exist: {assets_dir}")
        return 0, logs

    trash_dir = assets_dir / TRASH_DIR_NAME
    if not trash_dir.exists():
        logs.append("Trash is empty (no trash directory)")
        return 0, logs

    count = 0
    items_deleted: list[str] = []
    
    for item in trash_dir.iterdir():
        try:
            item_size = sum(1 for _ in item.rglob("*") if _.is_file()) if item.is_dir() else 0
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            count += 1
            items_deleted.append(f"{item.name} ({item_size} files)" if item.is_dir() else item.name)
        except Exception as exc:
            logs.append(f"Failed to remove {item.name}: {exc}")

    if items_deleted:
        logs.append(f"[CLEAR] Deleted {count} item(s):")
        for item in items_deleted:
            logs.append(f"  - {item}")
    
    if count > 0:
        try:
            trash_dir.rmdir()
        except OSError:
            pass

    msg = f"Cleared {count} item(s) from trash"
    logs.append(msg)
    tlog(f"[CLEAR] {msg}")
    return count, logs


def remove_from_trash(assets_dir: Path, ext_folder: str) -> tuple[bool, list[str]]:
    """Permanently delete asset folder from trash."""
    logs: list[str] = []
    if not assets_dir.exists():
        logs.append(f"Assets directory does not exist: {assets_dir}")
        return False, logs

    trash_dir = assets_dir / TRASH_DIR_NAME
    if not trash_dir.exists():
        logs.append(f"Trash directory does not exist: {trash_dir}")
        return False, logs

    trashed = _find_trashed_folder(assets_dir, ext_folder)
    if not trashed:
        logs.append(f"No trashed folder for {ext_folder}")
        return False, logs

    try:
        shutil.rmtree(trashed)
        msg = f"Permanently deleted {trashed.name} ({sum(1 for _ in trashed.rglob('*') if _.is_file())} files)"
        logs.append(msg)
        tlog(f"[DELETE] {msg}")
        return True, logs
    except Exception as exc:
        logs.append(f"Failed to delete {trashed.name}: {exc}")
        return False, logs


def list_kept_files(assets_dir: Path) -> dict[str, int]:
    """Count files kept by extension."""
    kept: dict[str, int] = {}
    if not assets_dir.exists():
        return kept

    for item in assets_dir.iterdir():
        if item.is_dir() and item.name != TRASH_DIR_NAME:
            count = sum(1 for f in item.rglob("*") if f.is_file())
            if count > 0:
                kept[item.name] = count

    return dict(sorted(kept.items()))


def list_trash(assets_dir: Path) -> dict[str, int]:
    """Count files in trash by original extension."""
    trashed: dict[str, int] = {}
    if not assets_dir.exists():
        return trashed

    trash_dir = assets_dir / TRASH_DIR_NAME
    if not trash_dir.exists():
        return trashed

    for item in trash_dir.iterdir():
        if item.is_dir():
            base = item.name
            base_ext = base.rsplit("_", 1)[0] if "_" in base else base
            count = sum(1 for f in item.rglob("*") if f.is_file())
            if count > 0:
                trashed[base_ext] = trashed.get(base_ext, 0) + count

    return dict(sorted(trashed.items()))


def list_all_extensions(assets_dir: Path) -> list[str]:
    """List all extension folders (kept + trashed)."""
    exts: set[str] = set()
    if not assets_dir.exists():
        return []

    for item in assets_dir.iterdir():
        if item.is_dir() and item.name != TRASH_DIR_NAME:
            exts.add(item.name)

    trash_dir = assets_dir / TRASH_DIR_NAME
    if trash_dir.exists():
        for item in trash_dir.iterdir():
            if item.is_dir():
                base = item.name
                base_ext = base.rsplit("_", 1)[0] if "_" in base else base
                exts.add(base_ext)

    return sorted(exts)


def get_summary(assets_dir: Path) -> dict:
    """Get overall kept/trash summary."""
    kept = list_kept_files(assets_dir)
    trashed = list_trash(assets_dir)
    total_kept = sum(kept.values())
    total_trashed = sum(trashed.values())

    return {
        "kept": kept,
        "trashed": trashed,
        "totalKept": total_kept,
        "totalTrashed": total_trashed,
    }


def move_extension_to_trash(assets_dir: Path, ext_folder: str, progress: Callable[[str], None] | None = None) -> dict:
    """Move entire extension folder to trash."""
    logs: list[str] = []
    ok, msg = move_to_trash(assets_dir, ext_folder)
    log_append(logs, msg, progress)

    result = {
        "success": ok,
        "message": msg,
        "type": "move_to_trash",
        "folder": ext_folder,
        "logs": logs,
    }

    if ok:
        result["summary"] = get_summary(assets_dir)

    return result


def restore_extension_from_trash(assets_dir: Path, ext_folder: str, progress: Callable[[str], None] | None = None) -> dict:
    """Restore entire extension folder from trash."""
    logs: list[str] = []
    ok, msg = restore_from_trash(assets_dir, ext_folder)
    log_append(logs, msg, progress)

    result = {
        "success": ok,
        "message": msg,
        "type": "restore_from_trash",
        "folder": ext_folder,
        "logs": logs,
    }

    if ok:
        result["summary"] = get_summary(assets_dir)

    return result


def delete_extension_from_trash(assets_dir: Path, ext_folder: str, progress: Callable[[str], None] | None = None) -> dict:
    """Permanently delete extension folder from trash."""
    logs: list[str] = []
    ok, messages = remove_from_trash(assets_dir, ext_folder)
    for msg in messages:
        log_append(logs, msg, progress)

    result = {
        "success": ok,
        "type": "delete_from_trash",
        "folder": ext_folder,
        "logs": logs,
    }

    if ok:
        result["summary"] = get_summary(assets_dir)

    return result


def clear_all_trash(assets_dir: Path, progress: Callable[[str], None] | None = None) -> dict:
    """Clear all trash."""
    logs: list[str] = []
    count, messages = clear_trash(assets_dir)
    for msg in messages:
        log_append(logs, msg, progress)

    result = {
        "success": True,
        "type": "clear_all_trash",
        "cleared": count,
        "logs": logs,
    }

    if count >= 0:
        result["summary"] = get_summary(assets_dir)

    return result
