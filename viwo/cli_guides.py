"""`viwo workbook` and `viwo runbook` (doc 19): the guides for the child tools, and runbooks run
step by step through the same handlers as the web UI (so every action keeps its own checks)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from viwo.contracts.errors import Envelope, ViwoError


def workbook(rt, args) -> Envelope:
    """viwo workbook [ID]: every workbook, or one with its steps (doc 19.1); stale steps and
    unusable files are warnings."""
    from viwo.core.workbooks import load

    books, problems = load(rt)
    shown = [b for b in books if b["id"] == args.id] if args.id else books
    if args.id and not shown:
        raise ViwoError("not_found", f"no workbook {args.id!r}", hint="`viwo workbook` lists them")
    stale = [
        f"{b['id']}: written for {b['tool']} {b['writtenFor']}, the pinned one is {b['pinned']}"
        for b in shown
        if b["stale"]
    ]
    data = {"workbook": shown[0]} if args.id else {"workbooks": books}
    return Envelope.success(data, problems + stale)


def runbook(rt, args) -> Envelope:
    """viwo runbook [ID] [--run --workspace W --set name=value --from N] (doc 19.2)."""
    from viwo.api.handlers_jobs import KINDS
    from viwo.core import runbooks

    books, problems = runbooks.load(rt, KINDS)
    if not args.id:
        return Envelope.success({"runbooks": books}, problems)
    book = next((b for b in books if b["id"] == args.id), None)
    if book is None:
        raise ViwoError("not_found", f"no runbook {args.id!r}", hint="`viwo runbook` lists them")
    if not args.run:
        return Envelope.success({"runbook": book}, problems)
    data, said = _run(rt, book, args)
    return Envelope.success(data, problems + said)


def _values(book: dict, pairs: list[str]) -> tuple[dict[str, str], list[str]]:
    """(values, warnings): a name the runbook does not have is said, never ignored silently."""
    split = [p.partition("=") for p in pairs]
    if any(not key or not sep for key, sep, _ in split):
        raise ViwoError("invalid_request", "--set takes NAME=VALUE", hint="e.g. --set game=D:/Foo")
    known = {"game", *(i["name"] for i in book["inputs"])}
    said = [
        f"--set {key}: {book['id']} has no value of that name ({', '.join(sorted(known))})"
        + ("; the workspace is --workspace" if key == "workspace" else "")
        for key, _, _ in split
        if key not in known
    ]
    return {key: value for key, _, value in split if key in known}, said


def _answer(args, answer: dict) -> dict:
    """What a step's action answered (a plan, a report), shown on stderr and kept."""
    kept = {k: v for k, v in answer.items() if k not in ("success", "jobId", "step")}
    shown = json.dumps(kept, indent=1, default=str)
    _say(args, "  " + (shown if len(shown) < 1500 else shown[:1500] + "\n  ... (all: --json)"))
    return kept


def _where(app, given: Path) -> str:
    """Where to resume: the workspace an extract step switched to, when it did."""
    now = app.workspace.resolve()
    return f" --workspace {now}" if now != given.resolve() else ""


def _say(args, line: str) -> None:
    if not getattr(args, "quiet", False):
        print(line, file=sys.stderr)


def _done_by_you(args, step: dict) -> bool:
    """A step the user does: its text (and workbook); True once confirmed at a terminal."""
    _say(args, f"  {step['text']}")
    if step["workbook"]:
        _say(args, f"  how, step by step: viwo workbook {step['workbook']}")
    if not sys.stdin.isatty():
        return False
    input("  press Enter when it is done (Ctrl+C stops the run) ")
    return True


def _run(rt, book: dict, args) -> tuple[dict, list[str]]:
    """Each step from --from on; a failed action stops the run and says where to resume."""
    from viwo.api.app import App

    steps = book["steps"]
    if args.workspace is None:
        raise ViwoError("invalid_request", "give --workspace <folder>")
    if not 1 <= args.start <= len(steps):
        raise ViwoError(
            "invalid_request", f"--from {args.start}: {book['id']} has steps 1-{len(steps)}"
        )
    (values, said), app, done = _values(book, args.set), App(rt), []
    app.set_workspace(args.workspace.resolve())
    for index in range(args.start - 1, len(steps)):
        _say(args, f"[RUNBOOK] {index + 1}/{len(steps)} {steps[index]['title']}")
        if "do" in steps[index]:
            done.append(_action(app, book, index, values, args))
        elif not _done_by_you(args, steps[index]):
            stop = {"runbook": book["id"], "done": done, "stoppedAt": index + 1}
            return stop, [*said, _paused(app, args, index, len(steps))]
    return {"runbook": book["id"], "done": done, "stoppedAt": None}, said


def _paused(app, args, index: int, total: int) -> str:
    """What a run that stopped at a step you do says (no --from after the last step)."""
    if index + 1 == total:
        return f"step {index + 1} is yours: do it; it is the last step"
    again = f"--from {index + 2}{_where(app, args.workspace)}"
    return f"step {index + 1} is yours: do it, then run again with {again}"


def _action(app, book: dict, index: int, values: dict, args) -> dict:
    """One action step; a failure stops the run with where to resume."""
    from viwo.api.handlers_runbooks import run_step

    try:
        answer = run_step(app, book, index, values)
    except ViwoError as exc:  # refused before the job: an empty value, said with the step
        answer = {"success": False, "error": exc.message, "code": exc.code, "hint": exc.hint}
    if not answer.get("success"):
        message = f"step {index + 1} ({book['steps'][index]['title']}): {answer.get('error')}"
        again = f"then --from {index + 1}{_where(app, args.workspace)}"
        hint = f"{answer['hint']}; {again}" if answer.get("hint") else again
        raise ViwoError(answer.get("code") or "failed", message, hint=hint)
    return {"step": index + 1, "jobId": answer.get("jobId", ""), "answer": _answer(args, answer)}
