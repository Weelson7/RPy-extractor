"""Integration run over Test-games/: detect, survey, extract, repack plan and sanitize plan for
every installed game (sqc/games.md), with a report and a game-folder integrity check.

Usage: python tools/integration_games.py [--games Test-games] [--out DIR] [--deep] [--skip-extract]
Every game folder is read-only: it is hashed before and after. Exit 1 when any step failed or a
game folder changed. Writes <out>/report.json and <out>/report.md.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
Runner = Callable[[list[str]], tuple[int, dict | None, str]]


def viwo(args: list[str]) -> tuple[int, dict | None, str]:
    """`viwo --json <args>` through this interpreter: (exit code, envelope, stderr tail)."""
    proc = subprocess.run(
        [sys.executable, "-m", "viwo.cli", "--json", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, _envelope(proc.stdout), proc.stderr[-2000:]


def viwo_inprocess(args: list[str]) -> tuple[int, dict | None, str]:
    """The same contract without a subprocess (tests)."""
    from viwo.cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(["--json", *args])
    return code, _envelope(out.getvalue()), err.getvalue()[-2000:]


def _envelope(stdout: str) -> dict | None:
    try:
        parsed = json.loads(stdout or "null")
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def tree_hashes(folder: Path) -> dict[str, str]:
    """Relative path -> sha256 of every file (streamed: game files can be large)."""
    out: dict[str, str] = {}
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
        except OSError as exc:  # a file the OS refuses to open (quarantined, locked) still counts
            out[path.relative_to(folder).as_posix()] = f"unreadable:{exc.errno}"
            continue
        out[path.relative_to(folder).as_posix()] = digest.hexdigest()
    return out


def game_folders(games: Path) -> list[Path]:
    """Every direct subfolder of Test-games/ that holds at least one file."""
    if not games.is_dir():
        return []
    return sorted(
        p for p in games.iterdir() if p.is_dir() and any(f.is_file() for f in p.rglob("*"))
    )


def step(record: dict, name: str, args: list[str], runner: Runner) -> dict | None:
    """Run one CLI step, record exit code, duration and error; return the envelope data."""
    started = time.monotonic()
    code, envelope, stderr = runner(args)
    ok = code == 0 and bool(envelope and envelope.get("ok"))
    error = ""
    if not ok:
        err = (envelope or {}).get("error") or {}
        error = err.get("message") if isinstance(err, dict) else str(err or "")
        error = error or (stderr.strip().splitlines() or ["no output"])[-1]
    record["steps"][name] = {
        "exit": code,
        "ok": ok,
        "seconds": round(time.monotonic() - started, 1),
        "error": error,
    }
    data = (envelope or {}).get("data")
    return data if isinstance(data, (dict, list)) else None


def _extract_summary(data: dict) -> dict:
    checks = data.get("checks") or {}
    return {
        "plugins": [p.get("id") for p in data.get("plugins", [])],
        "backends": {p.get("id"): p.get("backend") for p in data.get("plugins", [])},
        "copied": data.get("copiedFiles", 0),
        "byExt": data.get("copiedByExt", {}),
        "archivesFound": data.get("archivesFound", 0),
        "archivesExtracted": data.get("archivesExtracted", 0),
        "carved": data.get("carvedFiles", 0),
        "warnings": list(checks.get("warnings", [])),
        "workspace": data.get("workspace", ""),
    }


def integrity(record: dict, game: Path, before: dict[str, str]) -> bool:
    """The game folder must be byte-identical after the run."""
    after = tree_hashes(game)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    record["gameUnchanged"] = not changed
    record["changedFiles"] = changed[:20]
    return not changed


FLAGS_FILE = ROOT / "sqc" / "ctf.json"


def load_flags(path: Path = FLAGS_FILE) -> dict[str, list[dict]]:
    """slug -> CTF flags (sqc/17-ctf.md); the `_comment` key is documentation."""
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {k: v.get("flags", []) for k, v in data.items() if not k.startswith("_")}


def _count(ws: Path, pattern: str) -> int:
    inner = pattern.removeprefix("**/")
    files = ws.rglob(inner) if pattern.startswith("**/") else ws.glob(pattern)
    return sum(1 for p in files if p.is_file())


def check_flags(record: dict, ws: Path | None, flags: list[dict]) -> None:
    """A glob flag needs `min` files under the workspace; a warning flag needs the text in
    the run's warnings. Without an extraction, glob flags are left undecided (ok = None)."""
    out = []
    for flag in flags:
        if "warning" in flag:
            ok = any(flag["warning"] in w for w in record["warnings"])
            out.append({**flag, "ok": ok, "found": int(ok)})
        elif ws is None or not ws.is_dir():
            out.append({**flag, "ok": None, "found": 0})
        else:
            found = _count(ws, flag["glob"])
            out.append({**flag, "ok": found >= int(flag.get("min", 1)), "found": found})
    record["flags"] = out


