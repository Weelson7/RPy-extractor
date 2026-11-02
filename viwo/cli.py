"""`viwo` command line (doc 12.4)."""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

from viwo.contracts.errors import Envelope, ViwoError
from viwo.contracts.pipeline import ExtractionMode, ExtractionRequest, MixedPolicy, OnExisting
from viwo.core.jobs import JobRunner
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import detect_all, extract
from viwo.core.wiring.boot import boot

EXIT = {"invalid_request": 2, "needs_decision": 2, "refused": 3, "cancelled": 130}
LEGACY_APP = Path(__file__).resolve().parent.parent / "RPy-extractor" / "extract.py"


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="viwo", description="Vidya Wormhole")
    ap.add_argument("--ini", type=Path, help="startup ini (default: startup.ini)")
    ap.add_argument("--os", dest="os_id", help="auto | linux | windows")
    ap.add_argument("--json", action="store_true", help="print a JSON envelope")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="OS layer, plugins, slot bindings, problems")
    sub.add_parser("slots", help="slot bindings and dependency status")
    sub.add_parser("detect", help="engine detection").add_argument("game", type=Path)
    ex = sub.add_parser("extract", help="extract a game folder into a workspace")
    ex.add_argument("game", type=Path)
    ex.add_argument("--workspace", type=Path, required=True)
    ex.add_argument("--plugin", help="force one plugin")
    ex.add_argument("--mixed", help="comma-separated plugins for mixed mode")
    ex.add_argument("--policy", choices=[p.value for p in MixedPolicy], default="selected")
    ex.add_argument("--exts", help="comma-separated extensions to keep, e.g. .png,.ogg")
    ex.add_argument("--on-existing", choices=["new", "replace", "cancel"], default="ask")
    ex.add_argument("--option", action="append", default=[], help="plugin.key=value")
    sv = sub.add_parser("serve", help="start the web UI (v1 server)")
    sv.add_argument("rest", nargs=argparse.REMAINDER)
    return ap


def _request(args) -> ExtractionRequest:
    options: dict[str, dict[str, str]] = {}
    for item in args.option:
        owner_key, _, value = item.partition("=")
        owner, _, key = owner_key.partition(".")
        options.setdefault(owner, {})[key] = value
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
    sink = None if args.json else (lambda e: print(e.legacy_line(), file=sys.stderr))
    job = JobRunner(sink).submit(
        "extract", lambda jid, s, c: extract(rt, _request(args), jid, s, c), background=False
    )
    if job.error:
        raise ViwoError(**{k: job.error[k] for k in ("code", "message", "owner", "hint")})
    return Envelope.success(job.result.to_legacy_dict(), list(job.result.warnings))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "serve":
        sys.path.insert(0, str(LEGACY_APP.parent))
        sys.argv = [str(LEGACY_APP), *args.rest]
        runpy.run_path(str(LEGACY_APP), run_name="__main__")
        return 0
    try:
        envelope = _run(args)
    except ViwoError as exc:
        envelope = Envelope.failure(exc)
    if args.json or not envelope.ok:
        print(json.dumps(envelope.to_dict(), indent=2, default=str))
    else:
        print(json.dumps(envelope.data, indent=2, default=str))
    return 0 if envelope.ok else EXIT.get(envelope.error["code"], 1)


if __name__ == "__main__":
    sys.exit(main())
