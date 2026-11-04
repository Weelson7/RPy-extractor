"""The dynamic arm's commands (doc 11, 16.2b D1-D3): `viwo capture`, `viwo dump`, `viwo trace`,
`viwo agent`, `viwo record`."""

from __future__ import annotations

import sys

from viwo.contracts.errors import Envelope, ViwoError

FIELDS = ("pid", "name", "seconds", "game", "exe", "copy", "timeout")


def runtime(rt, args, printer) -> Envelope:
    """dump, trace, agent, record: the options each command has fill one RuntimeRequest."""
    from viwo.core.capture.runtime import RuntimeRequest, run

    given = {f: getattr(args, f) for f in FIELDS if getattr(args, f, None) is not None}
    if getattr(args, "functions", None) is not None:  # a blank list is refused by the core
        given["functions"] = tuple(f.strip() for f in args.functions.split(",") if f.strip())
    req = RuntimeRequest(args.workspace, **given)
    return Envelope.success(run(rt, args.command, req, printer))


def capture(rt, args) -> Envelope:
    """viwo capture: the warnings are printed before anything launches (never refusals)."""
    from viwo.core.capture import CaptureRequest, capture, warnings

    note = (
        None
        if getattr(args, "quiet", False)
        else (lambda e: print(e.legacy_line(), file=sys.stderr))
    )
    if not args.game.is_dir():
        raise ViwoError("not_found", f"game folder not found: {args.game}")
    if note:
        for warning in warnings(rt, args.game):
            print(f"[CAPTURE:WARN] {warning}", file=sys.stderr)
    req = CaptureRequest(args.game, args.exe, args.workspace, args.confirm, args.auto)
    return Envelope.success(capture(rt, req, note))
