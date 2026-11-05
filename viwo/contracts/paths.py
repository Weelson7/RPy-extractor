"""Walking a folder without following links (doc 4.3, 7.1): link-like folders are never entered,
and a target is inside a root only when no link lies between them. Re-exported by
contracts.workspace, where callers use them (`ws.walk`, `ws.inside`)."""

import fnmatch
import os
from pathlib import Path


def link_like(path) -> bool:
    """A symbolic link, a directory junction or another reparse point: never walked into (a
    junction in a game folder may point anywhere, or back at an ancestor)."""
    if os.path.islink(path):
        return True
    junction = getattr(os.path, "isjunction", None)  # Python 3.12+
    if junction is not None:
        return junction(path)
    try:
        return bool(getattr(os.lstat(path), "st_file_attributes", 0) & 0x400)  # REPARSE_POINT
    except OSError:
        return False


def walk(root: Path):
    """os.walk that never enters a link-like folder (see link_like)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not link_like(os.path.join(dirpath, d))]
        yield dirpath, dirnames, filenames


def files(root: Path, pattern: str = "*") -> list[Path]:
    """Every file under root whose name matches pattern (case-insensitive), sorted; link-like
    folders are never entered (see walk). The rglob of a game folder, without its junctions."""
    pattern = pattern.lower()
    return sorted(
        Path(dirpath) / name
        for dirpath, _, names in walk(root)
        for name in names
        if fnmatch.fnmatchcase(name.lower(), pattern)
    )


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
