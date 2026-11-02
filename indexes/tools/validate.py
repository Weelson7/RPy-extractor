"""Validate every index entry under games/ (stdlib only; exit 1 on any problem).

Usage: python tools/validate.py [indexes root]      (default: the folder above this script)
Checks the schema, the folder names against slug/game_version, and (when ViWo is importable)
that every tool id exists in viwo/data/tools.json.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SECRET = re.compile(r"key|secret|password", re.I)


def basic(entry: dict, slug: str, version: str) -> list[str]:
    out = []
    if entry.get("schema") != 1:
        out.append("schema must be 1")
    if entry.get("slug") != slug or not SLUG.fullmatch(slug):
        out.append(f"slug must be {slug!r} (lowercase, digits, dashes)")
    if entry.get("game_version") != version or not VERSION.fullmatch(version):
        out.append(f"game_version must be {version!r}")
    for key in ("title", "engine"):
        if not str(entry.get(key, "")).strip():
            out.append(f"{key} is required")
    if not isinstance(entry.get("detect"), list) or not entry["detect"]:
        out.append("detect needs at least one relative marker")
    for plugin, values in (entry.get("options") or {}).items():
        for key in values or {}:
            if SECRET.search(key):
                out.append(f"options.{plugin}.{key}: no secrets in an index")
    for item in entry.get("scripts") or []:
        if not str(item.get("url", "")).startswith("https://"):
            out.append(f"scripts: {item.get('name')}: https only")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            out.append(f"scripts: {item.get('name')}: sha256 missing")
    return out


def main() -> int:
    try:
        from viwo.core.indexes import validate as full
    except ImportError:
        full = None
    bad = 0
    for file in sorted((ROOT / "games").glob("*/*/index.json")):
        slug, version = file.parent.parent.name, file.parent.name
        try:
            entry = json.loads(file.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"{file}: not JSON: {exc}")
            bad += 1
            continue
        problems = basic(entry, slug, version) + (full(entry) if full else [])
        for problem in dict.fromkeys(problems):
            print(f"{slug}/{version}: {problem}")
        bad += bool(problems)
    print(f"{bad} invalid entr{'y' if bad == 1 else 'ies'}" if bad else "all index entries valid")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
