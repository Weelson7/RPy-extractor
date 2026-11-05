"""Workbooks (doc 19.1): guided how-tos for a child tool's own interface. Teaching text, never
automation. Shipped in viwo/data/workbooks/, the user's own in <data>/workbooks/ (one there with a
shipped id replaces it). A file that cannot be used is named in the problems, never skipped
silently; steps written for another version than the pinned tool are marked stale."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import thirdparty

SHIPPED = Path(__file__).resolve().parent.parent / "data" / "workbooks"
OPENERS = ("handoff", "attach")  # slot families whose tool a workbook may open (doc 8.3a)
_ID = re.compile(r"[a-z0-9-]+")
_TEXT = ("title", "tool", "written_for", "summary")


def user_dir(rt) -> Path:
    """`viwo-data/workbooks/`, beside the temp folder (like the capture confirmations)."""
    return rt.temp_root.parent / "workbooks"


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _step(raw) -> dict | None:
    if not isinstance(raw, dict) or not (_text(raw.get("title")) and _text(raw.get("text"))):
        return None
    keys, expect = raw.get("keys", []), raw.get("expect", "")
    if not isinstance(keys, list) or not all(_text(k) for k in keys) or not isinstance(expect, str):
        return None
    return {"title": raw["title"], "text": raw["text"], "keys": keys, "expect": expect}


def parse(raw, slots: dict) -> dict | str:
    """The workbook in a file's JSON, or why it cannot be used."""
    if not isinstance(raw, dict):
        return "not a JSON object"
    if not isinstance(raw.get("id"), str) or not _ID.fullmatch(raw["id"]):
        return "the id must be lowercase letters, digits and dashes"
    missing = [key for key in _TEXT if not _text(raw.get(key))]
    if missing:
        return f"missing {', '.join(missing)}"
    opens = raw.get("opens", "")
    if opens and (
        not isinstance(opens, str) or getattr(slots.get(opens), "family", "") not in OPENERS
    ):
        return f"opens names no handoff or attach slot: {opens!r}"
    steps = raw.get("steps")
    if not isinstance(steps, list) or not steps:
        return "no steps"
    parsed = [_step(s) for s in steps]
    if None in parsed:
        return f"step {parsed.index(None) + 1}: a title and a text, keys a list, expect a text"
    head = {"id": raw["id"], "title": raw["title"], "tool": raw["tool"]}
    return {**head, "writtenFor": raw["written_for"], "opens": opens, "summary": raw["summary"],
            "steps": parsed}  # fmt: skip


def _read(folder: Path, source: str, slots: dict, problems: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else ():
        try:
            book = parse(json.loads(path.read_text(encoding="utf-8")), slots)
        except (OSError, ValueError) as exc:
            book = f"unreadable ({exc})"
        if isinstance(book, dict) and book["id"] in found:
            book = f"the id {book['id']!r} is used twice"
        if isinstance(book, str):
            problems.append(f"workbook {path} skipped: {book}")
            continue
        found[book["id"]] = {**book, "source": source}
    return found


def load(rt) -> tuple[list[dict], list[str]]:
    """(workbooks by tool and title, problems): shipped first, the user's own over them."""
    problems: list[str] = []
    books = _read(SHIPPED, "viwo", rt.slots, problems)
    books.update(_read(user_dir(rt), "yours", rt.slots, problems))
    tools = thirdparty.manifest()["tools"]
    out = []
    for book in sorted(books.values(), key=lambda b: (b["tool"], b["title"])):
        entry = tools.get(book["tool"])  # a dict per pin; any other name is an unpinned tool
        pinned = str(entry.get("version", "")) if isinstance(entry, dict) else ""
        out.append(
            {**book, "pinned": pinned, "stale": bool(pinned) and pinned != book["writtenFor"]}
        )
    return out, problems
