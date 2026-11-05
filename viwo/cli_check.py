"""`viwo slots --check` (backend self-tests, doc 12.4 / 14.6), the forced single-archive unpack
behind `viwo unpack --slot/--backend`, and `viwo analyze` (doc 6)."""

import shutil
import sys
import tempfile
from pathlib import Path

from viwo.contracts.errors import Envelope, ViwoError

from .cli_extra import context_factory
from .cli_extra import event_printer as printer


def _check_one(rt, slot_id: str, backend_id: str, role: str) -> dict:
    backend = rt.backends[backend_id]
    probe = backend.self_check
    try:
        ok, reason = probe(rt.os)
    except Exception as exc:  # noqa: BLE001  (a self-test that crashes is a failed test)
        ok, reason = False, f"{type(exc).__name__}: {exc}"
    return {"slot": slot_id, "backend": backend_id, "role": role, "ok": bool(ok), "reason": reason}


def slots_check(rt) -> dict:
    """Run every bound backend's self-check; a failing bound main makes the command fail."""
    checks = []
    for slot_id, binding in sorted(rt.bindings.items()):
        for role, backend_id in (("main", binding.main), ("spare", binding.spare)):
            if backend_id and backend_id in rt.backends:
                checks.append(_check_one(rt, slot_id, backend_id, role))
    failed = [c for c in checks if not c["ok"] and c["role"] == "main"]
    data = {
        "bindings": rt.info()["slots"],
        "checks": checks,
        "failed": [f"{c['slot']} ({c['backend']}): {c['reason']}" for c in failed],
    }
    if failed:
        raise ViwoError(
            "failed",
            f"{len(failed)} bound main backend(s) failed their self-check",
            hint="; ".join(data["failed"][:6]),
        )
    return data


def _backend_for(rt, slot_id: str, choice: str) -> str:
    binding = rt.bindings.get(slot_id)
    if binding is None:
        raise ViwoError("invalid_request", f"unknown slot {slot_id}", hint="see `viwo slots`")
    if choice in ("main", "spare", ""):
        backend_id = getattr(binding, choice or "main")
        if not backend_id:
            raise ViwoError("unavailable", f"{slot_id} has no {choice or 'main'} backend")
        return backend_id
    backend = rt.backends.get(choice)
    if backend is None or rt.slots[slot_id].family not in backend.families:
        raise ViwoError("invalid_request", f"{choice} does not serve {slot_id}")
    return choice


def unpack_forced(rt, archive: Path, out: Path, options: dict, sink, choice) -> dict:
    """One archive through one chosen slot/backend, no nesting (doc 12.4 --slot/--backend)."""
    slot_id, backend_choice = choice
    if not archive.is_file():
        raise ViwoError("invalid_request", f"archive not found: {archive}")
    if out.exists() and any(out.iterdir()):
        raise ViwoError("refused", f"{out} is not empty")
    if not slot_id:  # --backend alone: the first bound slot that backend serves
        slot_id = next(
            (s for s, b in sorted(rt.bindings.items()) if backend_choice in (b.main, b.spare)), ""
        )
        if not slot_id:
            raise ViwoError("invalid_request", f"{backend_choice} is bound to no slot")
    backend_id = _backend_for(rt, slot_id, backend_choice)
    rt.temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=rt.temp_root) as tmp:
        ctx = context_factory(rt, archive.parent, Path(tmp), options, sink)(rt.slots[slot_id].owner)
        dest = Path(tmp) / "unpack"
        dest.mkdir()
        outcome = rt.backends[backend_id].extract(archive, dest, ctx)
        if not outcome.ok:
            raise ViwoError("failed", outcome.error or f"{backend_id} failed")
        shutil.copytree(dest, out, dirs_exist_ok=True)
    return {
        "archive": str(archive),
        "out": str(out),
        "archives": 1,
        "files": outcome.files,
        "byBackend": {backend_id: 1},
        "failures": [],
        "slot": slot_id,
    }


def analyze_command(rt, args) -> Envelope:
    """viwo analyze: --list targets, run one target, or --open it in the GUI tool."""
    from viwo.core.analysis import (
        AnalysisRequest,
        analyze,
        extras_for,
        handoffs_for,
        open_in,
        targets_for,
    )
    from viwo.core.handoff import wait_for

    if not args.game.is_dir():
        raise ViwoError("not_found", f"game folder not found: {args.game}")
    if args.list or not args.target:
        found = targets_for(rt, args.game)
        targets = [
            {**t.to_dict(), "handoffs": handoffs_for(rt, t.kind), "extras": extras_for(rt, t.kind)}
            for t in found
        ]
        return Envelope.success({"targets": targets})
    if args.workspace is None:
        raise ViwoError("invalid_request", "give --workspace <folder>")
    pairs = [s.partition("=") for s in args.set]
    if any(not key or not sep for key, sep, _ in pairs):
        raise ViwoError("invalid_request", "--set takes KEY=VALUE", hint="e.g. --set start=0x1400")
    options = {key: value for key, _, value in pairs}
    options.update({"timeout_s": args.timeout} if args.timeout else {})
    req = AnalysisRequest(args.game, args.workspace, args.target, options, args.slot)
    if args.open is not None:
        opened = open_in(rt, req, args.open)
        if not getattr(args, "quiet", False):
            print(
                f"[ANALYZE] {opened['label']} running (pid {opened['pid']}); close it to return",
                file=sys.stderr,
            )
        wait_for(opened["pid"])  # the tool is ViWo's child: it would die with this process
        return Envelope.success(opened)
    return Envelope.success(analyze(rt, req, printer(args)))


def diff_command(args) -> Envelope:
    """viwo diff OLD NEW: the A3 report beside the newer analysis unless --out says where."""
    from viwo.core.analysis import diff

    report = diff.diff(args.old, args.new)
    out = diff.write(
        report,
        args.out or args.new.parent.parent / "diff" / f"{args.old.name}--{args.new.name}",
    )
    return Envelope.success({"summary": report["summary"], "outputDir": str(out)})
