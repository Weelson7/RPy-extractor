"""Runbooks (doc 19.2): named, editable sequences of steps: ViWo's own actions (a job kind of
POST /api/jobs with its parameters) and steps the user does, in a child tool when a workbook
says how. The files are core/guides.py's; here are their rules and the `{name}` values a step's
parameters take. The job kinds live in the API layer, so callers pass them in."""

import re
from functools import partial
from pathlib import Path

from viwo.contracts.errors import ViwoError

from . import guides, workbooks, workflows
from .guides import text

KIND = "runbooks"
RESERVED = ("game", "workspace")  # the values every run has
_NAME = re.compile(r"[a-z][a-z0-9_]*")
_FIELD = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def names_in(value) -> set[str]:
    """Every `{name}` in the strings of a parameter tree."""
    if isinstance(value, dict):
        return set().union(*(names_in(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(names_in(v) for v in value))
    return set(_FIELD.findall(value)) if isinstance(value, str) else set()


def _input(raw) -> dict | str:
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        return "an input needs a name"
    name, default, secret = raw["name"], raw.get("default", ""), raw.get("secret", False)
    if not _NAME.fullmatch(name) or name in RESERVED or not isinstance(default, str):
        return f"input {name!r}: lowercase name (not game or workspace), a text default"
    if not isinstance(secret, bool) or (secret and default):
        return f"input {name!r}: secret is true or false, and a secret has no default"
    label = raw["label"] if text(raw.get("label")) else name
    return {"name": name, "label": label, "default": default, "secret": secret}


def _step(raw, kinds, books: set[str], names: set[str]) -> dict | str:
    if not isinstance(raw, dict) or not text(raw.get("title")):
        return "a step needs a title"
    if "do" in raw:
        params = raw.get("with", {})
        if not isinstance(raw["do"], str) or raw["do"] not in kinds:
            return f"unknown action {raw['do']!r} (one of {', '.join(sorted(kinds))})"
        if not isinstance(params, dict):
            return "with must be an object"
        unknown = {n for n in names_in(params) - names if not workflows.CARRIED.fullmatch(n)}
        if unknown:
            return f"no value named {', '.join(sorted(unknown))}"
        if "expect" in raw and not workflows.valid_expect(raw["expect"]):
            return "expect: a recording's {digest, facts} (doc 19.3)"
        step = {"title": raw["title"], "do": raw["do"], "with": params}
        return {**step, "expect": raw["expect"]} if "expect" in raw else step
    book = raw.get("workbook", "")
    if not text(raw.get("text")) or not isinstance(book, str) or (book and book not in books):
        return "a step you do needs a text (and a workbook that exists)"
    return {"title": raw["title"], "text": raw["text"], "workbook": book}


def parse(raw, kinds, books: set[str]) -> dict | str:
    """The runbook in a file's JSON (or a saved one), or why it cannot be used."""
    if not isinstance(raw, dict):
        return "not a JSON object"
    if not isinstance(raw.get("id"), str) or not guides.ID.fullmatch(raw["id"]):
        return "the id must be lowercase letters, digits and dashes"
    if not (text(raw.get("title")) and text(raw.get("summary"))):
        return "a title and a summary"
    given = raw.get("inputs", [])
    inputs = [_input(i) for i in given] if isinstance(given, list) else ["inputs: a list"]
    if bad := next((i for i in inputs if isinstance(i, str)), ""):
        return bad
    steps, names = raw.get("steps"), {*RESERVED, *(i["name"] for i in inputs)}
    if not isinstance(steps, list) or not steps:
        return "no steps"
    parsed = [_step(s, kinds, books, names) for s in steps]
    if bad := next(((n, s) for n, s in enumerate(parsed, 1) if isinstance(s, str)), None):
        return f"step {bad[0]}: {bad[1]}"
    head = {"id": raw["id"], "title": raw["title"], "summary": raw["summary"]}
    return {**head, "inputs": inputs, "steps": parsed}


def _parser(rt, kinds):
    return partial(parse, kinds=kinds, books={b["id"] for b in workbooks.load(rt)[0]})


def load(rt, kinds) -> tuple[list[dict], list[str]]:
    """(runbooks by title, problems)."""
    books, problems = guides.load(rt, KIND, _parser(rt, kinds))
    return sorted(books, key=lambda b: b["title"]), problems


def save(rt, kinds, raw) -> Path:
    return guides.save(rt, KIND, raw, _parser(rt, kinds))


def values_for(book: dict, given: dict, game: str, workspace: Path) -> dict[str, str]:
    """The run's values: the game, the active workspace, each input (its default when empty)
    and what earlier steps of this run answered (`step<N>_<key>`, doc 19.3)."""
    mine = {i["name"]: str(given.get(i["name"]) or i["default"]) for i in book["inputs"]}
    carried = {k: str(v) for k, v in given.items() if workflows.CARRIED.fullmatch(str(k))}
    return {**carried, "game": game, "workspace": str(workspace), **mine}


def resolve(value, values: dict[str, str]):
    """The parameter tree with every `{name}` replaced; an empty value is refused, named. A
    string that is one `{name}` alone whose value is "true" or "false" becomes that boolean
    (an input is text, and a flag like `plan` must not read "false" as set)."""
    if isinstance(value, dict):
        return {k: resolve(v, values) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, values) for v in value]
    if not isinstance(value, str):
        return value
    alone = _FIELD.fullmatch(value)
    if alone and values.get(alone.group(1), "").lower() in ("true", "false"):
        return values[alone.group(1)].lower() == "true"

    def one(match: re.Match) -> str:
        if not values.get(match.group(1)):
            raise ViwoError("invalid_request", f"this step needs a value for {match.group(1)}")
        return values[match.group(1)]

    return _FIELD.sub(one, value)
