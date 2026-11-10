"""Trash with three explicit layouts (doc 4.3, fixes v1 F9/F18).

.trash/groups/<ext>[_N]/   whole extension groups ("retain groups", step 3)
.trash/items/<rel path>    single files trashed in the sorting window
.trash/merger/<file>       inputs trashed after a merger build
"""

import re
import shutil
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.workspace import count_files

from ..provenance import moved

AREAS = ("groups", "items", "merger")


def area(workspace: Path, name: str) -> Path:
    return workspace / ws.TRASH_DIR / name


def _base(name: str) -> str:
    match = re.fullmatch(r"(.+)_\d+", name)
    return match.group(1) if match else name


def kept(workspace: Path) -> dict[str, int]:
    out = {}
    if workspace.is_dir():
        for item in workspace.iterdir():
            if item.is_dir() and not ws.is_reserved(item.name) and (n := count_files(item)):
                out[item.name] = n
    return dict(sorted(out.items()))


def trashed(workspace: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for name in ("groups", "items"):
        folder = area(workspace, name)
        for item in sorted(folder.iterdir()) if folder.is_dir() else ():
            key = _base(item.name) if name == "groups" else item.name
            out[key] = out.get(key, 0) + (count_files(item) if item.is_dir() else 1)
    return dict(sorted((k, v) for k, v in out.items() if v))


def summary(workspace: Path) -> dict:
    k, t = kept(workspace), trashed(workspace)
    return {"kept": k, "trashed": t, "totalKept": sum(k.values()), "totalTrashed": sum(t.values())}


def all_extensions(workspace: Path) -> list[str]:
    return sorted(set(kept(workspace)) | set(trashed(workspace)))


def _group_versions(workspace: Path, ext: str) -> list[Path]:
    folder = area(workspace, "groups")
    if not folder.is_dir():
        return []
    pattern = re.compile(rf"{re.escape(ext)}(_\d+)?")  # exact name, not a prefix (F18)
    found = [p for p in folder.iterdir() if p.is_dir() and pattern.fullmatch(p.name)]
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def group_name(ext: str) -> bool:
    """A group is one plain top-level folder name: no separators, drives or dot names."""
    return bool(ext) and not ws.is_reserved(ext) and Path(ext).name == ext and "\\" not in ext


def trash_group(workspace: Path, ext: str) -> tuple[bool, str]:
    if not group_name(ext):
        return False, f"Invalid group name: {ext!r}"
    source = workspace / ext
    if not source.is_dir():
        return False, f"Folder does not exist: {source}"
    dest = area(workspace, "groups")
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / ext
    index = 1
    while target.exists():
        target, index = dest / f"{ext}_{index}", index + 1
    count = count_files(source)
    shutil.move(str(source), str(target))
    return True, f"Moved {ext} to trash as {target.name} ({count} files)"


def _items(workspace: Path, ext: str) -> list[Path]:
    """The group's files trashed one by one in SORT (`.trash/items/<ext>/...`): the trashed
    count of a group includes them, so its RESTORE and DELETE take them too."""
    folder = area(workspace, "items") / ext
    return sorted(p for p in folder.rglob("*") if p.is_file()) if folder.is_dir() else []


def _restore_items(workspace: Path, ext: str) -> int:
    """Each item back to its own place (its provenance entry follows, as in SORT's undo)."""
    items, base = _items(workspace, ext), area(workspace, "items")
    for src in items:
        dest = ws.next_free(workspace / src.relative_to(base))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        moved(workspace, src, dest)
    shutil.rmtree(base / ext, ignore_errors=True)  # only the emptied folders are left there
    return len(items)


def restore_group(workspace: Path, ext: str) -> tuple[bool, str]:
    """The newest trashed version of the group, and every file of it trashed in SORT."""
    if not group_name(ext):
        return False, f"Invalid group name: {ext!r}"
    versions, said = _group_versions(workspace, ext), []
    if not versions and not _items(workspace, ext):
        return False, f"Nothing of {ext} in the trash"
    if versions:
        target = ws.next_free(workspace / ext)  # a kept group of that name: <ext>__N
        shutil.move(str(versions[0]), str(target))
        said.append(f"Restored {versions[0].name} from trash as {target.name}")
    if items := _restore_items(workspace, ext):
        said.append(f"restored {items} file(s) trashed in SORT")
    return True, "; ".join(said)


def delete_group(workspace: Path, ext: str) -> tuple[bool, str]:
    """Every trashed version of the group and every file of it trashed in SORT, for good."""
    if not group_name(ext):
        return False, f"Invalid group name: {ext!r}"
    versions, items = _group_versions(workspace, ext), _items(workspace, ext)
    if not versions and not items:
        return False, f"Nothing of {ext} in the trash"
    count = sum(count_files(v) for v in versions) + len(items)  # before deleting (v1 F9)
    for version in versions:
        shutil.rmtree(version)
    shutil.rmtree(area(workspace, "items") / ext, ignore_errors=True)
    return True, f"Permanently deleted the trashed {ext} ({count} files)"


def clear(workspace: Path) -> tuple[int, list[str]]:
    root = workspace / ws.TRASH_DIR
    if not root.is_dir():
        return 0, ["Trash is empty (no trash directory)"]
    entries = [p for name in AREAS if (a := root / name).is_dir() for p in a.iterdir()]
    messages = [
        f"  - {p.parent.name}/{p.name} ({count_files(p) if p.is_dir() else 1} files)"
        for p in entries
    ]
    shutil.rmtree(root)
    return len(entries), [f"[CLEAR] Deleted {len(entries)} item(s):", *messages]


def trash_files(workspace: Path, files: list[Path], area_name: str = "merger") -> int:
    dest = area(workspace, area_name)
    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    for src in files:
        if src.is_file():
            shutil.move(str(src), str(ws.next_free(dest / src.name)))
            moved += 1
    return moved
