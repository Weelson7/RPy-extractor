"""Edit set for the round trip (doc 18.2): modified workspace files found by hash against the
provenance map, files the user adds under `_added/<target path>`, and the same-format rule
(doc 18.3 RESOLVE): an edit whose bytes no longer match the member's format is rejected."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from viwo.contracts import workspace as ws

from .pipeline.collect import sha256
from .provenance import entries

ADDED_DIR = "_added"  # <workspace>/_added/<game-relative path> -> loose file in the patched copy
MAGIC = {
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8",),
    ".jpeg": (b"\xff\xd8",),
    ".gif": (b"GIF8",),
    ".bmp": (b"BM",),
    ".webp": (b"RIFF",),
    ".dds": (b"DDS ",),
    ".ogg": (b"OggS",),
    ".wav": (b"RIFF",),
    ".flac": (b"fLaC",),
    ".mp3": (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06"),
    ".7z": (b"7z\xbc\xaf",),
    ".rar": (b"Rar!",),
}


@dataclass
class Edit:
    file: Path
    kind: str  # loose | member | exported | added
    container: str
    member: str
    plugin: str = ""  # owner of "exported" files


def format_ok(file: Path, member: str) -> bool:
    """Same-format rule (18.3): an edit may not turn a member into a recognisably different
    format. A `.png` member that now starts with JPEG magic is rejected; bytes that match no
    known magic at all are accepted (synthetic or unknown data)."""
    magics = MAGIC.get(Path(member).suffix.lower())
    if magics is None:
        return True
    with open(file, "rb") as fh:
        head = fh.read(8)
    if any(head.startswith(m) for m in magics):
        return True
    others = (m for suffix, ms in MAGIC.items() for m in ms if ms is not magics)
    return not any(head.startswith(m) for m in others)


def original_hashes(workspace: Path) -> dict[str, dict[str, str]]:
    """container -> {member path: original sha256}, for the untouched-member check (18.3)."""
    out: dict[str, dict[str, str]] = {}
    for entry in entries(workspace):
        if entry.get("kind") == "member" and entry.get("container"):
            out.setdefault(entry["container"], {})[entry["member"]] = entry["sha256"]
    return out


def added_files(workspace: Path) -> list[Edit]:
    """Files the user placed under _added/, keyed by their target path in the game."""
    root = workspace / ADDED_DIR
    if not root.is_dir():
        return []
    edits = []
    for file in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = ws.safe_member(file.relative_to(root).as_posix())
        if rel is not None:
            edits.append(Edit(file, "added", "", rel.as_posix()))
    return edits


def edit_set(workspace: Path) -> tuple[list[Edit], list[str]]:
    """Workspace files whose content differs from what extraction wrote, plus added files."""
    edits, skipped, missing = [], [], []
    for entry in entries(workspace):
        rel = ws.safe_member(entry["path"])
        file = workspace.joinpath(*rel.parts) if rel else None
        if file is None or not file.is_file():
            missing.append(entry["path"])
            continue
        if sha256(file) == entry["sha256"]:
            continue
        kind = entry.get("kind", "derived")
        member = entry.get("member", "")
        if kind not in ("loose", "member", "exported"):
            skipped.append(f"{entry['path']}: {kind} file, writing it back is not supported yet")
        elif kind != "exported" and not format_ok(file, member or entry["path"]):
            skipped.append(f"{entry['path']}: format differs from the original member (18.3)")
        else:
            edits.append(
                Edit(file, kind, entry.get("container", ""), member, entry.get("plugin", ""))
            )
    if missing:  # renamed, moved or trashed since extraction: their edits cannot be traced
        shown = ", ".join(missing[:5]) + (
            f" and {len(missing) - 5} more" if len(missing) > 5 else ""
        )
        skipped.append(f"{len(missing)} extracted file(s) were moved, renamed or trashed: {shown}")
    return edits + added_files(workspace), skipped
