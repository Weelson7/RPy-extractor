"""Asset sanitizer (doc 5): plan first (read-only), then apply only accepted actions; every
apply is journaled under .sanitizer/ and can be undone (sanitizer_journal.py).

Phase 1 (the safe recipe): zero-byte files, wrong extensions, exact duplicates, engine junk,
health checks. Phase 2: open-format copies by the lossless decoders. Phase 3, opt-in: lossy
transcodes and renumbered sequences. Rules are providers (`sanitizer_rules`, core and plugins,
and `sanitizer_convert` for the rules that write files) run in cost order.
"""

import json
import shutil
import time
import uuid
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError
from viwo.contracts.sanitizer import WRITES

from .curation import trash
from .pipeline.guard import guarded
from .sanitizer_journal import JOURNAL, move, plan_id_of, record, undo, ws_file
from .sanitizer_rules import BatchRule, RuleContext, collect_rules, contained, rule_ids, sniff
from .steps import Step
from .workspace import write_atomic

ROOT = ".sanitizer"
SAFE = "phase1-safe"
RECIPES = [  # phase 1 lists every enabled, non-lossy rule in play; the others name theirs
    {"id": SAFE, "name": "Safe cleanup", "phase": 1, "lossy": False, "rules": []},
    {"id": "phase2-convert", "name": "Open-format copies", "phase": 2, "lossy": False}
    | {"rules": ["core.convert"]},
    {"id": "phase2-replace", "name": "Open formats, originals to the trash", "phase": 2}
    | {"lossy": False, "rules": ["core.convert_replace"]},
    {"id": "phase3-audio", "name": "Audio to Opus", "phase": 3, "lossy": True}
    | {"rules": ["core.transcode_audio"]},
    {"id": "phase3-video", "name": "Video to H.264 MP4", "phase": 3, "lossy": True}
    | {"rules": ["core.transcode_video"]},
    {"id": "phase3-renumber", "name": "Renumber sequences", "phase": 3, "lossy": False}
    | {"rules": ["core.renumber"]},
]
__all__ = ["ROOT", "RECIPES", "JOURNAL", "plan", "apply", "undo", "sniff", "recipes"]


def recipes(rules=None) -> list[dict]:
    """Every recipe with the rule ids in play and why it cannot act now ("" when it can)."""
    rules = rules or collect_rules()
    out = []
    for recipe in RECIPES:
        mine = _recipe_rules(recipe["id"], rules)
        why = "; ".join(w for w in (r.unready() for r in mine) if w)
        out.append({**recipe, "rules": rule_ids(mine), "unready": why or _absent(recipe, mine)})
    return out


def _absent(recipe: dict, mine: list) -> str:
    return "" if mine or recipe["id"] == SAFE else f"{', '.join(recipe['rules'])} not loaded"


def _recipe_rules(recipe: str, rules) -> list:
    found = next((r for r in RECIPES if r["id"] == recipe), None)
    if found is None:
        raise ViwoError("invalid_request", f"unknown sanitizer recipe {recipe!r}")
    if recipe == SAFE:  # never lossy, never an opt-in rule
        return [r for r in rules if r.default_enabled and not r.lossy]
    return [r for r in rules if r.rule_id in found["rules"]]


def _asset_files(workspace: Path, under: Path) -> list[Path]:
    groups = [under] if under != workspace else sorted(workspace.iterdir())
    return [
        p
        for group in groups
        if group.is_dir() and not ws.is_reserved(group.name)
        for p in sorted(group.rglob("*"))
        if p.is_file()
    ]


def plan(workspace: Path, sink=None, cancel=None, **opts) -> dict:
    """opts: rules (providers), recipe id, path (sub-folder), offset/limit (paging). The plan
    is saved in the workspace: a folder that may be a game is refused (guard.guarded)."""
    workspace = guarded(None, workspace)
    opts["recipe"] = opts.get("recipe") or SAFE
    rules = _recipe_rules(opts["recipe"], opts.get("rules") or collect_rules())
    under = contained(workspace, str(opts.get("path") or ""))
    if under is None or not under.is_dir():
        raise ViwoError(
            "invalid_request", f"path is not a folder inside the workspace: {opts.get('path')}"
        )
    ctx = RuleContext(workspace, cancel, sink)
    files, findings = _asset_files(workspace, under), []
    step = Step(sink, "scan", "Scanning files:", len(files))
    per_file = [r for r in rules if not isinstance(r, BatchRule)]
    for path in files:
        step.tick(cancel)
        for rule in per_file:
            if rule.applies_to(path) and (found := rule.inspect(path, ctx)):
                findings += [{**f, "lossy": rule.lossy} for f in found]
                break  # one verdict per file, cheapest rule first
    step.done()
    for rule in (r for r in rules if isinstance(r, BatchRule)):
        more = [{**f, "lossy": rule.lossy} for f in rule.inspect_all(files, ctx, findings)]
        gone = {f["path"] for f in more}
        findings = [f for f in findings if f["path"] not in gone] + more
    warnings = [w for w in (r.unready() for r in rules) if w]
    return _save_plan(workspace, files, findings, {**opts, "warnings": warnings})


def _save_plan(workspace: Path, files: list[Path], findings: list[dict], opts: dict) -> dict:
    for finding in findings:  # remembered so that a stale plan is never applied
        file = workspace.joinpath(*Path(finding["path"]).parts)
        finding["size"] = file.stat().st_size if file.is_file() else -1
    plan_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    result = {"planId": plan_id, "recipeId": opts["recipe"], "scanned": len(files)}
    result |= {"findings": findings, "warnings": opts["warnings"]}
    folder = workspace / ROOT / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    write_atomic(folder / f"{plan_id}.json", json.dumps(result, indent=1))
    offset, limit = max(0, int(opts.get("offset") or 0)), int(opts.get("limit") or 0)
    page = findings[offset : offset + limit] if limit > 0 else findings[offset:]
    page = [{**f, "index": offset + i} for i, f in enumerate(page)]  # accept[] indexes
    return {**result, "findings": page, "total": len(findings), "offset": offset, "limit": limit}


