"""T2 mod packages (doc 16.2b, patching arm): what a patched copy changed, as one distributable
zip. `pack` compares a patched copy with the game (size and time first, then sha256) and stores
every changed or added file at its game-relative path, with `viwo-mod.json` naming each file's
original and new hash, the mod's `requires` / `after`, and the AOB patch sets it was built from.
`check` tells whether a mod fits an install, or adapts to another version through those AOB
patches (the update check); `apply` writes mods in load order into a patched copy and refuses
conflicts. The game folder itself is only ever read. The in-game side of a mod framework
(loader, hooks, overlay) is the pinned runtime loaders' (BepInEx, UE4SS; doc 11.2)."""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

from viwo import __version__
from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

from . import patchsets
from .pipeline.collect import sha256
from .roundtrip import MARKER, prepare_copy

MANIFEST = "viwo-mod.json"
SKIP = {MARKER, ws.METADATA_DIR}


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
            old = sha256(original)
            if old == sha256(path):
                continue
        else:
            old = ""
        out.append({"path": rel.as_posix(), "original": old, "sha256": sha256(path)})
    return out


def pack(game: Path, copy: Path, out: Path, name: str = "", needs: dict | None = None) -> dict:
    """The zip: changed files, the AOB patch sets the copy was patched with (so the mod adapts
    to another game version), and `requires` / `after` (names of other mods) for load order."""
    if not (copy / MARKER).is_dir():
        raise ViwoError("invalid_request", f"{copy} is not a ViWo patched copy")
    if out.resolve().is_relative_to(game.resolve()):
        raise ViwoError("refused", f"the mod ({out}) is inside the game folder")
    files = changes(game, copy)
    if not files:
        raise ViwoError("failed", "the patched copy does not differ from the game")
    sets = sorted((copy / MARKER).glob("*.aob.patch.json"))
    manifest = {
        "schema": 1,
        "name": name or out.stem,
        "game": game.name,
        "made": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "viwo": __version__,
        "requires": list((needs or {}).get("requires", [])),
        "after": list((needs or {}).get("after", [])),
        "patches": [p.name for p in sets],
        "files": files,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, json.dumps(manifest, indent=1))
        for item in files:
            archive.write(copy / item["path"], f"files/{item['path']}")
        for patch_set in sets:
            archive.write(patch_set, f"patches/{patch_set.name}")
    return {"mod": str(out), "files": len(files), "manifest": manifest}


def read_manifest(mod: Path) -> dict:
    try:
        with zipfile.ZipFile(mod) as archive:
            return json.loads(archive.read(MANIFEST))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise ViwoError("invalid_request", f"{mod} is not a ViWo mod: {exc}") from exc


def _patched_files(mod: Path, manifest: dict) -> dict[str, list[dict]]:
    """file -> the AOB patches the mod carries for it."""
    out: dict[str, list[dict]] = {}
    with zipfile.ZipFile(mod) as archive:
        for name in manifest.get("patches", []):
            for patch in json.loads(archive.read(f"patches/{name}")).get("patches", []):
                out.setdefault(patch["file"], []).append(patch)
    return out


def check(game: Path, mod: Path) -> dict:
    """Per file: fits (the original is there), new (an added file), installed (the new bytes
    are there), adapts (another version, but the mod's AOB patches resolve in it: the update
    check), differs (another version the mod cannot follow)."""
    manifest, rows = read_manifest(mod), []
    patched = _patched_files(mod, manifest)
    for item in manifest["files"]:
        rel = ws.safe_member(item["path"])
        target = game.joinpath(*rel.parts) if rel else None
        current = sha256(target) if target is not None and target.is_file() else ""
        state = (
            "installed"
            if current == item["sha256"]
            else "fits"
            if current == item["original"] and current
            else "new"
            if not item["original"] and not current
            else "differs"
        )
        if state == "differs" and item["path"] in patched:
            plan = patchsets.plan(game, {"patches": patched[item["path"]]})
            state = "adapts" if plan["ok"] else "differs"
        rows.append({"path": item["path"], "state": state})
    return {
        "mod": str(mod),
        "name": manifest.get("name", ""),
        "fits": all(r["state"] != "differs" for r in rows),
        "files": rows,
    }


