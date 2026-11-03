"""Sanitizer rule providers (doc 5.2): core rules and plugin rules share one object model.

A `SanitizerRule` looks at one file (`applies_to` is cheap, `inspect` may read); a `BatchRule`
looks at the whole set (duplicates). Rules declare a `cost` and run in cost order; `inspect`
never writes; `fix` is report-only in phase 1 (phase 2 writes into `.sanitizer/cache/`).
Findings are plain dicts: {rule, path, message, action, severity, ...}.
"""

from __future__ import annotations

import mmap
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from viwo.contracts.workspace import inside

from .carve import SIGNATURES
from .carve import formats2 as g
from .pipeline.collect import sha256

JUNK = {".import", ".meta", ".tmp", ".bak"}
JUNK_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
SAME = {".jpeg": ".jpg", ".midi": ".mid", ".tif": ".tiff"}
NEEDLE_EXT = {
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
    b"GIF8": ".gif",
    b"OggS": ".ogg",
}
NEEDLE_EXT |= {b"MThd": ".mid", b"DDS |": ".dds", b"glTF": ".glb", b"7z\xbc\xaf\x27\x1c": ".7z"}


@dataclass
class RuleContext:
    """What a rule may use: the workspace root, the cancel token, nothing else."""

    workspace: Path
    cancel: object = None

    def finding(self, rule: str, path: Path, message: str, action: str, **extra) -> dict:
        rel = path.relative_to(self.workspace).as_posix()
        base = {"rule": rule, "path": rel, "message": message, "action": action}
        return {**base, "severity": extra.pop("severity", "warn"), **extra}


class SanitizerRule:
    """Per-file rule. Subclasses set the class attributes and implement `inspect`."""

    rule_id = ""
    owner = "core"
    category = "health"
    default_enabled = True
    lossy = False
    cost = 1  # 1 = header peek .. 10 = transcode

    def dependencies(self) -> Sequence:
        return ()

    def applies_to(self, path: Path) -> bool:
        return True

    def inspect(self, path: Path, ctx: RuleContext) -> list[dict]:
        return []

    def fix(self, finding: dict, ctx: RuleContext) -> None:
        """Phase 1: report-only; core commits trash/rename itself."""


class BatchRule(SanitizerRule):
    """Rule over the whole file set (dedupe, numbering)."""

    def inspect_all(self, files: list[Path], ctx: RuleContext, earlier: list[dict]) -> list[dict]:
        return []


def sniff(path: Path) -> tuple[str, int] | None:
    """(suffix, size) of the format this file starts with, from the carver's sizers;
    size -1 when the file starts with a signature but its structure does not walk."""
    size = path.stat().st_size
    if size < 16:
        return None
    with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
        for needle, delta, sizer in SIGNATURES:
            if m[-delta : -delta + len(needle)] != needle:  # needle sits at -delta in the file
                continue
            try:
                found = sizer(m, 0, size, {}) if sizer is g.zip_file else sizer(m, 0, size)
            except (IndexError, ValueError, OverflowError, struct.error):
                found = None
            if found:
                return found[1], found[0]
            if path.suffix.lower() == NEEDLE_EXT.get(needle):
                return path.suffix.lower(), -1
    return None


class ZeroByte(SanitizerRule):
    rule_id, category, cost = "core.zero_byte", "health", 1

    def inspect(self, path: Path, ctx: RuleContext) -> list[dict]:
        if path.stat().st_size == 0:
            return [ctx.finding(self.rule_id, path, "empty file", "trash")]
        return []


class Junk(SanitizerRule):
    rule_id, category, cost = "core.junk", "junk", 1

    def inspect(self, path: Path, ctx: RuleContext) -> list[dict]:
        ext, name = path.suffix.lower(), path.name.lower()
        if ext in JUNK or name in JUNK_NAMES:
            return [ctx.finding(self.rule_id, path, f"engine/OS junk ({ext or name})", "trash")]
        return []


class Identity(SanitizerRule):
    """Magic-byte identity and structural health in one read (core.extension, core.health)."""

    rule_id, category, cost = "core.extension", "identity", 2

    def applies_to(self, path: Path) -> bool:
        return path.stat().st_size >= 16

    def inspect(self, path: Path, ctx: RuleContext) -> list[dict]:
        found = sniff(path)
        if found is None:
            return []
        real, length = found
        ext, size = path.suffix.lower(), path.stat().st_size
        if length != size:
            what = (
                "truncated or corrupt" if length < 0 else f"{size - length} bytes of trailing data"
            )
            return [ctx.finding("core.health", path, f"{real[1:]} {what}", "none")]
        if SAME.get(ext, ext) != real and not (ext == ".wav" and real == ".wem"):
            new = path.with_suffix(real).name
            return [ctx.finding(self.rule_id, path, f"is really {real}", "rename", to=new)]
        return []


class Duplicates(BatchRule):
    """Identical files: keep the cleanest copy (no __N suffix, right extension, first path)."""

    rule_id, category, cost = "core.duplicate", "dedupe", 3

    def inspect_all(self, files: list[Path], ctx: RuleContext, earlier: list[dict]) -> list[dict]:
        from .steps import Step

        flagged = {f["path"] for f in earlier if f["action"] == "trash"}
        renames = {f["path"] for f in earlier if f["action"] == "rename"}
        by_size: dict[int, list[Path]] = {}
        for path in files:
            by_size.setdefault(path.stat().st_size, []).append(path)
        todo = [p for same in by_size.values() if len(same) > 1 for p in same]
        step, by_hash = Step(getattr(ctx, "sink", None), "hash", "Hashing files:", len(todo)), {}
        for path in todo:
            step.tick(ctx.cancel)
            by_hash.setdefault(sha256(path), []).append(path)
        if todo:
            step.done()
        out = []
        for same in (s for s in by_hash.values() if len(s) > 1):
            rel = {p: p.relative_to(ctx.workspace).as_posix() for p in same}
            candidates = [p for p in same if rel[p] not in flagged]  # never trash the last copy
            if len(candidates) < 2:
                continue
            keep = min(candidates, key=lambda p: ("__" in p.stem, rel[p] in renames, rel[p]))
            out += [
                ctx.finding(self.rule_id, p, f"same bytes as {rel[keep]}", "trash")
                for p in candidates
                if p != keep
            ]
        return out


def core_rules() -> list[SanitizerRule]:
    return [ZeroByte(), Junk(), Identity(), Duplicates()]


def collect_rules(rt=None) -> list[SanitizerRule]:
    """Core rules plus every plugin's `sanitizer_rules()`, in cost order; bad ids dropped."""
    rules = core_rules()
    for plugin_id, plugin in sorted(getattr(rt, "plugins", {}).items()):
        for rule in plugin.sanitizer_rules():
            if isinstance(rule, SanitizerRule) and rule.rule_id.startswith(f"{plugin_id}."):
                rules.append(rule)
    return sorted(rules, key=lambda r: (r.cost, r.rule_id))


def rule_ids(rules: Sequence[SanitizerRule]) -> list[str]:
    return [r.rule_id for r in rules] + (
        ["core.health"] if any(r.rule_id == "core.extension" for r in rules) else []
    )


def contained(workspace: Path, rel: str) -> Path | None:
    """A sub-folder given by the user, only when it stays inside the workspace."""
    target = (workspace / rel).resolve() if rel else workspace
    return target if rel == "" or inside(workspace, target) else None
