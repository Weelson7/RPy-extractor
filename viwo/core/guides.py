"""Guide files (doc 19): workbooks and runbooks are JSON files, shipped in viwo/data/<kind>/ and
the user's own in <data>/<kind>/ (beside the temp folder; one there with a shipped id replaces it
and is marked `yours`). A file that cannot be used is named in the problems, never skipped
silently. Saving and deleting touch only the user's folder."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from viwo.contracts.errors import ViwoError
from viwo.contracts.workspace import inside, safe_member

from .workspace import write_atomic

DATA = Path(__file__).resolve().parent.parent / "data"
ID = re.compile(r"[a-z0-9-]+")
Parse = Callable[[object], "dict | str"]  # a file's JSON -> the guide, or why it cannot be used


def text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def user_dir(rt, kind: str) -> Path:
    """`viwo-data/<kind>/`, beside the temp folder (like the capture confirmations)."""
    return rt.temp_root.parent / kind


def read(folder: Path, source: str, parse: Parse, problems: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else ():
        try:
            guide = parse(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:  # one bad file never hides the rest
            guide = f"unreadable ({exc})"
        if isinstance(guide, dict) and guide["id"] in found:
            guide = f"the id {guide['id']!r} is used twice"
        if isinstance(guide, str):
            problems.append(f"{folder.name[:-1]} {path} skipped: {guide}")
            continue
        found[guide["id"]] = {**guide, "source": source}
    return found


def load(rt, kind: str, parse: Parse) -> tuple[list[dict], list[str]]:
    """(guides, problems): the shipped ones, the user's own over them."""
    problems: list[str] = []
    guides = read(DATA / kind, "viwo", parse, problems)
    guides.update(read(user_dir(rt, kind), "yours", parse, problems))
    return list(guides.values()), problems


def _holder(folder: Path, guide_id: str) -> Path | None:
    """The user's file that holds this id (the first by name: the one `read` keeps), whatever
    the file is called."""
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else ():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(raw, dict) and raw.get("id") == guide_id and inside(folder, path):
            return path
    return None


def _file(rt, kind: str, guide_id: str) -> tuple[Path, Path]:
    """(the user's folder, the file holding the id, else <id>.json); an id that could leave the
    folder is refused."""
    folder = user_dir(rt, kind)
    name = safe_member(f"{guide_id}.json") if ID.fullmatch(str(guide_id)) else None
    if name is None or not inside(folder, folder / name):
        raise ViwoError("invalid_request", f"not a {kind[:-1]} id: {guide_id!r}")
    return folder, _holder(folder, guide_id) or folder / name


def save(rt, kind: str, raw, parse: Parse) -> Path:
    """Validate, then write the user's file for that id (a shipped id: the tweaked copy)."""
    guide = parse(raw)
    if isinstance(guide, str):
        raise ViwoError("invalid_request", f"{kind[:-1]} not saved: {guide}")
    folder, path = _file(rt, kind, guide["id"])
    folder.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(raw, indent=1, ensure_ascii=False) + "\n")
    return path


def delete(rt, kind: str, guide_id: str) -> Path:
    """Remove the user's own file for that id; a shipped guide has none and stays."""
    _, path = _file(rt, kind, guide_id)
    if not path.is_file():
        raise ViwoError(
            "not_found",
            f"no saved {kind[:-1]} {guide_id!r} in {path.parent}",
            hint="a shipped one cannot be deleted; save a tweaked copy over it instead",
        )
    path.unlink()
    return path
