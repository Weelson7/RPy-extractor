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
EPILOG = """examples:
  viwo survey D:/Games                 what can be pulled from each game (read-only)
  viwo extract D:/Games/Foo --workspace out/foo
  viwo install --all                   every missing pinned tool into third_party/
  viwo install --game skyrim-se        what an index entry needs (tools, scripts)
  viwo capture D:/Games/Foo --exe Foo.exe --workspace out/foo --confirm

exit codes: 0 ok | 1 failed or not found | 2 bad request or config | 3 refused (folder
containment) | 4 strict preflight failed | 130 cancelled (Ctrl+C). Errors print
"viwo: <code>: <message>" and a hint; `--json` prints the envelope instead."""


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="viwo",
        description="ViWo // Vidya Wormhole: game reverse engineering, local only.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--ini", type=Path, help="startup ini (default: startup.ini)")
    ap.add_argument("--os", dest="os_id", help="auto | linux | windows")
    ap.add_argument("--json", action="store_true", help="print a JSON envelope")
    common = argparse.ArgumentParser(add_help=False)  # --json also after the command
    common.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="print a JSON envelope"
    )
    sub = ap.add_subparsers(dest="command")

    def command(name: str, text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], help=text)

    command("info", "OS layer, plugins, slot bindings, problems")
    command("slots", "slot bindings and dependency status")
    command("detect", "which engine a game folder uses (read-only)").add_argument(
        "game", type=Path, help="the game folder"
    )
    _extract_args(command("extract", "extract a game folder into a workspace"))
    rp = command("replay", "re-run the extraction stored in a run record")
    rp.add_argument("record", type=Path, help="<workspace>/.extraction_metadata/runs/<id>.json")
    rp.add_argument("--workspace", type=Path, required=True, help="folder to extract into")
    rp.add_argument("--on-existing", choices=["new", "replace", "cancel"], default="ask")
    rp.add_argument("--option", action="append", default=[], help="secret: plugin.key=value")
    up = command("unpack", "unpack one archive (nested archives too)")
    up.add_argument("archive", type=Path, help="one archive file (zip, rpa, pck, pak, ...)")
    up.add_argument("--out", type=Path, required=True, help="empty output folder")
    up.add_argument("--option", action="append", default=[], help="plugin.key=value")
    _tool_commands(command)
    sv = command("serve", "start the web UI (host/port from [server] in the ini)")
    sv.add_argument("--host", help="override [server] host")
    sv.add_argument("--port", type=int, help="override [server] port")
    sv.add_argument("--no-browser", action="store_true", help="do not open the browser")
    return ap


def _tool_commands(command) -> None:
    """survey, repack, capture, sanitize, config."""
    cf = command("config", "generate the distro config files, or check config files strictly")
    cf.add_argument("action", choices=["generate", "check"], help="generate distros/ or check")
    cf.add_argument("paths", nargs="*", type=Path, help="check: files; generate: output folder")
    su = command("survey", "read-only coverage report for a game or a whole library")
    su.add_argument("folder", type=Path, help="one game folder, or a folder of games")
    su.add_argument("--deep", action="store_true", help="also run the carver on unknown blobs")
    rk = command("repack", "build a patched copy of the game with the files you edited")
    rk.add_argument("workspace", type=Path, help="the workspace holding your edited files")
    rk.add_argument("--out", type=Path, help="target folder for the patched copy")
    rk.add_argument("--plan", action="store_true", help="only show what would be written")
    cp = command("capture", "runtime GPU capture with RenderDoc (opt-in; see --help)")
    cp.description = (
        "Runs the game under RenderDoc and harvests every capture you take (F12) into the "
        "workspace. Opt-in: add `capture` to [startup] features in the ini and pass --confirm. "
        "Anti-cheat and online titles only produce warnings; you are responsible."
    )
    cp.add_argument("game", type=Path, help="the game folder")
    cp.add_argument("--exe", type=Path, required=True, help="the game executable to launch")
    cp.add_argument("--workspace", type=Path, required=True, help="where captures are gathered")
    cp.add_argument("--confirm", action="store_true", help=f"I confirm: {CONFIRMATION}")
    sz = command("sanitize", "find empty, junk, duplicate, mislabeled or broken files")
    sz.add_argument("workspace", type=Path, help="a ViWo workspace")
    sz.add_argument("--apply", action="store_true", help="apply every safe action of the plan")
    sz.add_argument("--undo", metavar="TOKEN", help="undo an earlier --apply")
    ins = command("install", "install pinned tools into third_party/ (checksums verified)")
    ins.add_argument("ids", nargs="*", help="dependency ids (see `viwo slots`)")
    ins.add_argument("--all", action="store_true", help="everything missing that can be installed")
    ins.add_argument(
        "--game", metavar="SLUG", help="what an index entry needs (indexes/games/<slug>)"
    )
    ins.add_argument(
        "--game-version", default="any", help="index folder under the slug (default: any)"
    )
    dg = command("diag", "zip logs, run records and tool status for a bug report (no secrets)")
    dg.add_argument("--out", type=Path, help="zip path (default: in the logs folder)")
    ix = command("indexes", "per-game indexes: update to the latest release for this version")
    ix.add_argument("action", choices=["update"], help="update: fetch the latest indexes release")


def _extract_args(ex: argparse.ArgumentParser) -> None:
    ex.add_argument("game", type=Path, help="the game folder (opened read-only)")
    ex.add_argument("--workspace", type=Path, required=True, help="folder to extract into")
    ex.add_argument("--plugin", help="force one plugin")
    ex.add_argument("--mixed", help="comma-separated plugins for mixed mode")
    ex.add_argument(
        "--policy",
        choices=[p.value for p in MixedPolicy],
        default="selected",
        help="mixed mode: the plugins named, the ones whose detection fired, or all",
    )
    ex.add_argument("--exts", help="comma-separated extensions to keep, e.g. .png,.ogg")
    ex.add_argument(
        "--on-existing",
        choices=["new", "replace", "cancel"],
        default="ask",
        help="workspace already used: extract next to it, replace it, or stop (default: ask)",
    )
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
        from viwo.core.preflight import check

        deps = check(rt, lambda e: None)  # versions: pinned ones are free, others run once
        return Envelope.success({"bindings": rt.info()["slots"], "dependencies": deps}, rt.problems)
    if args.command == "detect":
        found = detect_all(rt, FolderProbe(args.game))
        return Envelope.success({k: v.to_legacy_dict() for k, v in found.items()})
    tool_commands = (
        "repack",
        "sanitize",
        "survey",
        "capture",
        "config",
        "install",
        "diag",
        "indexes",
    )
    if args.command in tool_commands:
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
    if args.command is None:
        print(cli_format.WELCOME)
        return 0
    if args.command == "serve":
        from viwo.api.server import serve

        return serve(args.ini, args.host, args.port, not args.no_browser)
    try:
        envelope = _run(args)
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
        print(cli_format.FORMATTERS[args.command](envelope.data))
    return 0 if envelope.ok else EXIT.get(envelope.error["code"], 1)


if __name__ == "__main__":
    sys.exit(main())
