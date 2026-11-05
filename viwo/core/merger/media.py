"""Merger inputs: media entries, candidate groups, selection expansion (v1 semantics)."""

import re
from pathlib import Path
from typing import Any

from ..media import AUDIO, IMAGE, VIDEO, media_type  # noqa: F401

TIMELINE = IMAGE | VIDEO
PATTERNS = ("number-to-name", "name-to-number")


def natural(value: str) -> list[Any]:
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", value)]


def split_name(stem: str, pattern: str) -> tuple[str, str]:
    """('hero', '01') from '01_hero' (number-to-name) or 'hero_01' (name-to-number)."""
    trimmed = stem.strip()
    if not trimmed:
        return "untitled", ""
    regex = (
        r"^(?P<idx>\d+)[\s._-]*(?P<name>.+)$"
        if pattern == "number-to-name"
        else r"^(?P<name>.+?)[\s._-]*(?P<idx>\d+)$"
    )
    match = re.match(regex, trimmed)
    if not match:
        return trimmed, ""
    return (match["name"].strip(" _.-") or trimmed), match["idx"].strip()


def list_entries(folder: Path, allowed: set[str] | None = None) -> list[dict[str, str]]:
    exts = {e.lower() for e in (allowed or TIMELINE)}
    entries = []
    for path in folder.rglob("*") if folder.is_dir() else ():
        rel = path.relative_to(folder)
        if path.is_file() and not any(p.startswith(".") for p in rel.parts):
            if path.suffix.lower() in exts:
                entries.append(
                    {
                        "path": rel.as_posix(),
                        "name": path.name,
                        "stem": path.stem,
                        "ext": path.suffix.lower(),
                        "type": media_type(path.suffix),
                    }
                )
    return sorted(entries, key=lambda e: natural(e["path"]))


def summarize(entries: list[dict[str, str]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["ext"]] = counts.get(entry["ext"], 0) + 1
    return [{"ext": e, "count": c} for e, c in sorted(counts.items(), key=lambda i: natural(i[0]))]


def _conflicts(files: list[dict], pattern: str) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for entry in files:
        index = split_name(entry["stem"], pattern)[1]
        if index:
            buckets.setdefault(index, []).append(entry)
    return [
        {
            "index": idx,
            "options": [
                {"path": f["path"], "ext": f["ext"], "type": f["type"]}
                for f in sorted(b, key=lambda f: natural(f["name"]))
            ],
        }
        for idx, b in sorted(buckets.items(), key=lambda i: natural(i[0]))
        if len(b) > 1 and len({f["type"] for f in b}) > 1
    ]


def candidates(entries: list[dict], pattern: str, include_files: bool = True) -> list[dict]:
    groups: dict[str, dict] = {}
    for entry in entries:
        name, index = split_name(entry["stem"], pattern)
        group = groups.setdefault(name.lower(), {"name": name, "indexes": [], "files": []})
        group["files"].append(entry)
        if index and index not in group["indexes"]:
            group["indexes"].append(index)
    out = []
    for group in sorted(groups.values(), key=lambda g: natural(g["name"])):
        files = sorted(group["files"], key=lambda f: natural(f["name"]))
        payload = [
            {
                "path": f["path"],
                "ext": f["ext"],
                "type": f["type"],
                "parsedIndex": split_name(f["stem"], pattern)[1],
            }
            for f in files
        ]
        out.append(
            {
                "name": group["name"],
                "indexes": sorted(group["indexes"], key=natural),
                "files": payload if include_files else [],
                "conflicts": _conflicts(files, pattern),
                "count": len(files),
            }
        )
    return out


def _times(raw: Any) -> int:
    try:
        return max(1, int(str(raw).strip()))
    except ValueError:
        return 1


def _ordered(candidate: dict, resolutions: dict) -> list[str]:
    """File order with same-index conflicts resolved as the user ordered them."""
    buckets: dict[str, list[str]] = {}
    for f in candidate["files"]:
        buckets.setdefault(f["parsedIndex"] or f"__single__{f['path']}", []).append(f["path"])
    conflict_indexes = {c["index"] for c in candidate["conflicts"]}
    ordered: list[str] = []
    for key, paths in buckets.items():
        wanted = resolutions.get(key, []) if key in conflict_indexes else []
        first = [p for p in wanted if p in paths] if isinstance(wanted, list) else []
        for path in first + paths:
            if path not in ordered:
                ordered.append(path)
    return ordered


def expand(entries: list[dict], pattern: str, specs: list[dict]) -> list[str]:
    """Selected candidates -> timeline paths (conflict order, part loops, entirety loops)."""
    by_name = {c["name"].lower(): c for c in candidates(entries, pattern)}
    out: list[str] = []
    for spec in specs:
        candidate = by_name.get(str(spec.get("name", "")).strip().lower())
        if not candidate:
            continue
        index_of = {f["path"]: f["parsedIndex"] for f in candidate["files"]}
        loops: dict[str, int] = {}
        for row in spec.get("partLoops") or []:
            if isinstance(row, dict):
                for idx in re.split(r"[\s,;]+", str(row.get("indexes") or "")):
                    loops[idx] = _times(row.get("times", 1)) if idx else 1
        resolutions = spec.get("conflictResolutions") or {}
        parts = [
            p for p in _ordered(candidate, resolutions) for _ in range(loops.get(index_of[p], 1))
        ]
        out += parts * _times(spec.get("entiretyTimes", 1))
    return out
