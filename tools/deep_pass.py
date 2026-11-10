"""Deep pass (L7, real games): every capability on one installed game, judged on its output.
Static: detect, survey (deep), a full extraction, the accounting of every game byte and every
workspace file, every decoded file opened by a real reader, a contact sheet of images to look
at, cleanup plan/apply/undo, every analysis target run to completion. Patching: a real edit per
container type repacked into a patched copy and read back, an AOB patch set, a mod packed,
checked and applied. Dynamic (`--dynamic`): RenderDoc capture, the engine agent, a memory dump,
an API trace and the game's sound while it runs. The game folder is only read (checked).

Usage: python tools/deep_pass.py <game folder> [--out viwo-data/deep-pass/<slug>]
       [--dynamic] [--exe EXE] [--analysis-timeout SECONDS] [--keep]
Run it from a worktree at a committed version (docs/HANDOFF.md). Writes report.json/.md.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from deep_arms import analyses, dynamic, patching  # noqa: E402
from deep_checks import account, contact_sheet, validate  # noqa: E402
from integration_games import viwo  # noqa: E402

from viwo.core.pipeline.guard import change_warning, snapshot  # noqa: E402


class Pass:
    """One game's pass: every step's outcome, timing and data, in order."""

    def __init__(self, game: Path, out: Path) -> None:
        self.game, self.out = game, out
        self.ws = out / "ws"
        self.steps: dict[str, dict] = {}

    def run(self, name: str, args: list[str]) -> dict | None:
        """`viwo --json <args>`; the step is ok when the envelope says so."""
        start = time.monotonic()
        code, envelope, err = viwo(args)
        ok = code == 0 and bool(envelope and envelope.get("ok"))
        said = list((envelope or {}).get("warnings") or [])  # what ViWo said (never silent)
        self.record(name, ok, start, error="" if ok else _why(envelope, err), warnings=said[:60])
        self.steps[name]["warningCount"] = len(said)
        return envelope.get("data") if ok and envelope else None

    def record(self, name: str, ok: bool, start: float, **data) -> None:
        self.steps[name] = {"ok": ok, "seconds": round(time.monotonic() - start, 1), **data}
        mark = "ok  " if ok else "FAIL"
        print(f"   {mark} {name} ({self.steps[name]['seconds']} s)", flush=True)

    def check(self, name: str, fn, *args) -> object:
        """A step done here (accounting, validation): exceptions become a failed step."""
        start = time.monotonic()
        try:
            data = fn(*args)
        except Exception as exc:  # noqa: BLE001  (the pass goes on, the failure is recorded)
            self.record(name, False, start, error=f"{type(exc).__name__}: {exc}")
            return None
        self.record(name, True, start, data=data)
        return data


def _why(envelope: dict | None, err: str) -> str:
    if envelope and envelope.get("error"):
        e = envelope["error"]
        return f"{e.get('code')}: {e.get('message')}"[:600]
    return err.strip().splitlines()[-1][:600] if err.strip() else "no envelope"


def static(p: Pass) -> dict | None:
    detect = p.run("detect", ["detect", str(p.game)])
    p.steps["detect"]["data"] = detect
    survey = p.run("survey", ["survey", str(p.game), "--deep"])
    if survey is not None:
        (p.out / "survey.json").write_text(json.dumps(survey, indent=1), encoding="utf-8")
    args = ["extract", str(p.game), "--workspace", str(p.ws), "--on-existing", "replace"]
    result = p.run("extract", args)
    if result is not None:
        p.steps["extract"]["data"] = _extract_summary(result)
    if not p.ws.is_dir():
        return None
    p.check("account", account, p.game, p.ws)
    p.check("validate", validate, p.ws)
    p.check("contact_sheet", contact_sheet, p.ws, p.out / "contact.png")
    _cleanup(p)
    return result


def _extract_summary(data: dict) -> dict:
    keep = ("success", "copiedFiles", "archivesFound", "archivesExtracted", "carvedFiles")
    out = {k: data.get(k) for k in keep}
    out["plugins"] = [p.get("plugin") or p.get("id") for p in data.get("plugins", [])]
    out["byBackend"] = data.get("byBackend", {})
    return out


def _cleanup(p: Pass) -> None:
    """Plan, apply, undo: the workspace comes back exactly as it was."""
    from tests.helpers import tree_hashes

    plan = p.run("sanitize_plan", ["sanitize", str(p.ws)])
    p.steps["sanitize_plan"]["findings"] = (plan or {}).get("total", 0)
    if not plan or not plan.get("total"):
        return
    before = tree_hashes(p.ws, skip_reserved=True)
    applied = p.run("sanitize_apply", ["sanitize", str(p.ws), "--apply"])
    token = ((applied or {}).get("applied") or {}).get("undoToken")
    if token:
        p.run("sanitize_undo", ["sanitize", str(p.ws), "--undo", str(token)])
        same = tree_hashes(p.ws, skip_reserved=True) == before
        p.steps["sanitize_undo"]["restored"] = same
        p.steps["sanitize_undo"]["ok"] = p.steps["sanitize_undo"]["ok"] and same


def report_md(p: Pass) -> str:
    lines = [f"# Deep pass: {p.game.name}", "", "| Step | Result | Seconds | Note |"]
    lines.append("|---|---|---|---|")
    for name, s in p.steps.items():
        note = s.get("error") or _note(s.get("data"))
        lines.append(f"| {name} | {'ok' if s['ok'] else 'FAIL'} | {s['seconds']} | {note} |")
    return "\n".join(lines) + "\n"


def _note(data) -> str:
    if not isinstance(data, dict):
        return ""
    text = ", ".join(f"{k}={v}" for k, v in data.items() if isinstance(v, (int, float, str)))
    return re.sub(r"\s+", " ", text)[:300]


def _arguments(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("game", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--dynamic", action="store_true", help="also the dynamic arm (runs the game)")
    ap.add_argument("--exe", type=Path, help="the game's executable (default: the largest)")
    ap.add_argument("--analysis-timeout", type=int, default=3600)
    ap.add_argument("--keep", action="store_true", help="keep the workspace and copies")
    ap.add_argument(
        "--arms",
        default="static,analysis,patching",
        help="which parts run: static,analysis,patching (patching alone needs --workspace)",
    )
    ap.add_argument("--workspace", type=Path, help="an extraction of this game to reuse")
    args = ap.parse_args(argv)
    arms = {a.strip() for a in args.arms.split(",") if a.strip()}
    if unknown := arms - {"static", "analysis", "patching"}:
        ap.error(f"--arms: unknown {sorted(unknown)}")
    return args, arms


def main(argv=None) -> int:
    args, arms = _arguments(argv)
    game = args.game.resolve()
    slug = re.sub(r"[^a-z0-9]+", "-", game.name.lower()).strip("-")
    out = (args.out or ROOT / "viwo-data" / "deep-pass" / slug).resolve()
    out.mkdir(parents=True, exist_ok=True)
    p, before = Pass(game, out), snapshot(game)
    if args.workspace:  # an extraction made before: only read and edited, never deleted here
        p.ws = args.workspace.resolve()
    print(f"== deep pass {game} ({', '.join(sorted(arms))})", flush=True)
    if "static" in arms:
        static(p)
    if "analysis" in arms:
        analyses(p, args.analysis_timeout)
    if "patching" in arms:
        patching(p, args.exe)
    if args.dynamic:
        dynamic(p, args.exe)
    changed = change_warning(before, snapshot(game), "the deep pass")
    p.steps["game_unchanged"] = {"ok": not changed, "seconds": 0, "error": changed}
    (out / "report.json").write_text(json.dumps(p.steps, indent=1, default=str), encoding="utf-8")
    (out / "report.md").write_text(report_md(p), encoding="utf-8")
    if not args.keep:
        for folder in (out / "ws", out / "copy", out / "patched"):
            shutil.rmtree(folder, ignore_errors=True)
    print(f"report: {out / 'report.md'}")
    return 0 if all(s["ok"] for s in p.steps.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
