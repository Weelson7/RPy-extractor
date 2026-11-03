"""The dynamic arm's commands (doc 11, 16.2b D1/D3): `viwo capture`, `viwo dump`, `viwo trace`."""

from __future__ import annotations

import sys

from viwo.contracts.errors import Envelope, ViwoError


def runtime(rt, args) -> Envelope:
    from viwo.core.capture import runtime as tools

    if args.command == "agent":
        from viwo.core.capture.agents import AgentRequest, run_agent

        req = AgentRequest(args.game, args.exe, args.workspace, args.copy, args.timeout)
        done = run_agent(rt, req)
        return Envelope.success(done)
    if args.command == "record":
        from viwo.core.capture.audio import record

        return Envelope.success(record(rt, args.workspace, args.seconds))
    if args.command == "dump":
        return Envelope.success(tools.dump(rt, args.workspace, args.pid, args.name))
    names = [f.strip() for f in args.functions.split(",") if f.strip()]
    return Envelope.success(
        tools.trace(rt, args.workspace, (args.pid, args.name), names, args.seconds)
    )


def capture(rt, args) -> Envelope:
    """viwo capture: the warnings are printed before anything launches (never refusals)."""
    from viwo.core.capture import CaptureRequest, capture, warnings

    note = (
        None
        if args.json or getattr(args, "quiet", False)
        else (lambda e: print(e.legacy_line(), file=sys.stderr))
    )
    if not args.game.is_dir():
        raise ViwoError("not_found", f"game folder not found: {args.game}")
    if note:
        for warning in warnings(rt, args.game):
            print(f"[CAPTURE:WARN] {warning}", file=sys.stderr)
    req = CaptureRequest(args.game, args.exe, args.workspace, args.confirm, args.auto)
    return Envelope.success(capture(rt, req, note))
