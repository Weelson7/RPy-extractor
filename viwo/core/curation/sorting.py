"""Sorting window operations (keep / item trash / rename / undo / save / preview).

Response shapes match the v1 API (doc 4.1). Paths travel URL-encoded and
workspace-relative; every resolved path must stay inside the workspace.
"""

import shutil
from pathlib import Path
from urllib.parse import quote, unquote

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.contracts.os import FileSystemPolicy

from .. import provenance
from ..media import IMAGE, TEXT, media_type  # noqa: F401  (the sort filters use the sets)
from .trash import area

TEXT_BYTES = frozenset(range(32, 127)) | {9, 10, 13} | frozenset(range(128, 256))  # UTF-8


def encode(workspace: Path, path: Path) -> str:
    return "/".join(quote(part, safe="") for part in path.relative_to(workspace).parts)


def resolve(workspace: Path, encoded: str) -> Path:
    if not encoded:
        raise ViwoError("invalid_request", "Missing asset path")
    root = workspace.resolve()
    path = (root / unquote(encoded)).resolve()
    if root not in path.parents or ws.is_reserved(path.relative_to(root).parts[0]):
        raise ViwoError("invalid_request", "Invalid asset path")
    if not path.is_file():
        raise ViwoError("not_found", f"Asset not found: {unquote(encoded)}")
    return path


RANK = {"image": 0, "audio": 1, "video": 2, "text": 3}  # what shows a preview comes first


def asset_files(workspace: Path) -> list[Path]:
    """The sort queue: previewable files first (images, audio, video, text), then the rest, each
    in path order, so a session opens on something to look at rather than on raw blobs."""
    files = (
        p
        for p in workspace.rglob("*")
        if p.is_file() and not ws.is_reserved(p.relative_to(workspace).parts[0])
    )
    return sorted(files, key=lambda p: (RANK.get(media_type(p.suffix.lower()), 4), p))


def list_window(workspace: Path, offset: int, limit: int) -> dict:
    files = asset_files(workspace) if workspace.is_dir() else []
    offset, limit = max(0, offset), max(1, limit)
    page = files[offset : offset + limit]
    assets = [
        {
            "name": p.name,
            "path": encode(workspace, p),
            "ext": ws.ext_of(p),
            "size": p.stat().st_size,
            "type": media_type(p.suffix.lower()),
        }
        for p in page
    ]
    return {
        "success": True,
        "assets": assets,
        "assetPath": str(workspace),
        "totalCount": len(files),
        "indexedCount": len(assets),
        "indexedLimit": limit,
        "offset": offset,
        "truncated": offset + limit < len(files),
    }


def keep(workspace: Path, encoded: str, history: list[dict]) -> dict:
    path = resolve(workspace, encoded)
    history.append({"action": "keep", "path": str(path)})
    return {"success": True, "action": "keep", "path": encoded, "name": path.name}


def trash_item(workspace: Path, encoded: str, history: list[dict]) -> dict:
    path = resolve(workspace, encoded)
    rel = path.relative_to(workspace.resolve())
    target = ws.next_free(area(workspace, "items") / rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))
    provenance.moved(workspace, path, target)
    history.append({"action": "trash", "source": str(path), "target": str(target)})
    return {"success": True, "action": "trash", "path": encoded, "name": rel.name}


def rename(
    workspace: Path, encoded: str, new_name: str, history: list[dict], fs: FileSystemPolicy
) -> dict:
    path = resolve(workspace, encoded)
    new_name = new_name.strip()
    if not fs.is_valid_filename(new_name):
        raise ViwoError("invalid_request", "Invalid filename")
    target = path.parent / new_name
    if target.exists() and target != path:
        raise ViwoError("invalid_request", f"File already exists: {new_name}")
    path.rename(target)
    provenance.moved(workspace, path, target)
    history.append({"action": "rename", "old_path": str(path), "new_path": str(target)})
    return {
        "success": True,
        "action": "rename",
        "oldPath": encoded,
        "newPath": encode(workspace.resolve(), target),
        "name": target.name,
    }


def _restore(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    index, target = 1, dest
    while target.exists():
        target = dest.with_name(f"{dest.stem}__undo{index}{dest.suffix}")
        index += 1
    shutil.move(str(src), str(target))
    return target


def undo(workspace: Path, history: list[dict]) -> dict:
    if not history:
        raise ViwoError("invalid_request", "No actions to undo")
    last = history.pop()
    action, root = last.get("action", ""), workspace.resolve()
    if action == "keep":
        return {"success": True, "undone": "keep"}
    moved_from, moved_to = ("target", "source") if action == "trash" else ("new_path", "old_path")
    current = Path(last.get(moved_from, ""))
    if action not in ("trash", "rename") or not current.exists():
        raise ViwoError("not_found", f"Cannot undo {action}: file no longer exists")
    restored = _restore(current, Path(last[moved_to]))
    provenance.moved(workspace, current, restored)
    result = {"success": True, "undone": action, "path": encode(root, restored)}
    if action == "rename":
        result["previousPath"] = encode(root, current)
    return result


def save_remaining(workspace: Path, encoded_paths: list[str], destination: Path) -> dict:
    if not destination.is_dir():
        raise ViwoError("invalid_request", f"Destination folder does not exist: {destination}")
    moved, skipped, failures = 0, 0, []
    for encoded in encoded_paths:
        try:
            src = resolve(workspace, encoded)
        except ViwoError as exc:
            skipped += 1
            failures += [exc.message] if exc.code != "not_found" else []
            continue
        target = ws.next_free(destination / src.relative_to(workspace.resolve()))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(target))
        moved += 1
    return {
        "success": True,
        "moved": moved,
        "skipped": skipped,
        "failures": failures,
        "destinationPath": str(destination),
    }


def preview(workspace: Path, encoded: str, max_lines: int = 50) -> dict:
    path = resolve(workspace, encoded)
    kind, name = media_type(path.suffix.lower()), path.name
    if kind in ("image", "audio", "video"):
        return {
            "success": True,
            "type": kind,
            "name": name,
            "url": f"/preview/{encode(workspace.resolve(), path)}",
        }
    try:
        with path.open("rb") as fh:
            head = fh.read(4096)
        printable = sum(b in TEXT_BYTES for b in head) if head else 1
        if head and (b"\0" in head or printable < 0.9 * len(head)):
            raise OSError("binary")  # game data (.lmp, .bin...) is not text
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = [line.rstrip("\n") for _, line in zip(range(max_lines + 1), fh)]
    except OSError:
        return {
            "success": True,
            "type": "binary",
            "name": name,
            "message": "Binary data: no preview. Open the folder to use another tool.",
        }
    truncated = len(lines) > max_lines
    lines = lines[:max_lines]
    return {
        "success": True,
        "type": "text",
        "name": name,
        "lineCount": len(lines),
        "content": "\n".join(lines),
        "truncated": truncated,
    }
