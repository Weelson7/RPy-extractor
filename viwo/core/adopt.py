"""Convert a folder of the user's own files into a ViWo workspace (doc 4.3): every file moves
into the group of its type (`flac/`, `csv/`, `noext/`), its original path, sha256 and size
recorded in provenance (`kind: adopted`); the folders the moves emptied are removed. Nothing is
deleted, duplicates included; a dot-entry at the top (`.trash`, `.git`) is left alone. The
marker is written last, so an interrupted conversion can simply be run again."""

import json
import os
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

from .pipeline.collect import sha256
from .workspace import claim, workspace_lock


def _files(folder: Path) -> list[Path]:
    """Every file to adopt; files without an extension at the top go first (a top-level file
    `flac` must leave before the `flac/` group can be made)."""
    out = []
    for dirpath, dirnames, names in ws.walk(folder):
        if Path(dirpath) == folder:
            dirnames[:] = [d for d in dirnames if not ws.is_reserved(d)]
            names = [n for n in names if not ws.is_reserved(n)]
        out += [Path(dirpath) / n for n in names]
    return sorted(out, key=lambda p: (p.parent != folder or bool(p.suffix), p.as_posix()))


def _target(folder: Path, path: Path) -> Path:
    group = folder / ws.ext_folder(ws.ext_of(path))
    return path if path.parent == group else ws.next_free(group / path.name)


def preview(folder: Path) -> dict:
    """What a conversion would do: files, how many move, the groups, refused or not (a refused
    folder is not walked: the home folder would take minutes)."""
    refused = _refused(folder)
    files = [] if refused else _files(folder)
    moves = sum(1 for p in files if _target(folder, p) != p)
    groups = sorted({ws.ext_folder(ws.ext_of(p)) for p in files})
    return {"path": str(folder), "owned": ws.has_marker(folder), "files": len(files),
            "moves": moves, "groups": groups, "refused": refused}  # fmt: skip


def _refused(folder: Path) -> str:
    if not folder.is_dir():
        return f"not a folder: {folder}"
    if folder.parent == folder or folder.resolve() == Path.home().resolve():
        return "a drive root or the home folder is never converted"
    return ""


def _prune(folder: Path, left: set[Path]) -> None:
    """Remove the folders the moves emptied, deepest first; never the workspace itself."""
    for path in sorted(left, key=lambda p: len(p.parts), reverse=True):
        while path != folder and folder in path.parents:
            try:
                path.rmdir()  # only an empty folder goes
            except OSError:
                break
            path = path.parent


def adopt(folder: Path) -> dict:
    """Convert the folder; returns the preview fields plus `moved`."""
    if why := _refused(folder):
        raise ViwoError("refused", why)
    if ws.has_marker(folder):
        return {**preview(folder), "moved": 0}
    records, left = [], set()
    with workspace_lock(folder):
        for src in _files(folder):
            rel, target = src.relative_to(folder).as_posix(), _target(folder, src)
            if target != src:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(src, target)
                left.add(src.parent)
            new = target.relative_to(folder).as_posix()
            records.append({"path": new, "origin": f"adopted:{rel}", "sha256": sha256(target),
                            "size": target.stat().st_size, "kind": "adopted", "container": "",
                            "member": rel})  # fmt: skip
        _prune(folder, left)
        (folder / ws.METADATA_DIR).mkdir(exist_ok=True)
        with open(folder / ws.PROVENANCE_FILE, "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r, sort_keys=True) + "\n" for r in records)
        claim(folder)
    return {**preview(folder), "moved": sum(1 for r in records if r["path"] != r["member"])}
