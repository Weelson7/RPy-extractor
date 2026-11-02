"""Workspace layout contract (doc 4.3)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

MARKER = ".viwo-workspace"
LEGACY_MARKERS = (".rpyx-workspace",)  # written by the v1 hotfix
METADATA_DIR = ".extraction_metadata"
RUNS_DIR = f"{METADATA_DIR}/runs"
PROVENANCE_FILE = f"{METADATA_DIR}/provenance.jsonl"
TRASH_DIR = ".trash"
NOEXT = ".noext"
COLLISION = "{stem}__{index}{suffix}"


def is_reserved(name: str) -> bool:
    """Top-level names starting with "." are never asset groups."""
    return name.startswith(".")


def ext_of(path: Path) -> str:
    return path.suffix.lower().strip() or NOEXT


def ext_folder(ext: str) -> str:
    return ext[1:] if ext.startswith(".") else ext


def has_marker(folder: Path) -> bool:
    return any((folder / name).exists() for name in (MARKER, *LEGACY_MARKERS))


def next_free(path: Path) -> Path:
    if not path.exists():
        return path
    index = 1
    while True:
        candidate = path.with_name(
            COLLISION.format(stem=path.stem, index=index, suffix=path.suffix)
        )
        if not candidate.exists():
            return candidate
        index += 1


def safe_member(name: str) -> PurePosixPath | None:
    """An archive member name as a relative path, or None when it would leave the target
    (absolute, drive letter, "..")."""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts or ":" in parts[0] or name.startswith(("/", "\\")):
        return None
    return PurePosixPath(*parts)