def run_game(
    game: Path, out: Path, runner: Runner = viwo, deep=False, extract=True, flags=()
) -> dict:
    """detect -> survey -> extract -> repack plan -> sanitize plan, then the integrity check."""
    record: dict = {"game": game.name, "path": str(game), "steps": {}, "warnings": []}
    target = out / game.name
    target.mkdir(parents=True, exist_ok=True)
    before = tree_hashes(game)
    detect = step(record, "detect", ["detect", str(game)], runner) or {}
    record["detection"] = {
        pid: round(float(d.get("confidence", 0)), 2)
        for pid, d in detect.items()
        if isinstance(d, dict)
    }
    survey = step(record, "survey", ["survey", str(game), *(["--deep"] if deep else [])], runner)
    if survey is not None:
        (target / "survey.json").write_text(json.dumps(survey, indent=1), encoding="utf-8")
    if extract:
        ws = target / "ws"
        args = ["extract", str(game), "--workspace", str(ws), "--on-existing", "replace"]
        data = step(record, "extract", args, runner)
        if data:
            record["extract"] = _extract_summary(data)
            record["warnings"] += record["extract"]["warnings"]
        if ws.is_dir():
            step(record, "repack_plan", ["repack", str(ws), "--plan"], runner)
            step(record, "sanitize_plan", ["sanitize", str(ws)], runner)
    check_flags(record, target / "ws" if extract else None, list(flags))
    unchanged = integrity(record, game, before)
    steps_ok = all(s["ok"] for s in record["steps"].values())
    flags_ok = all(f["ok"] is not False for f in record["flags"])
    record["ok"] = unchanged and steps_ok and flags_ok
    return record


def exit_code(records: list[dict]) -> int:
    return 0 if records and all(r["ok"] for r in records) else 1


def report_md(records: list[dict]) -> str:
    """One table row per game, then a totals line."""
    head = (
        "| Game | Detected | Plugins | Copied | Archives | Warnings | Unchanged | Flags | Steps "
        "| Result |"
    )
    lines = ["# Integration run", "", head, "|---|---|---|---|---|---|---|---|---|---|"]
    for r in records:
        top = max(r.get("detection", {}).items(), key=lambda kv: kv[1], default=("none", 0))
        ex = r.get("extract") or {}
        steps = ", ".join(f"{k}:{'ok' if v['ok'] else 'FAIL'}" for k, v in r["steps"].items())
        lines.append(
            f"| {r['game']} | {top[0]} {top[1]:.0%} | {', '.join(ex.get('plugins', [])) or '-'} | "
            f"{ex.get('copied', '-')} | "
            f"{ex.get('archivesExtracted', '-')}/{ex.get('archivesFound', '-')} | "
            f"{len(r['warnings'])} | {'yes' if r.get('gameUnchanged') else 'NO'} | "
            f"{_flags_cell(r)} | {steps} | {'PASS' if r['ok'] else 'FAIL'} |"
        )
    passed = sum(1 for r in records if r["ok"])
    lines += ["", f"Total: {passed}/{len(records)} games passed; exit code {exit_code(records)}."]
    for r in records:
        for w in r["warnings"][:5]:
            lines.append(f"- {r['game']}: {w}")
        for f in r.get("flags", []):
            if f["ok"] is False:
                lines.append(f"- {r['game']}: FLAG FAILED: {f['name']} (found {f['found']})")
    return "\n".join(lines) + "\n"


def _flags_cell(r: dict) -> str:
    flags = r.get("flags", [])
    decided = [f for f in flags if f["ok"] is not None]
    if not flags:
        return "-"
    if not decided:
        return f"0/{len(flags)} n/a"
    return f"{sum(1 for f in decided if f['ok'])}/{len(flags)}"


def write_report(records: list[dict], out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(records, indent=1), encoding="utf-8")
    (out / "report.md").write_text(report_md(records), encoding="utf-8")
    return out / "report.md"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--games", type=Path, default=ROOT / "Test-games")
    ap.add_argument("--out", type=Path, default=ROOT / "viwo-data" / "integration")
    ap.add_argument("--deep", action="store_true", help="survey with the carver on unknown blobs")
    ap.add_argument("--skip-extract", action="store_true", help="detect and survey only")
    ap.add_argument("--only", default="", help="comma-separated slugs (default: every folder)")
    args = ap.parse_args(argv)
    folders = game_folders(args.games)
    flags = load_flags()
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        folders = [f for f in folders if f.name in wanted]
    if not folders:
        print(f"no games under {args.games}: install some (sqc/games.md)")
        return 1
    records = []
    for game in folders:
        print(f"== {game.name}", flush=True)
        extract = not args.skip_extract
        records.append(run_game(game, args.out, viwo, args.deep, extract, flags.get(game.name, ())))
        print("   " + ("PASS" if records[-1]["ok"] else "FAIL"), flush=True)
    print(write_report(records, args.out).read_text(encoding="utf-8"))
    return exit_code(records)


if __name__ == "__main__":
    sys.exit(main())
