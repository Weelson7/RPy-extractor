"""`viwo` command line (doc 12.4)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from viwo import cli_format
from viwo.cli_extra import replay_request, unpack_one, workspace_command
from viwo.contracts.errors import Envelope, ViwoError
from viwo.contracts.pipeline import (
    CarveMode,
    ExtractionMode,
    ExtractionRequest,
    MixedPolicy,
    OnExisting,
)
from viwo.core.capture.policy import CONFIRMATION
from viwo.core.jobs import JobRunner
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import detect_all, extract
from viwo.core.wiring.boot import boot

EXIT = {"invalid_request": 2, "needs_decision": 2, "refused": 3, "cancelled": 130}


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="viwo", description="Vidya Wormhole")
    ap.add_argument("--ini", type=Path, help="startup ini (default: startup.ini)")
    ap.add_argument("--os", dest="os_id", help="auto | linux | windows")
    ap.add_argument("--json", action="store_true", help="print a JSON envelope")
    common = argparse.ArgumentParser(add_help=False)  # --json also after the command
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="command", required=True)

    def command(name: str, text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], help=text)

    command("info", "OS layer, plugins, slot bindings, problems")
    command("slots", "slot bindings and dependency status")
    command("detect", "engine detection").add_argument("game", type=Path)
    _extract_args(command("extract", "extract a game folder into a workspace"))
    rp = command("replay", "re-run the extraction stored in a run record")
    rp.add_argument("record", type=Path)
    rp.add_argument("--workspace", type=Path, required=True)
    rp.add_argument("--on-existing", choices=["new", "replace", "cancel"], default="ask")
    rp.add_argument("--option", action="append", default=[], help="secret: plugin.key=value")
    up = command("unpack", "unpack one archive (nested archives too)")
    up.add_argument("archive", type=Path)
    up.add_argument("--out", type=Path, required=True)
    up.add_argument("--option", action="append", default=[], help="plugin.key=value")
    _tool_commands(command)
    sv = command("serve", "start the web UI (host/port from [server] in the ini)")
    sv.add_argument("--host", help="override [server] host")
    sv.add_argument("--port", type=int, help="override [server] port")
    return ap


def _tool_commands(command) -> None:
    """survey, repack, capture, sanitize."""
    su = command("survey", "read-only coverage report for a game or a whole library")
    su.add_argument("folder", type=Path)
    su.add_argument("--deep", action="store_true", help="also run the carver on unknown blobs")
    rk = command("repack", "build a patched copy of the game with the files you edited")
    rk.add_argument("workspace", type=Path)
    rk.add_argument("--out", type=Path, help="target folder for the patched copy")
    rk.add_argument("--plan", action="store_true", help="only show what would be written")
    cp = command("capture", "runtime capture with RenderDoc (pilot; policy-checked)")
    cp.add_argument("game", type=Path)
    cp.add_argument("--exe", type=Path, required=True, help="the game executable to launch")
    cp.add_argument("--workspace", type=Path, required=True)
    cp.add_argument("--confirm", action="store_true", help=f"I confirm: {CONFIRMATION}")
    sz = command("sanitize", "find empty, junk, duplicate, mislabeled or broken files")
    sz.add_argument("workspace", type=Path)
    sz.add_argument("--apply", action="store_true", help="apply every safe action of the plan")
    sz.add_argument("--undo", metavar="TOKEN", help="undo an earlier --apply")


def _extract_args(ex: argparse.ArgumentParser) -> None:
    ex.add_argument("game", type=Path)
    ex.add_argument("--workspace", type=Path, required=True)
    ex.add_argument("--plugin", help="force one plugin")
    ex.add_argument("--mixed", help="comma-separated plugins for mixed mode")
    ex.add_argument("--policy", choices=[p.value for p in MixedPolicy], default="selected")
    ex.add_argument("--exts", help="comma-separated extensions to keep, e.g. .png,.ogg")
    ex.add_argument("--on-existing", choices=["new", "replace", "cancel"], default="ask")
    ex.add_argument("--option", action="append", default=[], help="plugin.key=value")
    ex.add_argument(
        "--carve",
        choices=[c.value for c in CarveMode],
        default="unknown",
        help="find embedded files in blobs: unrecognized files (default), all files, or off",
    )


def _options(items: list[str]) -> dict[str, dict[str, str]]:
    options: dict[str, dict[str, str]] = {}
    for item in items:
        owner_key, _, value = item.partition("=")
        owner, _, key = owner_key.partition(".")
        options.setdefault(owner, {})[key] = value
    return options


def _request(args) -> ExtractionRequest:
    options = _options(args.option)
    mode, plugins = ExtractionMode.AUTO, ()
    if args.plugin:
        mode, plugins = ExtractionMode.SINGLE, (args.plugin,)
    elif args.mixed:
        mode, plugins = ExtractionMode.MIXED, tuple(p.strip() for p in args.mixed.split(","))
    exts = frozenset(e.strip().lower() for e in args.exts.split(",")) if args.exts else None
    return ExtractionRequest(
        str(args.game),
        str(args.workspace),
        exts,
        mode,
        plugins,
        MixedPolicy(args.policy),
        plugin_options=options,
        on_existing=OnExisting(args.on_existing),
        carve=CarveMode(args.carve),
    )


def _run(args) -> Envelope:
    rt = boot(args.ini, args.os_id)
    if args.command == "info":
        return Envelope.success(rt.info(), rt.problems)
    if args.command == "slots":
        return Envelope.success(
            {"bindings": rt.info()["slots"], "dependencies": rt.dependency_report()}, rt.problems
        )
    if args.command == "detect":
        found = detect_all(rt, FolderProbe(args.game))
        return Envelope.success({k: v.to_legacy_dict() for k, v in found.items()})
    if args.command in ("repack", "sanitize", "survey", "capture"):
        return workspace_command(rt, args)
    sink = None if args.json else (lambda e: print(e.legacy_line(), file=sys.stderr))
    if args.command == "unpack":
        return Envelope.success(unpack_one(rt, args.archive, args.out, _options(args.option), sink))
    if args.command == "replay":
        request = replay_request(
            args.record, args.workspace, OnExisting(args.on_existing), _options(args.option)
        )
    else:
        request = _request(args)
    job = JobRunner(sink).submit(
        "extract", lambda jid, s, c: extract(rt, request, jid, s, c), background=False
    )
    if job.error:
        raise ViwoError(**{k: job.error[k] for k in ("code", "message", "owner", "hint")})
    return Envelope.success(job.result.to_legacy_dict(), list(job.result.warnings))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "serve":
        from viwo.api.server import serve

        return serve(args.ini, args.host, args.port)
    try:
        envelope = _run(args)
    except ViwoError as exc:
        envelope = Envelope.failure(exc)
    if args.json:
        print(json.dumps(envelope.to_dict(), indent=2, default=str))
    elif not envelope.ok:
        print(cli_format.error(envelope.error), file=sys.stderr)
    else:
        print(cli_format.FORMATTERS[args.command](envelope.data))
    return 0 if envelope.ok else EXIT.get(envelope.error["code"], 1)


if __name__ == "__main__":
    sys.exit(main())
