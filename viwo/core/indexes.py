"""Per-game indexes (community data, `indexes/`): what a game needs and how to recognize it.

An index entry (`games/<slug>/<game-version>/index.json`) names the engine, detection markers,
plugins to enable, plugin options (never secrets), the pinned tools it needs and QuickBMS scripts
pinned by sha256. `install_game` installs the tools through the preflight and the scripts into
third_party/quickbms/scripts (HTTPS only, checksum verified). The folder is laid out as the
future `vidya_wormhole_indexes` submodule root (docs/indexes.md).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from viwo.contracts.errors import ViwoError

from . import thirdparty
from .steps import teller
from .wiring.boot import DEFAULT_INI

SCHEMA = 1
DEFAULT_ROOT = DEFAULT_INI.parent / "indexes"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SCRIPT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.bms$")
SECRET_KEY = re.compile(r"key|secret|password", re.I)
LISTS = ("detect", "plugins", "tools", "scripts")


def _known_tools() -> set[str]:
    data = thirdparty.manifest()
    tools = {k for k, v in data["tools"].items() if not v.get("hidden")}
    return tools | set(data["python"]) | {k for k in data.get("workers", {}) if k[0] != "_"}


def list_games(root: Path = DEFAULT_ROOT) -> dict[str, list[str]]:
    """slug -> game versions that have an index.json."""
    games: dict[str, list[str]] = {}
    for file in sorted((root / "games").glob("*/*/index.json")):
        games.setdefault(file.parent.parent.name, []).append(file.parent.name)
    return games


def load_index(root: Path, slug: str, game_version: str = "any") -> dict:
    if not SLUG.fullmatch(slug) or not VERSION.fullmatch(game_version):
        raise ViwoError("invalid_request", f"bad index name: {slug}/{game_version}")
    file = root / "games" / slug / game_version / "index.json"
    if not file.is_file():
        raise ViwoError("not_found", f"no index for {slug} ({game_version})", hint=str(file))
    try:
        entry = json.loads(file.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ViwoError("invalid_request", f"{file}: not JSON ({exc})")
    problems = validate(entry)
    if problems or entry.get("slug") != slug or entry.get("game_version") != game_version:
        hint = "; ".join(problems) or "slug/game_version do not match the folder"
        raise ViwoError("invalid_request", f"invalid index {slug}/{game_version}", hint=hint)
    return entry


def _validate_scripts(scripts, out: list[str]) -> None:
    for item in scripts:
        if not isinstance(item, dict):
            out.append("scripts: every item must be an object")
            continue
        name, url = str(item.get("name", "")), str(item.get("url", ""))
        if not SCRIPT_NAME.fullmatch(name):
            out.append(f"scripts: bad name {name!r} (want <ext>.bms, no path)")
        if not url.startswith("https://"):
            out.append(f"scripts: {name}: url must be https")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            out.append(f"scripts: {name}: sha256 missing or malformed")
        if not isinstance(item.get("size"), int) or item["size"] <= 0:
            out.append(f"scripts: {name}: size must be a positive integer")


def validate(entry: dict) -> list[str]:
    """Problems with one index entry (empty = valid). Pure: no network, no filesystem."""
    out: list[str] = []
    if not isinstance(entry, dict):
        return ["entry must be an object"]
    if entry.get("schema") != SCHEMA:
        out.append(f"schema must be {SCHEMA}")
    if not SLUG.fullmatch(str(entry.get("slug", ""))):
        out.append("slug: lowercase letters, digits and dashes only")
    if not VERSION.fullmatch(str(entry.get("game_version", ""))):
        out.append("game_version: letters, digits, dots, dashes (or 'any')")
    for key in ("title", "engine"):
        if not str(entry.get(key, "")).strip():
            out.append(f"{key} is required")
    for key in LISTS:
        if not isinstance(entry.get(key, []), list):
            out.append(f"{key} must be a list")
    if not entry.get("detect"):
        out.append("detect needs at least one marker (relative path or glob)")
    for marker in entry.get("detect", []) if isinstance(entry.get("detect"), list) else []:
        if not isinstance(marker, str) or marker.startswith(("/", "\\")) or ".." in marker:
            out.append(f"detect: {marker!r} must be a relative path or glob")
    options = entry.get("options", {})
    if not isinstance(options, dict):
        out.append("options must be an object of plugin -> {key: value}")
    else:
        for plugin, values in options.items():
            for key in values if isinstance(values, dict) else []:
                if SECRET_KEY.search(str(key)):
                    out.append(f"options.{plugin}.{key}: secrets never live in an index")
    known = _known_tools()
    for tool in entry.get("tools", []) if isinstance(entry.get("tools"), list) else []:
        if tool not in known:
            out.append(f"tools: unknown dependency id {tool!r} (not in tools.json)")
    if isinstance(entry.get("scripts"), list):
        _validate_scripts(entry["scripts"], out)
    return out


def _install_script(item: dict, folder: Path, say, cancel) -> str:
    target = folder / item["name"]
    if target.is_file():
        if hashlib.sha256(target.read_bytes()).hexdigest() == item["sha256"]:
            return "present"
        raise ViwoError(
            "refused", f"{item['name']} already exists with another checksum; not replaced"
        )
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".script-", dir=folder) as tmp:
        file = Path(tmp) / item["name"]
        if thirdparty._download(item["url"], file, item["size"], say, cancel) != item["sha256"]:
            raise ViwoError("refused", f"{item['name']}: checksum mismatch, not installed")
        file.replace(target)
    return "installed"


def install_game(rt, root: Path, slug: str, version: str = "any", sink=None, cancel=None) -> dict:
    """Install what one index entry needs: pinned tools (preflight) and QuickBMS scripts."""
    from .preflight import install

    entry = load_index(root, slug, version)
    say = teller(sink, "index")
    scripts_dir = thirdparty.home_of(rt.config) / "third_party" / "quickbms" / "scripts"
    tools, scripts, failed = [], {}, {}
    available = {i["id"] for i in rt.dependency_report() if i["available"]}
    for dep in entry.get("tools", []):
        if dep in available:
            continue
        try:
            tools.append(install(rt, dep, sink, cancel)["installed"])
        except ViwoError as exc:
            failed[dep] = exc.message
    for item in entry.get("scripts", []):
        try:
            scripts[item["name"]] = _install_script(item, scripts_dir, say, cancel)
        except ViwoError as exc:
            failed[item["name"]] = exc.message
    if say:
        say(f"Index {slug} ({version}): {len(tools)} tool(s), {len(scripts)} script(s)")
    return {
        "slug": slug,
        "gameVersion": version,
        "plugins": list(entry.get("plugins", [])),
        "options": dict(entry.get("options", {})),
        "tools": tools,
        "scripts": scripts,
        "failed": failed,
        "notes": str(entry.get("notes", "")),
    }


def _release_assets(major: int, fetch) -> tuple[str, dict]:
    """Tag and {asset name: url} of the newest indexes release in the v<major>.* line."""
    from .diag import API, INDEXES_REPO

    releases = fetch(API.format(repo=INDEXES_REPO) + "?per_page=50") or []
    line = [r for r in releases if re.fullmatch(rf"v{major}\.\d+(\.\d+)?", str(r.get("tag_name")))]
    if not line:
        raise ViwoError("not_found", f"no indexes release for the v{major}.x line yet")
    tag = str(line[0]["tag_name"])
    assets = {a["name"]: a["browser_download_url"] for a in line[0].get("assets", [])}
    if f"indexes-{tag}.zip" not in assets or "SHA256SUMS.txt" not in assets:
        raise ViwoError("not_found", f"release {tag} lacks indexes-{tag}.zip or SHA256SUMS.txt")
    return tag, assets


def _swap(home: Path, fresh: Path) -> Path:
    """Replace <home>/indexes with `fresh` (old one kept until the new one is in place)."""
    target, old = home / "indexes", home / "indexes.old"
    if (target / ".git").exists():
        raise ViwoError("refused", "indexes/ is a git checkout: use git submodule update instead")
    if old.exists():
        shutil.rmtree(old)
    if target.exists():
        os.replace(target, old)
    shutil.move(str(fresh), str(target))
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)
    return target


def update_indexes(home: Path, major: int, sink=None, cancel=None, fetch=None) -> dict:
    """Latest vidya_wormhole_indexes release of the v<major>.* line into <home>/indexes."""
    from .diag import github_json

    say = teller(sink, "indexes")
    tag, assets = _release_assets(major, fetch or github_json)
    name = f"indexes-{tag}.zip"
    home.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".indexes-", dir=home) as tmp:
        sums = Path(tmp) / "SHA256SUMS.txt"
        thirdparty._download(assets["SHA256SUMS.txt"], sums, 0, None, cancel)
        pairs = [line.split() for line in sums.read_text().splitlines()]
        want = {n.lstrip("*"): h for h, n in (p for p in pairs if len(p) == 2)}.get(name, "")
        file = Path(tmp) / name
        if not want or thirdparty._download(assets[name], file, 0, say, cancel) != want:
            raise ViwoError("refused", f"{name}: checksum mismatch, indexes not updated")
        fresh = Path(tmp) / "new"
        thirdparty._unzip(file, fresh)
        root = fresh if (fresh / "games").is_dir() else next(fresh.glob("*/games"), fresh).parent
        (root / "VERSION").write_text(tag + "\n", encoding="utf-8")
        where = _swap(home, root)
    if say:
        say(f"Indexes {tag} installed into {where}")
    return {"tag": tag, "where": str(where)}
