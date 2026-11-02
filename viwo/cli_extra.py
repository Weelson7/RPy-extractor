"""`viwo replay` and `viwo unpack` (doc 12.4)."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.pipeline import ExtractionMode, ExtractionRequest, MixedPolicy, OnExisting
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
