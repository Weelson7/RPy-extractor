"""`viwo replay`, `viwo unpack`, the tool commands, `viwo install` and plugin add-on commands."""

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from viwo.contracts.errors import Envelope, ViwoError
from viwo.contracts.pipeline import (
    CarveMode,
    ExtractionMode,
    ExtractionRequest,
    MixedPolicy,
    OnExisting,
)
from viwo.core.context import core_context, for_owner
from viwo.core.pipeline.runner import SECRET
from viwo.core.pipeline.unpack import unpack_all
from viwo.core.wiring.boot import boot
from viwo.core.wiring.registry import cli_commands

from .cli_dynamic import attach, capture, runtime
from .cli_guides import runbook, workbook
from .cli_patch import mod, patch


def replay_request(
    record_path: Path, workspace: Path, on_existing: OnExisting, secrets: dict[str, dict[str, str]]
) -> ExtractionRequest:
    """Rebuild the request stored in a run record; secrets must be supplied again."""
    try:
        stored = json.loads(record_path.read_text(encoding="utf-8"))["request"]
    except (OSError, ValueError, KeyError) as exc:
        raise ViwoError("invalid_request", f"not a ViWo run record: {record_path} ({exc})")
    options = {o: dict(v) for o, v in stored.get("options", {}).items()}
    for owner, values in options.items():
        for key, value in values.items():
            if value == SECRET:
                if key not in secrets.get(owner, {}):
                    raise ViwoError(
                        "needs_key",
                        f"secret option {owner}.{key} is not stored",
                        hint=f"pass --option {owner}.{key}=VALUE",
                    )
                values[key] = secrets[owner][key]
    exts = stored.get("selected_exts")
    return ExtractionRequest(
        stored["game_path"],
        str(workspace),
        frozenset(exts) if exts is not None else None,
        ExtractionMode(stored["mode"]),
        tuple(stored.get("plugins", ())),
        MixedPolicy(stored.get("mixed_policy", "selected")),
        plugin_options=options,
        on_existing=on_existing,
        carve=CarveMode(stored.get("carve", "unknown")),
    )


def context_factory(rt, root: Path, work: Path, options: dict, sink):
    base = core_context(rt, "unpack", root, work, sink)
    return lambda owner: for_owner(base, rt, owner, options.get(owner, {}))


def unpack_one(rt, archive: Path, out: Path, options: dict, sink) -> dict:
    """Unpack one archive (and nested archives) into out/<origin>/ via its slot."""
    if not archive.is_file():
        raise ViwoError("invalid_request", f"archive not found: {archive}")
    if out.exists() and any(out.iterdir()):
        raise ViwoError("refused", f"{out} is not empty")
    rt.temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=rt.temp_root) as tmp:
        make = context_factory(rt, archive.parent, Path(tmp), options, sink)
        report = unpack_all(rt, [(archive, archive.name)], Path(tmp) / "unpack", make)
        if not report.extracted:
            raise ViwoError("failed", "; ".join(report.failures) or "not a known archive")
        for folder, origin in report.origins.items():
            target = out / rt.os.fs.sanitize_filename(origin.replace(":", "!"), "archive")
            shutil.copytree(folder, target, dirs_exist_ok=True)
    return {
        "archive": str(archive),
        "out": str(out),
        "archives": report.extracted,
        "files": report.files,
        "byBackend": dict(report.by_backend),
        "failures": report.failures,
    }


def _repack(rt, args) -> Envelope:
    from viwo.core.roundtrip import repack

    if not args.plan and args.out is None:
        raise ViwoError("invalid_request", "give --out <folder> (or --plan)")
    note = event_printer(args)
    return Envelope.success(repack(rt, args.workspace, args.out, note, apply=not args.plan))


def _sanitize(rt, args) -> Envelope:
    from viwo.core import sanitizer
    from viwo.core.sanitizer_rules import collect_rules

    if not args.workspace.is_dir():
        raise ViwoError("not_found", f"workspace not found: {args.workspace}")
    if args.undo:
        return Envelope.success(sanitizer.undo(args.workspace, args.undo))
    result = sanitizer.plan(args.workspace, rules=collect_rules(rt))
    if args.apply:
        result["applied"] = sanitizer.apply(args.workspace, result["planId"])
    return Envelope.success(result)


def _survey(rt, args) -> Envelope:
    from viwo.core.survey import survey

    if not args.folder.is_dir():
        raise ViwoError("not_found", f"folder not found: {args.folder}")
    quiet = getattr(args, "quiet", False)
    note = None if quiet else (lambda g, i, n: print(f"[SURVEY] {i}/{n} {g}", file=sys.stderr))
    return Envelope.success({"games": survey(rt, args.folder, args.deep, note)})


def _diff(rt, args) -> Envelope:
    from .cli_check import diff_command

    return diff_command(args)


def _analyze(rt, args) -> Envelope:
    from .cli_check import analyze_command  # cli_check imports this module

    return analyze_command(rt, args)


def workspace_command(rt, args) -> Envelope:
    """One of the TOOLS commands (below)."""
    handler = TOOLS[args.command]
    if handler in (runtime, patch, mod):  # long runs: progress lines on stderr
        return handler(rt, args, event_printer(args))
    return handler(rt, args)


def event_printer(args):
    """Progress lines on stderr, each with the time of day, also with --json (the envelope is
    on stdout); --quiet only silences them (doc 12.4)."""
    if getattr(args, "quiet", False):
        return None
    return lambda e: print(f"{time.strftime('%H:%M:%S')} {e.legacy_line()}", file=sys.stderr)


