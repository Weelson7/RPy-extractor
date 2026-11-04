"""Workspace layout contract (doc 4.3)."""

from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path, PurePosixPath

MARKER = ".viwo-workspace"
METADATA_DIR = ".extraction_metadata"
RUNS_DIR = f"{METADATA_DIR}/runs"
PROVENANCE_FILE = f"{METADATA_DIR}/provenance.jsonl"
TRASH_DIR = ".trash"
NOEXT = ".noext"
COLLISION = "{stem}__{index}{suffix}"
EXPORT_MAP = ".viwo-export-map.json"  # staging: exported file -> [container, member]
NAMES_FILE = ".viwo-names.json"  # an unpack folder: altered member path -> original name


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
    return (folder / MARKER).exists()


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
INVALID = re.compile(r'[<>"|?*\x00-\x1f]')  # characters no Windows file name may hold


def safe_member(name: str) -> PurePosixPath | None:
    """An archive member name as a relative path, or None when it could leave the target on
    any OS: absolute, "..", a drive or stream (":" anywhere), Windows device names, a character
    Windows refuses (< > " | ? * or a control character), or parts ending in "." / " " (which
    Windows silently rewrites). Callers count what they skip and say it."""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or name.startswith(("/", "\\")):
        return None
    for part in parts:
        if part == ".." or ":" in part or part[-1] in ". " or RESERVED.match(part):
            return None
        if INVALID.search(part):
            return None
    return PurePosixPath(*parts)


def writable(name: str) -> PurePosixPath | None:
    """A member name as a relative path every OS can write: what Windows refuses (see
    safe_member) is altered to "_"; None only for an escape (absolute, "..", empty)."""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or name.startswith(("/", "\\")) or ".." in parts:
        return None
    return PurePosixPath(*(_writable_part(p) for p in parts))


def _writable_part(part: str) -> str:
    part = INVALID.sub("_", part).replace(":", "_")
    part = part[:-1] + "_" if part[-1] in ". " else part
    return "_" + part if RESERVED.match(part) else part


class Names:
    """Where an unpacker writes each member under dest: writable names; an altered one gets a
    free name and is recorded in NAMES_FILE (altered -> original), so COLLECT gives provenance
    the original and the round trip writes the member back under it."""

    def __init__(self, dest: Path) -> None:
        self.dest, self.altered, self.escapes = dest, {}, 0

    def target(self, name: str) -> Path | None:
        rel = writable(name)
        if rel is None:
            self.escapes += 1
            return None
        original = "/".join(p for p in name.replace("\\", "/").split("/") if p not in ("", "."))
        if not inside(self.dest, self.dest.joinpath(*rel.parts)):  # a link inside dest
            self.escapes += 1
            return None
        if rel.as_posix() == original and original not in self.altered:
            return self.dest.joinpath(*rel.parts)
        base = path = self.dest.joinpath(*rel.parts)
        index = 1
        while path.exists() or path.relative_to(self.dest).as_posix() in self.altered:
            path = base.with_name(COLLISION.format(stem=base.stem, index=index, suffix=base.suffix))
            index += 1  # "a?.png" and "a*.png" are both kept
        self.altered[path.relative_to(self.dest).as_posix()] = original
        return path

    def save(self) -> tuple[str, ...]:
        """Write the record; the notes to return (never silent)."""
        notes = []
        if self.altered:
            self.dest.mkdir(parents=True, exist_ok=True)
            record = json.dumps(self.altered, ensure_ascii=False, indent=0)
            (self.dest / NAMES_FILE).write_text(record, encoding="utf-8")
            notes.append(
                f"{len(self.altered)} member name(s) Windows cannot write altered "
                "(originals recorded for the round trip)"
            )
        if self.escapes:
            notes.append(f"{self.escapes} entr(ies) whose name leads out of the folder skipped")
        return tuple(notes)


def renamed(folder: Path) -> dict[str, str]:
    """The NAMES_FILE record of an unpack folder (altered relative path -> original name)."""
    try:
        data = json.loads((folder / NAMES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


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


def member_path(root: Path, rel: str) -> Path | None:
    """`rel` (a member name, a path read back from a record) under `root`; None when it is
    unsafe (see safe_member) or leads out of root, through a link included (see inside)."""
    member = safe_member(rel)
    path = root.joinpath(*member.parts) if member is not None else None
    return path if path is not None and inside(root, path) else None


def stage_members(members: dict[str, Path], root: Path) -> list[Path]:
    """Copy edited members to root/<member> for a packer (unsafe names are skipped); returns
    the staged files."""
    staged = []
    for member, source in members.items():
        rel = safe_member(member)
        if rel is not None:
            target = root.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            staged.append(target)
    return staged
