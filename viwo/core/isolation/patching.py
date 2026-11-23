"""One `patch` action in a session (doc 11.8): the set written live (live.apply_live) through the
located program, with what makes it hold up in a real guest. The view is checked first: a program
that restarted is located again by name (ASLR moved it), one that is gone is said (a program that
refuses to run in a VM ends like this). A whole-guest snapshot can be taken first (`snapshot`), so
`rollback` also undoes what the program derived from the bytes. Pages not in RAM yet are waited
for (`wait` seconds: the set is tried again once a second until they load). Bytes the program
puts back are written again while it is watched (`hold` seconds, each revert counted and said).
A module that other processes map too is said: a patched page of it changes for them as well."""

import json
import time
from pathlib import Path

from viwo.contracts.errors import ViwoError

from .. import patchsets
from . import atomic_write, guest, live

HEADERS = (b"MZ", b"\x7fE")  # the first bytes of a PE and of an ELF image
SNAPSHOT = "pre-patch"


def fresh_view(rt, session, where: Path, log) -> dict | None:
    """The located program, located again when it is no longer where it was."""
    view = guest.load(where)
    if view is None or guest.present(session, view):
        return view
    name = guest.main(view)
    log(f"{name} (pid {view['pid']}) is no longer where it was located (restarted or exited); "
        "locating it again", "warn")  # fmt: skip
    try:
        guest.locate(rt, session, where, name, log)
    except ViwoError as exc:
        guest.drop(where)
        hint = "a program that refuses to run in a VM exits like this (vm_detected)"
        raise ViwoError("not_found", f"{name} is gone from the guest: {exc.message}", hint=hint)
    return guest.load(where)


def _shared(view: dict | None, patch_set: dict, log) -> list[str]:
    files = {Path(str(p.get("file", ""))).name.lower() for p in patch_set["patches"]}
    found = [m for m in (view or {}).get("modules", ()) if m["name"].lower() in files]
    shared = [f"{m['name']} ({m['shared']} other processes)" for m in found if m.get("shared")]
    if shared:
        log(f"Patched modules other processes map too (their pages change as well): "
            f"{', '.join(shared)}", "warn")  # fmt: skip
    return shared


def _until_resident(apply, wait, log) -> dict:
    """`apply()` the set; while its pages are not in RAM, again once a second for `wait` s."""
    end, said = time.monotonic() + max(0.0, float(wait or 0)), False
    while True:
        report = apply()
        waiting = any("not resident" in (r.get("detail") or "") for r in report["results"])
        if report["written"] or not waiting or time.monotonic() >= end:
            if waiting and wait:
                report["waited"] = f"{wait} s, and the pages never loaded"
            return report
        if not said:
            log(f"Some pages are not in guest RAM yet: trying again for up to {wait} s", "info")
            said = True
        time.sleep(1.0)


def _hold(target, entries: list[dict], seconds: float, log) -> int:
    """Watch the edits for `seconds`; write each again whenever its bytes went back."""
    reverts, end = 0, time.monotonic() + seconds
    log(f"Holding {len(entries)} edits for {seconds:g} s", "info")
    while time.monotonic() < end:
        for entry in entries:
            space, new = guest.bound(target, entry), bytes.fromhex(entry["new"])
            now = space.read_mem(int(entry["addr"]), len(new))
            if now and now != new and not atomic_write(space, int(entry["addr"]), new).blocked:
                reverts += 1
                log(f"The program put back {int(entry['addr']):#x}; written again", "warn")
        time.sleep(0.5)
    return reverts


def patch(rt, session, where: Path, opt: dict, log) -> dict:
    exe, patchset = opt.get("exe"), opt.get("patchset")
    if exe is None or patchset is None:
        raise ViwoError("invalid_request", "patch needs the program (--exe) and a --patchset")
    view = fresh_view(rt, session, where, log)
    patch_set = patchsets.load(Path(patchset))
    head: dict = {"shared": _shared(view, patch_set, log)}
    if opt.get("snapshot"):
        name = time.strftime(f"{SNAPSHOT}-%Y%m%d-%H%M%S")  # unique: `rollback --name` it
        made = session.snapshot(name)
        head["snapshot"] = name if made.ok else f"not taken: {made.error}"
        log(f"Snapshot {name}: {'taken' if made.ok else made.error}",
            "info" if made.ok else "warn")  # fmt: skip
    base = int(opt.get("base") or 0) or guest.bases(where) or 0  # --base wins over a located one
    journal, target = where / "journal.jsonl", guest.view(session, where)
    before = len(journal.read_text(encoding="utf-8").splitlines()) if journal.is_file() else 0
    game = Path(exe).parent
    apply = lambda: live.apply_live(rt, target, game, patch_set, base, journal)  # noqa: E731
    report = _until_resident(apply, opt.get("wait"), log)
    hold = float(opt.get("hold") or 0)
    if hold > 0 and report["written"]:
        lines = journal.read_text(encoding="utf-8").splitlines()[before:]
        report["reverts"] = _hold(target, [json.loads(line) for line in lines], hold, log)
    if view and report["written"] and str(head.get("snapshot", "")).startswith(SNAPSHOT):
        head.update(_exited(session, view, head["snapshot"], log))
    return {**head, **report}


def _exited(session, view: dict, snapshot: str, log) -> dict:
    """The program is gone once patched (a check that exits): the guest goes back to the
    snapshot taken just before, so the session goes on and nothing is lost but the try."""
    if guest.present(session, view):
        return {}
    back = session.rollback(snapshot)
    log(f"{guest.main(view)} exited after the patch; the guest is back at {snapshot}"
        if back.ok else f"{guest.main(view)} exited after the patch; rollback failed: "
        f"{back.error}", "warn" if back.ok else "error")  # fmt: skip
    return {"exited": True, "rolled_back": snapshot if back.ok else ""}
