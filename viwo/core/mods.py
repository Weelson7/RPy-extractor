"""T2 mod packages (doc 16.2b, patching arm): what a patched copy changed, as one distributable
zip. `pack` compares a patched copy with the game (size and time first, then sha256) and stores
every changed or added file at its game-relative path, with `viwo-mod.json` naming each file's
original and new hash. `check` tells whether a mod fits an install (the originals match);
`apply` writes a mod into a patched copy. The game folder itself is only ever read."""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
import zipfile
from pathlib import Path

from viwo import __version__
from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

from .roundtrip import MARKER, prepare_copy

MANIFEST = "viwo-mod.json"
SKIP = {MARKER, ws.METADATA_DIR}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def changes(game: Path, copy: Path) -> list[dict]:
    """Files of `copy` that differ from `game` (or are new), game-relative."""
    out = []
    for path in sorted(p for p in copy.rglob("*") if p.is_file()):
        rel = path.relative_to(copy)
        if rel.parts[0] in SKIP:
            continue
        original = game / rel
        if original.is_file():
            a, b = original.stat(), path.stat()
            if a.st_size == b.st_size and a.st_mtime_ns == b.st_mtime_ns:
                continue  # copy2 keeps times: an untouched file
            old = _sha(original)
            if old == _sha(path):
                continue
        else:
            old = ""
        out.append({"path": rel.as_posix(), "original": old, "sha256": _sha(path)})
    return out


def pack(game: Path, copy: Path, out: Path, name: str = "") -> dict:
    if not (copy / MARKER).is_dir():
        raise ViwoError("invalid_request", f"{copy} is not a ViWo patched copy")
    files = changes(game, copy)
    if not files:
        raise ViwoError("failed", "the patched copy does not differ from the game")
    manifest = {
        "schema": 1,
        "name": name or out.stem,
        "game": game.name,
        "made": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "viwo": __version__,
        "files": files,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, json.dumps(manifest, indent=1))
        for item in files:
            archive.write(copy / item["path"], f"files/{item['path']}")
    return {"mod": str(out), "files": len(files), "manifest": manifest}


def read_manifest(mod: Path) -> dict:
    try:
        with zipfile.ZipFile(mod) as archive:
            return json.loads(archive.read(MANIFEST))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise ViwoError("invalid_request", f"{mod} is not a ViWo mod: {exc}") from exc


def check(game: Path, mod: Path) -> dict:
    """Per file: fits (the original is there), new (an added file), differs (another version
    of the game), installed (the new bytes are already there)."""
    rows = []
    for item in read_manifest(mod)["files"]:
        rel = ws.safe_member(item["path"])
        target = game.joinpath(*rel.parts) if rel else None
        current = _sha(target) if target is not None and target.is_file() else ""
        state = (
            "installed"
            if current == item["sha256"]
            else "fits"
            if current == item["original"] and current
            else "new"
            if not item["original"] and not current
            else "differs"
        )
        rows.append({"path": item["path"], "state": state})
    return {"mod": str(mod), "fits": all(r["state"] != "differs" for r in rows), "files": rows}


def apply(rt, game: Path, mod: Path, copy: Path) -> dict:
    """The mod's files into a patched copy (made from the game first when `copy` is not one)."""
    report = check(copy if (copy / MARKER).is_dir() else game, mod)
    if not report["fits"]:
        bad = [r["path"] for r in report["files"] if r["state"] == "differs"]
        raise ViwoError("failed", "the mod was made for another version: " + ", ".join(bad[:5]))
    if not (copy / MARKER).is_dir():
        rt.temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=rt.temp_root) as tmp:
            prepare_copy(game, copy, Path(tmp))
    with zipfile.ZipFile(mod) as archive:
        for row in report["files"]:
            rel = ws.safe_member(row["path"])
            target = copy.joinpath(*rel.parts) if rel is not None else None
            if target is None or not ws.inside(copy, target):
                raise ViwoError("refused", f"unsafe path in the mod: {row['path']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(f"files/{row['path']}"))
    return {**report, "copy": str(copy), "applied": len(report["files"])}
