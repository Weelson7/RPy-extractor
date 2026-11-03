"""Persisted survey reports: numbered files under viwo-data/surveys, never overwritten."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.workspace import inside

from .workspace import write_atomic

REPORT_ID = re.compile(r"^\d{8}-\d{6}-[A-Za-z0-9._-]+$")
HEADER = ("id", "when", "folder", "deep", "gameCount", "path")


def _slug(name: str) -> str:
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "survey")[:40]


def save(root_dir: Path, folder: Path, deep: bool, games: list[dict]) -> dict:
    """Write one report; a name clash gets a -2, -3... suffix instead of overwriting."""
    root_dir.mkdir(parents=True, exist_ok=True)
    base = f"{time.strftime('%Y%m%d-%H%M%S')}-{_slug(folder.name)}"
    report_id, n = base, 1
    while (root_dir / f"{report_id}.json").exists():
        n += 1
        report_id = f"{base}-{n}"
    path = root_dir / f"{report_id}.json"
    report = {
        "id": report_id,
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "folder": str(folder),
        "deep": bool(deep),
        "gameCount": len(games),
        "path": str(path),
        "games": games,
    }
    write_atomic(path, json.dumps(report, indent=1))
    return {k: report[k] for k in HEADER}


def _path(root_dir: Path, report_id: str) -> Path:
    if not REPORT_ID.match(str(report_id)):
        raise ViwoError("invalid_request", f"not a survey report id: {report_id!r}")
    path = root_dir / f"{report_id}.json"
    if not inside(root_dir, path) or not path.is_file():
        raise ViwoError("not_found", f"no survey report {report_id}")
    return path


def load(root_dir: Path, report_id: str) -> dict:
    return json.loads(_path(root_dir, report_id).read_text(encoding="utf-8"))


def _order(path: Path) -> tuple[str, int, str]:
    """Newest first by the id's timestamp, then by the collision number (-2, -3...)."""
    stem = path.stem
    tail = stem.rsplit("-", 1)[-1]
    return stem[:15], int(tail) if tail.isdigit() and len(tail) < 4 else 1, stem


def list_reports(root_dir: Path) -> list[dict]:
    """Headers of every report, newest first (unreadable files are skipped)."""
    out, files = [], list(root_dir.glob("*.json")) if root_dir.is_dir() else []
    for path in sorted(files, key=_order, reverse=True):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            out.append({k: report.get(k) for k in HEADER})
        except (OSError, ValueError):
            continue
    return out
