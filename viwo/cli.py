"""`viwo` command line (doc 12.4)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from viwo import cli_args, cli_format
from viwo.cli_check import slots_check, unpack_forced
from viwo.cli_extra import (
    add_plugin_commands,
    boot_for_cli,
    event_printer,
    replay_request,
    run_plugin_command,
    unpack_one,
    workspace_command,
)
from viwo.contracts.errors import Envelope, ViwoError
from viwo.contracts.pipeline import OnExisting
from viwo.core.jobs import JobRunner
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import detect_all, extract
from viwo.core.wiring.boot import boot

EXIT = {"invalid_request": 2, "needs_decision": 2, "refused": 3, "cancelled": 130}
TOOL_COMMANDS = (
    "repack",
    "sanitize",
    "survey",
    "capture",
    "analyze",
    "diff",
    "patch",
    "mod",
    "config",
    "install",
    "diag",
    "indexes",
)


def _parser(rt=None) -> argparse.ArgumentParser:
    """Core subcommands, then the add-ons of the loaded plugins when a runtime is given."""
    ap = argparse.ArgumentParser(
        prog="viwo",
        description="ViWo // Vidya Wormhole: game reverse engineering, local only.",
        epilog=cli_args.EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--ini", type=Path, help="startup ini (default: startup.ini)")
    ap.add_argument("--os", dest="os_id", help="auto | linux | windows")
    ap.add_argument(
        "--profile",
        help="renpy | unity | unreal | godot | custom | mixed: that distro's plugin set",
    )
    ap.add_argument("--json", action="store_true", help="print a JSON envelope")
    ap.add_argument("--quiet", action="store_true", help="no progress lines on stderr")
    ap.add_argument("--verbose", action="store_true", help="also print the ini and bindings")
    common = argparse.ArgumentParser(add_help=False)  # the globals also after the command
    for flag in ("--json", "--quiet", "--verbose"):
        common.add_argument(flag, action="store_true", default=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="command")

    def command(name: str, text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], help=text)

    cli_args.core_commands(command)
    sv = command("serve", "start the web UI (host/port from [server] in the ini)")
    sv.add_argument("--host", help="override [server] host")
    sv.add_argument("--port", type=int, help="override [server] port")
    sv.add_argument("--no-browser", action="store_true", help="do not open the browser")
    if rt is not None:
        add_plugin_commands(sub, common, rt)
    return ap


def _query(rt, args) -> Envelope:
    """info, slots, detect: read-only answers from the runtime."""
    if args.command == "info":
        return Envelope.success(rt.info(), rt.problems)
    if args.command == "slots":
        if args.check:
            return Envelope.success(slots_check(rt), rt.problems)
        from viwo.core.preflight import check

        deps = check(rt, lambda e: None)  # versions: pinned ones are free, others run once
        return Envelope.success({"bindings": rt.info()["slots"], "dependencies": deps}, rt.problems)
    if not args.game.is_dir():
        raise ViwoError("invalid_request", f"game folder not found: {args.game}")
    found = detect_all(rt, FolderProbe(args.game))
    return Envelope.success({k: v.to_legacy_dict() for k, v in found.items()})


def _verbose_header(rt, args) -> None:
    if args.verbose and not args.json:
        print(f"[CLI] ini: {rt.config.source}", file=sys.stderr)
        for slot_id, b in sorted(rt.bindings.items()):
            print(f"[CLI] {slot_id}: {b.main or '-'} / {b.spare or '-'}", file=sys.stderr)


def _run(args, rt=None) -> Envelope:
    rt = rt or boot(args.ini, args.os_id, profile=args.profile)
    _verbose_header(rt, args)
    plugin_command = getattr(args, "plugin_command", None)
    if plugin_command is not None:  # an add-on, possibly overriding a core command
        return run_plugin_command(rt, plugin_command, args)
    if args.command in ("info", "slots", "detect"):
        return _query(rt, args)
    if args.command in TOOL_COMMANDS:
        return workspace_command(rt, args)
    sink = event_printer(args)
    if args.command == "unpack":
        opts = cli_args.options(args.option)
        if args.slot or args.backend:
            choice = (args.slot or "", args.backend or "")
            return Envelope.success(unpack_forced(rt, args.archive, args.out, opts, sink, choice))
        return Envelope.success(unpack_one(rt, args.archive, args.out, opts, sink))
    if args.command == "replay":
        request = replay_request(
            args.record, args.workspace, OnExisting(args.on_existing), cli_args.options(args.option)
        )
    else:
        request = cli_args.request(args)
    job = JobRunner(sink).submit(
        "extract", lambda jid, s, c: extract(rt, request, jid, s, c), background=False
    )
    if job.error:
        raise ViwoError(**{k: job.error[k] for k in ("code", "message", "owner", "hint")})
    return Envelope.success(job.result.to_legacy_dict(), list(job.result.warnings))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rt = boot_for_cli(argv) if argv else None  # add-ons need the runtime; bare `viwo` stays fast
    args = _parser(rt).parse_args(argv)
    if args.command is None:
        print(cli_format.WELCOME)
        return 0
    if args.command == "serve":
        from viwo.api.server import serve

        return serve(args.ini, args.host, args.port, not args.no_browser)
    try:
        envelope = _run(args, rt)
    except ViwoError as exc:
        envelope = Envelope.failure(exc)
    except KeyboardInterrupt:
        envelope = Envelope.failure(ViwoError("cancelled", "stopped by Ctrl+C"))
    except Exception as exc:  # never a traceback for the user
        envelope = Envelope.failure(
            ViwoError(
                "internal",
                f"{type(exc).__name__}: {exc}",
                hint="run `viwo diag` and attach the bundle to a bug report",
            )
        )
    if args.json:
        print(json.dumps(envelope.to_dict(), indent=2, default=str))
    elif not envelope.ok:
        print(cli_format.error(envelope.error), file=sys.stderr)
    else:
        print(_formatter(args)(envelope.data))
    return 0 if envelope.ok else EXIT.get(envelope.error["code"], 1)


def _formatter(args):
    cmd = getattr(args, "plugin_command", None)
    if cmd is not None and cmd.formatter is not None:
        return cmd.formatter
    if args.command == "slots" and getattr(args, "check", False):
        return cli_format.slots_check
    return cli_format.FORMATTERS.get(args.command, cli_format.generic)


if __name__ == "__main__":
    sys.exit(main())