def _act(workspace: Path, finding: dict) -> str:
    """Trash or rename one file; returns where it went (workspace-relative)."""
    src = ws_file(workspace, finding["path"])
    if src is None or not src.is_file():
        raise OSError("file is gone or outside the workspace")
    if finding["action"] in ("trash", "replace"):
        dest = trash.area(workspace, "items").joinpath(*Path(finding["path"]).parts)
    else:
        name = ws.safe_member(str(finding.get("to", "")))
        if name is None or len(name.parts) != 1:
            raise OSError("bad new name")
        dest = src.with_name(name.name)
    return move(src, dest).relative_to(workspace).as_posix()


def _write(workspace: Path, finding: dict, rule, ctx: RuleContext, journal: list) -> list[str]:
    """A finding whose rule writes files: its copies made and committed (and, for `replace`,
    the original then trashed); returns the files made. Journaled as each lands."""
    from .sanitizer_convert import commit

    if rule is None:
        raise OSError(f"rule {finding['rule']} is not loaded: scan again")
    if ws_file(workspace, finding["path"]) is None:
        raise OSError("file is outside the workspace")
    ctx.cache.mkdir(parents=True, exist_ok=True)
    try:
        origin = rule.fix(finding, ctx)
    except ViwoError as exc:  # a cancel stops the batch; any other refusal is this file's
        if exc.code == "cancelled":
            raise
        raise OSError(exc.message) from exc
    except OSError:
        raise
    except Exception as exc:  # noqa: BLE001  (a decoder's crash is this file's failure)
        raise OSError(f"{type(exc).__name__}: {exc}"[:300]) from exc
    made: list[dict] = []
    try:
        commit(workspace, ctx.cache, origin, made)
    finally:
        journal += made
    if not made:
        raise OSError(f"{finding['rule']} wrote nothing")
    if finding["action"] == "replace":
        journal.append([_act(workspace, finding), finding["path"]])
    return [m["made"] for m in made]


def _chosen(workspace: Path, findings: list[dict], accept) -> list[dict]:
    """The accepted findings of a plan, refused when a file changed since the scan.
    "all-safe" is every finding that is not lossy; "all" every one; else a list of indexes."""
    try:
        if accept in ("all-safe", "all"):
            picked = [i for i, f in enumerate(findings) if accept == "all" or not f.get("lossy")]
        else:
            picked = sorted({int(i) for i in accept})
    except (TypeError, ValueError):
        raise ViwoError("invalid_request", "accept must be 'all-safe', 'all' or a list of indexes")
    chosen = [findings[i] for i in picked if 0 <= i < len(findings)]
    for finding in chosen:
        file = ws_file(workspace, finding["path"])
        if "size" in finding and file and file.is_file() and file.stat().st_size != finding["size"]:
            raise ViwoError(
                "invalid_request", f"plan is stale: {finding['path']} changed; scan again"
            )
    return chosen


def apply(workspace: Path, plan_id: str, accept="all-safe", sink=None, cancel=None, rules=None):
    """`rules`: the providers whose `fix` writes files (phases 2-3); trash and rename need none."""
    workspace = guarded(None, workspace)  # it moves files: never in a folder that may be a game
    plan_id = plan_id_of(plan_id)
    path = workspace / ROOT / "plans" / f"{plan_id}.json"
    if not path.is_file():
        raise ViwoError("not_found", f"no sanitizer plan {plan_id}")
    chosen = _chosen(workspace, json.loads(path.read_text(encoding="utf-8"))["findings"], accept)
    journal, failed, converted = [], [], []
    by_id, cache = {r.rule_id: r for r in rules or ()}, workspace / ROOT / "cache" / plan_id
    step = Step(sink, "apply", "Applying actions:", len(chosen))
    try:
        for n, finding in enumerate(chosen):
            step.tick(cancel)
            try:
                if finding["action"] in WRITES:
                    ctx = RuleContext(workspace, cancel, sink, cache / str(n))
                    made = _write(workspace, finding, by_id.get(finding["rule"]), ctx, journal)
                    converted.append({"path": finding["path"], "made": made} | _what(finding))
                elif finding["action"] in ("trash", "rename"):
                    journal.append([_act(workspace, finding), finding["path"]])
            except OSError as exc:
                failed.append(f"{finding['path']}: {exc}")
    finally:  # a cancel keeps what was already moved or made undoable
        record(workspace, plan_id, journal)
        shutil.rmtree(cache, ignore_errors=True)
    if chosen:
        step.done()
    return _report(plan_id, chosen, journal, failed, converted)


def _what(finding: dict) -> dict:
    return {"rule": finding["rule"], "action": finding["action"], "lossy": finding.get("lossy")}


def _report(plan_id: str, chosen: list, journal: list, failed: list, converted: list) -> dict:
    moves = [entry for entry in journal if isinstance(entry, list)]
    moved = [{"from": before, "to": now} for now, before in moves]
    done = {before for _, before in moves}
    trashed = sum(1 for f in chosen if f["action"] in ("trash", "replace") and f["path"] in done)
    return {
        "planId": plan_id,
        "applied": len(done - {c["path"] for c in converted}) + len(converted),
        "moved": moved,
        "trashed": trashed,
        "converted": converted,
        "failed": failed,
        "undoToken": plan_id,
    }