def order(mods: list[Path]) -> list[Path]:
    """Load order: a mod comes after everything it `requires` or names in `after`; a missing
    requirement or a cycle is refused."""
    names = [read_manifest(m).get("name", m.stem) for m in mods]
    twice = sorted({n for n in names if names.count(n) > 1})
    if twice:  # one would silently replace the other
        raise ViwoError("invalid_request", f"two mods share the name {', '.join(twice)}")
    by_name = dict(zip(names, mods))
    needs = {name: read_manifest(m) for name, m in by_name.items()}
    done: list[str] = []

    def visit(name: str, trail: tuple[str, ...]) -> None:
        if name in done:
            return
        if name in trail:
            raise ViwoError(
                "invalid_request", f"mod load order has a cycle: {' -> '.join(trail + (name,))}"
            )
        for dep in needs[name].get("requires", []):
            if dep not in by_name:
                raise ViwoError(
                    "invalid_request", f"mod {name} requires {dep}, which is not in the list"
                )
        for dep in [*needs[name].get("requires", []), *needs[name].get("after", [])]:
            if dep in by_name:
                visit(dep, trail + (name,))
        done.append(name)

    for name in by_name:
        visit(name, ())
    return [by_name[name] for name in done]


def conflicts(mods: list[Path]) -> list[str]:
    """Two mods writing one file differently, unless the later one declares `after` the other
    (an explicit override)."""
    seen: dict[str, tuple[str, str]] = {}
    found = []
    for mod in mods:
        manifest = read_manifest(mod)
        name = manifest.get("name", mod.stem)
        for item in manifest["files"]:
            if item["path"] in seen and seen[item["path"]][1] != item["sha256"]:
                other = seen[item["path"]][0]
                if other not in manifest.get("after", []) and other not in manifest.get(
                    "requires", []
                ):
                    found.append(f"{item['path']}: {other} and {name}")
            seen[item["path"]] = (name, item["sha256"])
    return found


def _adapt(copy: Path, path: str, patches: list[dict]) -> None:
    """Each AOB patch is already there, or written and read back; anything else stops the
    apply with the patch's own reason (a half-adapted file is never left unsaid)."""
    for patch in patches:
        found = patchsets.locate(copy, patch)
        if found["status"] == "already":
            continue
        if found["status"] != "ready" or not patchsets.write(copy, patch, found):
            why = found["reason"] or "the written bytes did not read back"
            raise ViwoError("failed", f"{path}: a patch of the mod did not apply ({why})")


def _apply_one(mod: Path, copy: Path) -> dict:
    report = check(copy, mod)
    if not report["fits"]:
        bad = [r["path"] for r in report["files"] if r["state"] == "differs"]
        raise ViwoError(
            "failed", f"{report['name']} was made for another version: " + ", ".join(bad[:5])
        )
    manifest = read_manifest(mod)
    patched = _patched_files(mod, manifest)
    with zipfile.ZipFile(mod) as archive:
        for row in report["files"]:
            target = ws.member_path(copy, row["path"])
            if target is None:
                raise ViwoError("refused", f"unsafe path in the mod: {row['path']}")
            if row["state"] == "adapts":  # another version: the AOB patches, not the file
                _adapt(copy, row["path"], patched[row["path"]])
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(f"files/{row['path']}"))
    return report


def apply(rt, game: Path, mods: list[Path], copy: Path, sink=None) -> dict:
    """Mods in load order into one patched copy (made from the game first when `copy` is not
    one); conflicts between them are refused before anything is written."""
    mods = order(list(mods))
    clash = conflicts(mods)
    if clash:
        raise ViwoError(
            "refused",
            "mods conflict: " + "; ".join(clash[:5]),
            hint="declare `after` in the mod that should win",
        )
    left = prepare_copy(rt, game, copy, sink, "mod", reuse=True)
    reports = [_apply_one(mod, copy) for mod in mods]
    return {
        "copy": str(copy),
        "order": [r["name"] for r in reports],
        "mods": reports,
        "applied": sum(len(r["files"]) for r in reports),
        "notCopied": left,  # files the OS refused to copy (also a warn event)
    }
