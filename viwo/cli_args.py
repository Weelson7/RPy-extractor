"""Argument definitions of the core `viwo` subcommands (doc 12.4); `cli.py` wires them."""

from __future__ import annotations

import argparse
from pathlib import Path

from viwo.contracts.pipeline import (
    CarveMode,
    ExtractionMode,
    ExtractionRequest,
    MixedPolicy,
    OnExisting,
)
from viwo.core.capture.policy import CONFIRMATION, DEFAULT_AUTO

EPILOG = """examples:
  viwo survey D:/Games                 what can be pulled from each game (read-only)
  viwo extract D:/Games/Foo --workspace out/foo
  viwo unpack data.pak --out out/pak --slot unarchive.upak --backend spare
  viwo slots --check                   run every bound backend's self-test
  viwo install --all                   every missing pinned tool into third_party/
  viwo install --game skyrim-se        what an index entry needs (tools, scripts)
  viwo capture D:/Games/Foo --exe Foo.exe --workspace out/foo --confirm

global flags: --ini PATH, --os auto|linux|windows, --json (envelope on stdout),
--quiet (no progress lines on stderr), --verbose (also the effective ini and bindings).
exit codes: 0 ok | 1 failed or not found | 2 bad request or config | 3 refused (folder
containment, unsupported OS layer) | 4 strict preflight failed | 130 cancelled (Ctrl+C).
Errors print "viwo: <code>: <message>" and a hint; `--json` prints the envelope instead."""


def core_commands(command) -> None:
    """info, slots, detect, extract, replay, unpack, then the tool commands."""
    command("info", "OS layer, plugins, slot bindings, problems")
    command("slots", "slot bindings and dependency status").add_argument(
        "--check", action="store_true", help="run every bound backend's self-test (exit 1 on fail)"
    )
    command("detect", "which engine a game folder uses (read-only)").add_argument(
        "game", type=Path, help="the game folder"
    )
    extract_args(command("extract", "extract a game folder into a workspace"))
    rp = command("replay", "re-run the extraction stored in a run record")
    rp.add_argument("record", type=Path, help="<workspace>/.extraction_metadata/runs/<id>.json")
    rp.add_argument("--workspace", type=Path, required=True, help="folder to extract into")
    rp.add_argument("--on-existing", choices=["new", "replace", "cancel"], default="ask")
    rp.add_argument("--option", action="append", default=[], help="secret: plugin.key=value")
    up = command("unpack", "unpack one archive (nested archives too)")
    up.add_argument("archive", type=Path, help="one archive file (zip, rpa, pck, pak, ...)")
    up.add_argument("--out", type=Path, required=True, help="empty output folder")
    up.add_argument("--option", action="append", default=[], help="plugin.key=value")
    up.add_argument("--slot", help="force one slot, e.g. unarchive.7z (no nested unpack)")
    up.add_argument("--backend", help="main | spare | <backend id> for that slot")
    tool_commands(command)


def capture_command(command) -> None:
    """capture: unattended by default (--auto SECONDS: one frame, then the game stops; 0 = F12)."""
    cp = command("capture", "runtime GPU capture with RenderDoc (opt-in; see --help)")
    cp.description = (
        "Runs the game under RenderDoc and harvests every capture you take (F12) into the "
        "workspace. Opt-in: add `capture` to [startup] features in the ini and pass --confirm "
        "once per game. Anti-cheat and online titles only produce warnings; you are responsible."
    )
    cp.add_argument("game", type=Path, help="the game folder")
    cp.add_argument("--exe", type=Path, required=True, help="the game executable to launch")
    cp.add_argument("--workspace", type=Path, required=True, help="where captures are gathered")
    cp.add_argument("--confirm", action="store_true", help=f"I confirm: {CONFIRMATION}")
    cp.add_argument(
        "--auto",
        type=float,
        default=DEFAULT_AUTO,
        metavar="SECONDS",
        help="one frame after SECONDS, then the game stops (default 30; 0 = press F12 yourself)",
    )


def tool_commands(command) -> None:
    """survey, repack, capture, sanitize, config, install, diag, indexes."""
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
    capture_command(command)
    analysis_command(command)
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


def analysis_command(command) -> None:
    """viwo analyze (doc 6): list the targets, run one, or open it in the GUI tool."""
    an = command("analyze", "static analysis of a game binary (Ghidra headless; opt-in)")
    an.description = (
        "Lists the binaries the plugins propose (--list), runs the analyzer for one target into "
        "<workspace>/.analysis/, or opens the prepared project in the GUI tool (--open). Opt-in: "
        "add `analysis` to [startup] features; you are responsible for having the right to "
        "analyse the binaries."
    )
    an.add_argument("game", type=Path, help="the game folder (read-only; the binary is copied)")
    an.add_argument("--workspace", type=Path, help="where .analysis/ lands (required to run)")
    an.add_argument("--target", metavar="KEY", help="target key from --list")
    an.add_argument("--list", action="store_true", help="only list the targets")
    an.add_argument("--open", metavar="HANDOFF", nargs="?", const="", help="continue in the GUI")
    an.add_argument("--timeout", type=int, default=0, help="seconds (default 4 h)")


def extract_args(ex: argparse.ArgumentParser) -> None:
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


def options(items: list[str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for item in items:
        owner_key, _, value = item.partition("=")
        owner, _, key = owner_key.partition(".")
        out.setdefault(owner, {})[key] = value
    return out


def request(args) -> ExtractionRequest:
    opts = options(args.option)
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
        plugin_options=opts,
        on_existing=OnExisting(args.on_existing),
        carve=CarveMode(args.carve),
    )
