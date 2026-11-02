"""Workspace file listing helpers for the legacy curation code."""
import os
from pathlib import Path

# Marker files written by ViWo / the v1 hotfix; never shown as assets.
MARKER_FILES = {".viwo-workspace", ".rpyx-workspace"}


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
    """Walk a workspace; reserved dot-folders (.trash, .extraction_metadata...) are skipped."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        for filename in filenames:
            if filename in MARKER_FILES:
                continue
            files.append(current / filename)
    return files


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
