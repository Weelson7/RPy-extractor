"""Workbooks (doc 19.1): guided how-tos for a child tool's own interface. Teaching text, never
automation. The files (shipped, the user's own, problems named) are core/guides.py's; here are
their rules, and the stale mark for steps written for another version than the pinned tool."""

from functools import partial

from . import guides, thirdparty
from .guides import text

KIND = "workbooks"
SHIPPED = guides.DATA / KIND
OPENERS = ("handoff", "attach")  # slot families whose tool a workbook may open (doc 8.3a)
_TEXT = ("title", "tool", "written_for", "summary")


def user_dir(rt):
    return guides.user_dir(rt, KIND)


def _step(raw) -> dict | None:
    if not isinstance(raw, dict) or not (text(raw.get("title")) and text(raw.get("text"))):
        return None
    keys, expect = raw.get("keys", []), raw.get("expect", "")
    if not isinstance(keys, list) or not all(text(k) for k in keys) or not isinstance(expect, str):
        return None
    return {"title": raw["title"], "text": raw["text"], "keys": keys, "expect": expect}


def parse(raw, slots: dict) -> dict | str:
    """The workbook in a file's JSON, or why it cannot be used."""
    if not isinstance(raw, dict):
        return "not a JSON object"
    if not isinstance(raw.get("id"), str) or not guides.ID.fullmatch(raw["id"]):
        return "the id must be lowercase letters, digits and dashes"
    missing = [key for key in _TEXT if not text(raw.get(key))]
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


def load(rt) -> tuple[list[dict], list[str]]:
    """(workbooks by tool and title, problems); `pinned` and `stale` from tools.json."""
    books, problems = guides.load(rt, KIND, partial(parse, slots=rt.slots))
    tools = thirdparty.manifest()["tools"]
    out = []
    for book in sorted(books, key=lambda b: (b["tool"], b["title"])):
        entry = tools.get(book["tool"])  # a dict per pin; any other name is an unpinned tool
        pinned = str(entry.get("version", "")) if isinstance(entry, dict) else ""
        out.append(
            {**book, "pinned": pinned, "stale": bool(pinned) and pinned != book["writtenFor"]}
        )
    return out, problems
