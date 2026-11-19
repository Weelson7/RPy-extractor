"""Main -> spare failover for one slot call, and the `supplement` policy (doc 8.2)."""

import json
import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Callable

from viwo.contracts import workspace as ws
from viwo.contracts.slots import Backend, SlotBinding
from viwo.contracts.types import Outcome, OutcomeKind

RECORDS = (ws.NAMES_FILE, ws.EXPORT_MAP)  # rel path -> where it came from: merged, not moved


def fresh(folder: Path) -> None:
    """An empty `folder`: whatever an earlier attempt wrote there is gone."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)


def run_with_failover(
    binding: SlotBinding,
    backends: dict[str, Backend],
    call: Callable[[Backend], Outcome],
    *,
    into: Path | None,
    cancel,
) -> tuple[Outcome, str]:
    """Try main, then spare when the outcome is retryable. Returns (outcome, backend id).

    `into` is the folder the call writes (None only for a call that writes nothing, a probe):
    every attempt starts with it empty, so a spare never writes beside the truncated files
    and the export map a failed main left, and nothing of a failed attempt is collected.
    `cancel` (a token or None): a cancelled run never starts the spare (the main failed
    because it was stopped). Both are required: no caller can forget them."""
    if not binding.bound:
        reasons = "; ".join(binding.reasons) or "no backend available"
        return Outcome(OutcomeKind.UNAVAILABLE, error=reasons), ""
    last = Outcome(OutcomeKind.FAILED, error="not attempted")
    used, failed = "", ""
    for backend_id in (binding.main, binding.spare):
        if not backend_id:
            continue
        if used and cancel is not None and cancel.cancelled:
            break
        if used:
            failed = f"{used} {last.kind.value}: {last.error or 'no reason given'}"
        if into is not None:
            fresh(into)
        used = backend_id
        try:
            last = call(backends[backend_id])
        except Exception as exc:  # a backend bug is a failed outcome, not a crash
            last = Outcome(OutcomeKind.FAILED, error=f"{type(exc).__name__}: {exc}"[:300])
        if last.ok or not last.retryable:
            break
    if failed:  # never silent: the main backend's failure travels with the outcome
        error = f"{last.error} (after {failed})" if not last.ok else last.error
        last = replace(last, error=error, fallback=f"{failed}; used {used}")
    stopped = cancel is not None and cancel.cancelled
    if last.ok and not failed and binding.policy == "supplement" and binding.spare and not stopped:
        last = supplement(binding, backends[binding.spare], call, into, last)
    return last, used


def supplement(binding: SlotBinding, spare: Backend, call, into: Path | None, first: Outcome):
    """`supplement` (doc 8.2): after the main succeeded, the spare runs too, into the same
    folder emptied (the main's output waits beside it), and every file it wrote that the main
    did not, by relative path, joins the main's output with its entries in the names record
    and the export map. What it added, or why it failed, is in the outcome's notes."""
    if into is None:
        return first
    kept = into.with_name(f"{into.name}.viwo-main")
    try:
        shutil.rmtree(kept, ignore_errors=True)
        os.replace(into, kept)
    except OSError as exc:  # a handle the main left open: the main's output stays as it is
        return replace(first, notes=(*first.notes, f"supplement {spare.backend_id} not run: {exc}"))
    try:
        fresh(into)
        try:
            more = call(spare)
        except Exception as exc:  # a backend bug is a failed outcome, not a crash
            more = Outcome(OutcomeKind.FAILED, error=f"{type(exc).__name__}: {exc}"[:300])
        added = _merge(into, kept) if more.ok else 0
    finally:
        shutil.rmtree(into, ignore_errors=True)
        os.replace(kept, into)
    who = f"supplement {spare.backend_id}"
    if not more.ok:
        notes = (f"{who} {more.kind.value}: {more.error or 'no reason given'}",)
    else:  # nothing added is no event: the main wrote it all
        notes = (f"{who} added {added} file(s) {binding.main} did not write",) if added else ()
    notes += more.notes if added else ()  # the spare's own notes, when its files are kept
    return replace(first, files=first.files + added, notes=(*first.notes, *notes))


def _merge(extra: Path, kept: Path) -> int:
    """Move each file under `extra` that `kept` lacks into `kept` (never through a link, every
    name through `member_path`); the records' entries of the moved files follow them."""
    added: set[str] = set()
    for dirpath, _, names in ws.walk(extra):
        for name in names:
            src = Path(dirpath) / name
            rel = src.relative_to(extra).as_posix()
            target = ws.member_path(kept, rel)
            if name in ws.OWN_FILES or src.is_symlink() or target is None or target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(target))
            added.add(rel)
    for record in RECORDS:
        theirs = _record(extra / record)
        mine = {k: v for k, v in theirs.items() if k in added}
        if mine:
            text = json.dumps({**_record(kept / record), **mine}, ensure_ascii=False, indent=0)
            (kept / record).write_text(text, encoding="utf-8")
    return len(added)


def _record(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
