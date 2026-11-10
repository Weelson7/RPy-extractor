"""`viwo` command line (doc 12.4)."""

import argparse
import contextlib
import json
import os
import sys

from viwo import cli_args, cli_arms, cli_format
from viwo.cli_boot import boot_for_cli, boot_from, global_flags
from viwo.cli_check import slots_check, unpack_forced
from viwo.cli_extra import (
    TOOLS,
    add_plugin_commands,
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
from viwo.core.wiring.memory import guard

EXIT = {"invalid_request": 2, "needs_decision": 2, "refused": 3, "cancelled": 130}


def _parser(rt=None) -> argparse.ArgumentParser:
    """Core subcommands, then the add-ons of the loaded plugins when a runtime is given."""
    ap = argparse.ArgumentParser(
        prog="viwo",
        description="ViWo // Vidya Wormhole: game reverse engineering, local only.",
        epilog=cli_args.EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    global_flags(ap)
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
    cli_arms.group_commands(ap, sub)
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
    if args.verbose:
        print(f"[CLI] ini: {rt.config.source}", file=sys.stderr)
        for slot_id, b in sorted(rt.bindings.items()):
            print(f"[CLI] {slot_id}: {b.main or '-'} / {b.spare or '-'}", file=sys.stderr)


def _run(args, rt=None) -> Envelope:
    rt = rt or boot_from(args)
    _verbose_header(rt, args)
    plugin_command = getattr(args, "plugin_command", None)
    if plugin_command is not None:  # an add-on, possibly overriding a core command
        return run_plugin_command(rt, plugin_command, args)
    if args.command in ("info", "slots", "detect"):
        return _query(rt, args)
    if args.command in TOOLS:
        return workspace_command(rt, args)
    sink = event_printer(args)
    if args.command == "unpack":
        from viwo.core.context import require

        require(rt, "extraction", "extraction")
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


@contextlib.contextmanager
def _only_the_answer(json_mode: bool):
    """`--json` promises one JSON document on stdout. A native library (UnityPy's layout
    generator) or a child tool may print straight to the process's stdout, under Python: while
    the command runs, that stream is pointed at stderr, and restored for the answer."""
    try:
        fd = sys.stdout.fileno() if json_mode else -1
    except (AttributeError, OSError, ValueError):  # captured in memory (tests): nothing under it
        fd = -1
    if fd < 0:
        yield
        return
    sys.stdout.flush()
    saved = os.dup(fd)
    os.dup2(sys.stderr.fileno(), fd)
    try:
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, fd)
        os.close(saved)


def _ceiling(rt, argv: list[str]) -> None:
    """The memory ceiling of this process (doc 9.2); said when it does not hold, or on request."""
    said, holds = guard(rt) if rt is not None else ("", True)
    if not holds or (said and "--verbose" in argv):  # never silent when unprotected
        print(f"[CLI] {said}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    arm, argv = cli_arms.split_arm(list(sys.argv[1:] if argv is None else argv))
    rt = boot_for_cli(argv) if argv else None  # add-ons need the runtime; bare `viwo` stays fast
    _ceiling(rt, argv)
    parser = _parser(rt)
    if arm and cli_arms.first_word(argv) < 0:  # `viwo static`: that arm's commands
        print(cli_arms.listing(parser.viwo_helps, (arm,)))
        return 0
    args = parser.parse_args(argv)
    if args.command is None:
        print(cli_format.WELCOME)
        return 0
    if args.command == "serve":
        from viwo.api.server import serve

        return serve(args.ini, args.host, args.port, not args.no_browser)
    try:
        with _only_the_answer(args.json):
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
        for warning in envelope.warnings or ():  # never silent: the text mode says them too
            print(f"viwo: warning: {warning}", file=sys.stderr)
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
