"""Workspace layout contract (doc 4.3)."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

MARKER = ".viwo-workspace"
LEGACY_MARKERS = (".rpyx-workspace",)  # written by the v1 hotfix
METADATA_DIR = ".extraction_metadata"
RUNS_DIR = f"{METADATA_DIR}/runs"
PROVENANCE_FILE = f"{METADATA_DIR}/provenance.jsonl"
TRASH_DIR = ".trash"
NOEXT = ".noext"
COLLISION = "{stem}__{index}{suffix}"
EXPORT_MAP = ".viwo-export-map.json"  # staging: exported file -> [container, member]


def count_files(folder: Path) -> int:
    """Regular files under a folder, recursively."""
    return sum(1 for p in folder.rglob("*") if p.is_file())


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


RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.IGNORECASE)


def safe_member(name: str) -> PurePosixPath | None:
    """An archive member name as a relative path, or None when it could leave the target on
    any OS: absolute, "..", a drive or stream (":" anywhere), Windows device names, or parts
    ending in "." / " " (which Windows silently rewrites)."""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or name.startswith(("/", "\\")):
        return None
    for part in parts:
        if part == ".." or ":" in part or part[-1] in ". " or RESERVED.match(part):
            return None
    return PurePosixPath(*parts)


def inside(root: Path, target: Path) -> bool:
    """True when target (after resolving links) is root or lies under it, and no existing
    component between them is a symbolic link."""
    base, path = root.resolve(), target.resolve()
    if path != base and base not in path.parents:
        return False
    probe = target
    while probe != root and probe != probe.parent:
        if probe.is_symlink():
            return False
        probe = probe.parent
    return True