def _system(rt, args) -> Envelope:
    """viwo diag [--out FILE] | viwo indexes update."""
    if args.command == "diag":
        from viwo.core.diag import bundle

        return Envelope.success({"path": str(bundle(rt, rt.config.server.workspace, args.out))})
    from viwo import __version__
    from viwo.core.indexes import update_indexes
    from viwo.core.thirdparty import home_of

    note = event_printer(args)
    return Envelope.success(
        update_indexes(home_of(rt.config), int(__version__.split(".")[0]), note)
    )


def _install(rt, args) -> Envelope:
    """viwo install [--all | <id>... | --game <slug>]: pinned tools into third_party/ (doc 10)."""
    from viwo.core.preflight import check, install

    note = event_printer(args)
    if getattr(args, "game", None):
        from viwo.core.indexes import DEFAULT_ROOT, install_game

        done = install_game(rt, DEFAULT_ROOT, args.game, args.game_version, note)
        return Envelope.success(
            {"installed": done["tools"] + list(done["scripts"]), "failed": done["failed"], **done},
            list(done["failed"].values()),
        )
    items = check(rt, note or (lambda e: None))
    wanted = set(args.ids)
    if args.all:
        wanted |= {i["id"] for i in items if not i["available"] and i["installable"]}
    unknown = wanted - {i["id"] for i in items}
    if unknown or not wanted:
        raise ViwoError(
            "invalid_request",
            f"unknown dependency id(s): {', '.join(sorted(unknown))}"
            if unknown
            else "nothing to install: give ids or --all",
            hint="ids are listed by `viwo slots`",
        )
    done, failed = [], {}
    for dep_id in sorted(wanted):
        try:
            done.append(install(rt, dep_id, note)["installed"])
        except ViwoError as exc:
            failed[dep_id] = exc.message + (f" ({exc.hint})" if exc.hint else "")
    from viwo.core.thirdparty import home_of

    where = str(home_of(rt.config) / "third_party")
    return Envelope.success(
        {"installed": done, "failed": failed, "where": where}, list(failed.values())
    )


def _config(args) -> Envelope:
    """viwo config generate [folder] | viwo config check [files] (strict; exit 2 on problems)."""
    from viwo.core.wiring import distros
    from viwo.core.wiring.boot import DEFAULT_INI

    if args.action == "generate":
        out = args.paths[0] if args.paths else DEFAULT_INI.parent / "distros"
        report = distros.generate(out)
        bad = {name: issues for name, issues in report.items() if issues}
        if bad:
            hint = "; ".join(f"{name}: {issues[0]}" for name, issues in sorted(bad.items()))
            raise ViwoError("invalid_request", f"{len(bad)} distro file(s) not written", hint=hint)
        return Envelope.success({"folder": str(out), "written": sorted(report)})
    files = args.paths or [args.ini or DEFAULT_INI]
    problems = {str(path): distros.check(path) for path in files}
    if any(problems.values()):
        hint = "; ".join(f"{f}: {p[0]}" for f, p in problems.items() if p)
        raise ViwoError("invalid_request", "config check failed", hint=hint)
    return Envelope.success({"checked": sorted(problems), "problems": problems})


def split_features(args) -> tuple[str, ...] | None:
    """`--features a,b` as a tuple (None when the flag is absent: the ini decides)."""
    text = getattr(args, "features", None)
    return tuple(f.strip() for f in text.split(",") if f.strip()) if text else None


def boot_for_cli(argv: list[str]):
    """Boot early so plugin add-on commands can join the parser (the global overrides
    `--ini`, `--os`, `--profile` and `--features` are read first).
    A bad configuration returns None here; the command itself reports it."""
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--ini", type=Path)
    pre.add_argument("--os", dest="os_id")
    pre.add_argument("--profile")
    pre.add_argument("--features")
    known, _ = pre.parse_known_args(argv)
    try:
        return boot(known.ini, known.os_id, profile=known.profile, features=split_features(known))
    except Exception:  # noqa: BLE001 (reported by the real boot in _run)
        return None


def add_plugin_commands(sub, common, rt) -> None:
    """Plugin subcommands (contract CliCommand); an override replaces the core subparser."""
    found, problems = cli_commands(rt.plugins, set(sub.choices))
    rt.problems.extend(problems)
    for name, (plugin_id, cmd) in found.items():
        if name in sub.choices:  # override: drop the core parser and its help entry
            sub.choices.pop(name)
            sub._choices_actions = [a for a in sub._choices_actions if a.dest != name]
        parser = sub.add_parser(name, parents=[common], help=f"{cmd.help} [{plugin_id}]")
        cmd.build(parser)
        parser.set_defaults(plugin_command=cmd)


def run_plugin_command(rt, cmd, args) -> Envelope:
    result = cmd.run(rt, args)
    return result if isinstance(result, Envelope) else Envelope.success(result)


TOOLS = {  # the tool commands (the dynamic and patching arms, survey, analyze, system): a handler
    "repack": _repack,
    "sanitize": _sanitize,
    "survey": _survey,
    "capture": capture,
    "dump": runtime,
    "trace": runtime,
    "profile": runtime,
    "agent": runtime,
    "record": runtime,
    "attach": attach,
    "analyze": _analyze,
    "diff": _diff,
    "patch": patch,
    "mod": mod,
    "config": lambda _rt, a: _config(a),
    "install": _install,
    "diag": _system,
    "indexes": _system,
    "workbook": workbook,
    "runbook": runbook,
}
