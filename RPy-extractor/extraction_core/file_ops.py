"""File scanning and moving operations for extraction."""
import os
import shutil
from pathlib import Path

from models import DEFAULT_COMMON_EXTS, SKIP_DIRS

from .runtime import tlog


def safe_suffix(path: Path) -> str:
    """Get file extension safely."""
    ext = path.suffix.lower().strip()
    if ext:
        return ext
    return ".noext"


def ext_folder_name(ext: str) -> str:
    """Convert extension to folder name."""
    return ext[1:] if ext.startswith(".") else ext


def walk_files(root: Path, skip_dirs: set[str]) -> list[Path]:
    """Walk directory tree, skipping specified directories."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for filename in filenames:
            files.append(current / filename)
    return files


def move_one(src: Path, assets_dir: Path, moved_by_ext: dict[str, int], selected_exts: set[str] | None) -> bool:
    """Move single file to assets directory."""
    ext = safe_suffix(src)
    if selected_exts is not None and ext not in selected_exts:
        return False

    try:
        folder = ext_folder_name(ext)
        dst_dir = assets_dir / folder
        dst_dir.mkdir(parents=True, exist_ok=True)

        base = src.stem
        candidate = dst_dir / src.name
        src_stat = src.stat()
        src_size = src_stat.st_size
        src_mtime = int(src_stat.st_mtime)

        index = 1
        while candidate.exists():
            try:
                dst_stat = candidate.stat()
                if src_size == dst_stat.st_size and src_mtime == int(dst_stat.st_mtime):
                    return False
            except OSError:
                pass

            candidate = dst_dir / f"{base}__{index}{src.suffix}"
            index += 1

        shutil.move(str(src), str(candidate))
        moved_by_ext[folder] = moved_by_ext.get(folder, 0) + 1
        return True
    except Exception as exc:
        tlog(f"[WARN] Failed to move {src}: {exc}")
        return False


def remove_unselected_files(output_dir: Path, selected_exts: set[str] | None) -> dict[str, int]:
    """Remove files with unselected extensions."""
    removed_by_ext: dict[str, int] = {}
    if output_dir is None or not output_dir.exists():
        return removed_by_ext

    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        if ".trash" in path.parts:
            continue

        ext = safe_suffix(path)
        if selected_exts is not None and ext in selected_exts:
            continue

        folder = ext_folder_name(ext)
        try:
            path.unlink()
            removed_by_ext[folder] = removed_by_ext.get(folder, 0) + 1
        except OSError:
            continue

    return dict(sorted(removed_by_ext.items()))


def detect_extensions_in_dir(root: Path, max_scan: int = 200000) -> list[str]:
    """Detect all file extensions in directory."""
    seen: set[str] = set()
    if not root.exists():
        return []
    count = 0
    for file_path in walk_files(root, {".trash", "__pycache__"}):
        seen.add(safe_suffix(file_path))
        count += 1
        if count >= max_scan:
            break
    return sorted(seen)


def detect_extensions(game_root: Path, max_scan: int = 200000) -> list[str]:
    """Detect extensions in game root."""
    seen: set[str] = set(DEFAULT_COMMON_EXTS)
    count = 0
    for file_path in walk_files(game_root, SKIP_DIRS):
        seen.add(safe_suffix(file_path))
        count += 1
        if count >= max_scan:
            break
    return sorted(seen)


def collect_source_roots(game_root: Path, staging_dir: Path) -> list[Path]:
    """Collect roots to scan for files."""
    roots = [staging_dir]
    game_dir = game_root / "game"
    if game_dir.exists() and game_dir.is_dir():
        roots.append(game_dir)
    else:
        roots.append(game_root)
    return roots
