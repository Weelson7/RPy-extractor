"""`viwo replay` and `viwo unpack` (doc 12.4)."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from viwo.contracts.errors import Envelope, ViwoError
from viwo.contracts.pipeline import (
    CarveMode,
    ExtractionMode,
    ExtractionRequest,
    MixedPolicy,
    OnExisting,
)
from viwo.contracts.plugin import ExtractionContext
from viwo.contracts.types import CancelToken, DetectionResult
from viwo.core.pipeline.runner import SECRET
from viwo.core.pipeline.unpack import unpack_all


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
    def make(owner: str) -> ExtractionContext:
        merged = {**rt.owner_options(owner), **options.get(owner, {})}
        return ExtractionContext(
            "unpack",
            root,
            work / "staging" / owner,
            work / "scratch",
            rt.os,
            DetectionResult(owner, 0.0, (), owner),
            None,
            merged,
            sink,
            CancelToken(),
            "core" if owner == "core" else f"plugin:{owner}",
        )

    return make


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


def workspace_command(rt, args) -> Envelope:
    """survey, repack and sanitize: commands that read or write a workspace / library."""
    if args.command == "repack":
        from viwo.core.roundtrip import repack

        if not args.plan and args.out is None:
            raise ViwoError("invalid_request", "give --out <folder> (or --plan)")
        note = None if args.json else (lambda e: print(e.legacy_line(), file=sys.stderr))
        return Envelope.success(repack(rt, args.workspace, args.out, note, apply=not args.plan))
    if args.command == "sanitize":
        from viwo.core import sanitizer

        if args.undo:
            return Envelope.success(sanitizer.undo(args.workspace, args.undo))
        result = sanitizer.plan(args.workspace)
        if args.apply:
            result["applied"] = sanitizer.apply(args.workspace, result["planId"])
        return Envelope.success(result)
    if args.command == "survey":
        from viwo.core.survey import survey

        if not args.folder.is_dir():
            raise ViwoError("not_found", f"folder not found: {args.folder}")
        note = (
            None if args.json else (lambda g, i, n: print(f"[SURVEY] {i}/{n} {g}", file=sys.stderr))
        )
        return Envelope.success({"games": survey(rt, args.folder, args.deep, note)})
    if args.command == "capture":
        from viwo.core.capture import CaptureRequest, capture

        note = None if args.json else (lambda e: print(e.legacy_line(), file=sys.stderr))
        req = CaptureRequest(args.game, args.exe, args.workspace, args.confirm)
        return Envelope.success(capture(rt, req, note))
    if args.command == "config":
        return _config(args)
    raise ViwoError("invalid_request", f"unknown command {args.command}")


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
