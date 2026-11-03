"""Asset sanitizer, phase 1 (doc 5): zero-byte files, wrong extensions, exact duplicates,
engine junk, and health checks. Plan first (read-only), then apply only accepted safe
actions; every apply is journaled under .sanitizer/ and can be undone. Nothing lossy.

Rules are providers (`sanitizer_rules.SanitizerRule`, core and plugins) run in cost order.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

from . import provenance
from .curation import trash
from .sanitizer_rules import BatchRule, RuleContext, collect_rules, contained, rule_ids, sniff
from .steps import Step
from .workspace import write_atomic

ROOT = ".sanitizer"
RECIPES = [
    {
        "id": "phase1-safe",
        "name": "Safe cleanup",
        "lossy": False,
        "rules": ["core.zero_byte", "core.junk", "core.extension", "core.duplicate", "core.health"],
    }
]
__all__ = ["ROOT", "RECIPES", "plan", "apply", "undo", "sniff"]


def recipes(rules=None) -> list[dict]:
    """Built-in recipes; the safe recipe lists every enabled, non-lossy rule in play."""
    active = [r for r in (rules or collect_rules()) if r.default_enabled and not r.lossy]
    return [{**RECIPES[0], "rules": rule_ids(active)}]


def _asset_files(workspace: Path, under: Path) -> list[Path]:
    groups = [under] if under != workspace else sorted(workspace.iterdir())
    return [
        p
        for group in groups
        if group.is_dir() and not ws.is_reserved(group.name)
        for p in sorted(group.rglob("*"))
        if p.is_file()
    ]


def _recipe_rules(recipe: str, rules) -> list:
    known = {r["id"] for r in RECIPES}
    if recipe not in known:
        raise ViwoError("invalid_request", f"unknown sanitizer recipe {recipe!r}")
    return [r for r in rules if r.default_enabled and not r.lossy]  # phase 1: never lossy


def plan(workspace: Path, sink=None, cancel=None, **opts) -> dict:
    """opts: rules (providers), recipe id, path (sub-folder), offset/limit (paging)."""
    rules = _recipe_rules(
        opts.get("recipe") or RECIPES[0]["id"], opts.get("rules") or collect_rules()
    )
    under = contained(workspace, str(opts.get("path") or ""))
    if under is None or not under.is_dir():
        raise ViwoError(
            "invalid_request", f"path is not a folder inside the workspace: {opts.get('path')}"
        )
    ctx = RuleContext(workspace, cancel)
    ctx.sink = sink  # type: ignore[attr-defined]  # batch rules report their own step
    files, findings = _asset_files(workspace, under), []
    step = Step(sink, "scan", "Scanning files:", len(files))
    per_file = [r for r in rules if not isinstance(r, BatchRule)]
    for path in files:
        step.tick(cancel)
        for rule in per_file:
            if rule.applies_to(path) and (found := rule.inspect(path, ctx)):
                findings += found
                break  # one verdict per file, cheapest rule first
    step.done()
    for rule in (r for r in rules if isinstance(r, BatchRule)):
        more = rule.inspect_all(files, ctx, findings)
        gone = {f["path"] for f in more}
        findings = [f for f in findings if f["path"] not in gone] + more
    return _save_plan(workspace, files, findings, opts)


def _save_plan(workspace: Path, files: list[Path], findings: list[dict], opts: dict) -> dict:
    for finding in findings:  # remembered so that a stale plan is never applied
        file = workspace.joinpath(*Path(finding["path"]).parts)
        finding["size"] = file.stat().st_size if file.is_file() else -1
    plan_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    recipe = opts.get("recipe") or RECIPES[0]["id"]
    result = {"planId": plan_id, "recipeId": recipe, "scanned": len(files), "findings": findings}
    folder = workspace / ROOT / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    write_atomic(folder / f"{plan_id}.json", json.dumps(result, indent=1))
    offset, limit = max(0, int(opts.get("offset") or 0)), int(opts.get("limit") or 0)
    page = findings[offset : offset + limit] if limit > 0 else findings[offset:]
    page = [{**f, "index": offset + i} for i, f in enumerate(page)]  # accept[] indexes
    return {**result, "findings": page, "total": len(findings), "offset": offset, "limit": limit}


def _move(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = ws.next_free(dest)
    shutil.move(str(src), str(target))
    return target


PLAN_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


def _plan_id(value) -> str:
    if not PLAN_ID.match(str(value)):
        raise ViwoError("invalid_request", f"not a sanitizer plan id: {value!r}")
    return str(value)


def _ws_file(workspace: Path, rel) -> Path | None:
    """A path read back from a plan or journal, only if it stays inside the workspace."""
    member = ws.safe_member(str(rel))
    path = workspace.joinpath(*member.parts) if member else None
    return path if path is not None and ws.inside(workspace, path) else None


def _act(workspace: Path, finding: dict) -> str:
    """Carry out one finding; returns where the file went (workspace-relative)."""
    src = _ws_file(workspace, finding["path"])
    if src is None or not src.is_file():
        raise OSError("file is gone or outside the workspace")
    if finding["action"] == "trash":
        dest = trash.area(workspace, "items").joinpath(*Path(finding["path"]).parts)
    else:
        name = ws.safe_member(str(finding.get("to", "")))
        if name is None or len(name.parts) != 1:
            raise OSError("bad new name")
        dest = src.with_name(name.name)
    return _move(src, dest).relative_to(workspace).as_posix()


def _chosen(workspace: Path, findings: list[dict], accept) -> list[dict]:
    """The accepted findings of a plan, refused when a file changed since the scan."""
    try:
        picked = range(len(findings)) if accept == "all-safe" else sorted({int(i) for i in accept})
    except (TypeError, ValueError):
        raise ViwoError("invalid_request", "accept must be 'all-safe' or a list of indexes")
    chosen = [findings[i] for i in picked if 0 <= i < len(findings)]
    for finding in chosen:
        file = _ws_file(workspace, finding["path"])
        if "size" in finding and file and file.is_file() and file.stat().st_size != finding["size"]:
            raise ViwoError(
                "invalid_request", f"plan is stale: {finding['path']} changed; scan again"
            )
    return chosen


def apply(workspace: Path, plan_id: str, accept="all-safe", sink=None, cancel=None) -> dict:
    plan_id = _plan_id(plan_id)
    path = workspace / ROOT / "plans" / f"{plan_id}.json"
    if not path.is_file():
        raise ViwoError("not_found", f"no sanitizer plan {plan_id}")
    chosen = _chosen(workspace, json.loads(path.read_text(encoding="utf-8"))["findings"], accept)
    journal, failed = [], []
    step = Step(sink, "apply", "Applying actions:", len(chosen))
    for finding in chosen:
        step.tick(cancel)
        if finding["action"] in ("trash", "rename"):
            try:
                journal.append([_act(workspace, finding), finding["path"]])
            except OSError as exc:
                failed.append(f"{finding['path']}: {exc}")
    if chosen:
        step.done()
    folder = workspace / ROOT / "journal"
    folder.mkdir(parents=True, exist_ok=True)
    record = folder / f"{plan_id}.json"  # several applies of one plan add up
    earlier = json.loads(record.read_text(encoding="utf-8")) if record.is_file() else []
    write_atomic(record, json.dumps(earlier + journal))
    provenance.rewrite(workspace, {before: now for now, before in journal})
    moved = [{"from": before, "to": now} for now, before in journal]
    return {
        "planId": plan_id,
        "applied": len(journal),
        "moved": moved,
        "trashed": sum(1 for f in chosen if f["action"] == "trash") - len(failed),
        "failed": failed,
        "undoToken": plan_id,
    }


def undo(workspace: Path, token: str, sink=None, cancel=None) -> dict:
    path = workspace / ROOT / "journal" / f"{_plan_id(token)}.json"
    if not path.is_file():
        raise ViwoError("not_found", f"nothing to undo for {token}")
    restored, back = 0, {}
    entries = json.loads(path.read_text(encoding="utf-8"))
    step = Step(sink, "undo", "Undoing actions:", len(entries))
    for now, before in reversed(entries):
        step.tick(cancel)
        src, dest = _ws_file(workspace, now), _ws_file(workspace, before)
        if src is not None and dest is not None and src.is_file():
            back[now] = _move(src, dest).relative_to(workspace).as_posix()
            restored += 1
    if entries:
        step.done()
    provenance.rewrite(workspace, back)
    path.unlink()
    return {"restored": restored}
