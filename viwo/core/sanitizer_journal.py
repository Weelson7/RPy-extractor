"""The sanitizer's journal and its undo (doc 5.2): one file per plan under .sanitizer/journal/.

An entry is a move, `[now, before]` (trash, rename, renumber, the original a `replace` trashed),
or a file the sanitizer made, `{"made": path, "sha256": digest}` (an open-format copy, a
transcode). Undo follows the journal in reverse: a move goes back, a made file is removed only
while it is still what was made (an edited copy stays, named). What cannot be undone stays in
the journal, so a later undo can finish.
"""

import json
import re
import shutil
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

from . import provenance
from .pipeline.collect import sha256
from .pipeline.guard import guarded
from .steps import Step
from .workspace import write_atomic

JOURNAL = ".sanitizer/journal"
PLAN_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


def plan_id_of(value) -> str:
    if not PLAN_ID.match(str(value)):
        raise ViwoError("invalid_request", f"not a sanitizer plan id: {value!r}")
    return str(value)


def ws_file(workspace: Path, rel) -> Path | None:
    """A path read back from a plan or journal, only if it stays inside the workspace."""
    return ws.member_path(workspace, str(rel))


def move(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = ws.next_free(dest)
    shutil.move(str(src), str(target))
    return target


def record(workspace: Path, plan_id: str, journal: list) -> None:
    folder = workspace / JOURNAL
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{plan_id}.json"  # several applies of one plan add up
    earlier = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    write_atomic(path, json.dumps(earlier + journal))
    moves = [entry for entry in journal if isinstance(entry, list)]
    provenance.rewrite(workspace, {before: now for now, before in moves})


def _undo_one(workspace: Path, entry, back: dict, gone: set) -> bool:
    """One journal entry undone (True), or left as it is (False)."""
    if isinstance(entry, dict):  # a file the sanitizer made: removed while it is unchanged
        made = ws_file(workspace, entry.get("made", ""))
        if made is None or not made.is_file() or sha256(made) != entry.get("sha256"):
            return False
        made.unlink()
        gone.add(entry["made"])
        return True
    now, before = entry
    src, dest = ws_file(workspace, now), ws_file(workspace, before)
    if src is None or dest is None or not src.is_file():
        return False
    back[now] = move(src, dest).relative_to(workspace).as_posix()
    return True


def undo(workspace: Path, token: str, sink=None, cancel=None) -> dict:
    """Move every journaled file back and remove every file made; what cannot go back (or a
    cancel did not reach) stays in the journal and is named, so a later undo can finish."""
    workspace = guarded(None, workspace)
    path = workspace / JOURNAL / f"{plan_id_of(token)}.json"
    if not path.is_file():
        raise ViwoError("not_found", f"nothing to undo for {token}")
    entries = json.loads(path.read_text(encoding="utf-8"))
    left, back, gone = list(entries), {}, set()
    step = Step(sink, "undo", "Undoing actions:", len(entries))
    try:
        for entry in reversed(entries):
            step.tick(cancel)
            if _undo_one(workspace, entry, back, gone):
                left.remove(entry)
    finally:
        provenance.rewrite(workspace, back)
        provenance.forget(workspace, gone)
        if left:
            write_atomic(path, json.dumps(left))
        else:
            path.unlink()
    if entries:
        step.done()
    named = [e["made"] if isinstance(e, dict) else e[0] for e in left]
    return {"restored": len(back), "removed": len(gone), "notRestored": named}
