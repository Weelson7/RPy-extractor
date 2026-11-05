"""Deep pass arms: every analysis target run to completion; a real edit per container type
repacked into one patched copy and read back, an AOB patch set and a mod into that copy; the
dynamic arm on the running game (capture, agent, dump, trace, sound)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from deep_checks import provenance

from viwo.contracts import workspace as ws

ANALYSIS = ["--features", "extraction,analysis"]
DYNAMIC = ["--features", "extraction,analysis,capture"]
NEEDS_INPUT = {"analysis.emulate", "analysis.symbolic"}
DOS = b"cannot be run in DOS mode"  # in every PE stub: a harmless, universal AOB target


def analyses(p, timeout: int) -> None:
    listed = p.run("analysis_list", [*ANALYSIS, "analyze", str(p.game), "--list"])
    targets = (listed or {}).get("targets", [])
    p.steps["analysis_list"]["targets"] = [t.get("key") for t in targets]
    for target in targets:
        key = str(target.get("key"))
        args = [*ANALYSIS, "analyze", str(p.game), "--workspace", str(p.ws), "--target", key]
        args += ["--timeout", str(timeout)]
        for slot in ["", *[x.get("slot", "") for x in target.get("extras", [])]]:
            name = f"analyze:{key}" + (f":{slot.rsplit('.', 1)[-1]}" if slot else "")
            if slot in NEEDS_INPUT:  # a routine's address is the user's choice, not the pass's
                p.steps[name] = {"ok": True, "seconds": 0, "skipped": "needs a routine address"}
                continue
            data = p.run(name, args + (["--slot", slot] if slot else []))
            if data is not None:
                p.steps[name]["artifacts"] = len(data.get("artifacts", []))
                p.steps[name]["backend"] = data.get("backend")


def main_exe(game: Path, exe: Path | None) -> Path | None:
    if exe is not None:
        return exe.resolve()
    exes = ws.files(game, "*.exe")
    return max(exes, key=lambda e: e.stat().st_size) if exes else None


def patching(p, exe: Path | None) -> None:
    copy = p.out / "patched"
    need = sum(f.stat().st_size for f in ws.files(p.game)) * 1.1
    free = shutil.disk_usage(p.out).free
    if need > free:
        why = f"needs {need / 1e9:.0f} GB for a patched copy, {free / 1e9:.0f} GB free: skipped"
        p.steps["patched_copy"] = {"ok": False, "seconds": 0, "error": why}
        return
    edits = _edit(p)
    p.steps["edits"] = {"ok": bool(edits), "seconds": 0, "data": edits}
    if edits:
        plan = p.run("repack_plan", ["repack", str(p.ws), "--plan"]) or {}
        data = p.run("repack", ["repack", str(p.ws), "--out", str(copy)])
        if data is not None:
            step = p.steps["repack"]
            step["verified"], step["results"] = data.get("verified"), data.get("results", [])[:20]
            step["ok"] = bool(data.get("verified")) and bool(step["results"])
            if not step["results"]:  # nothing written back: the plan says why
                step["error"] = "; ".join(plan.get("warnings", []) + plan.get("skipped", []))[:600]
    target = main_exe(p.game, exe)
    if target is None:
        p.steps["patch_set"] = {"ok": False, "seconds": 0, "error": "no executable to patch"}
        return
    _patch_and_mod(p, target, copy)


def _edit(p) -> dict:
    """One member per container type: an image gets a red square, a text gets a line, any other
    file one changed byte (verification compares bytes; the launch check wants the image)."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in provenance(p.ws):
        if row.get("kind") in ("member", "exported") and row.get("container"):
            by_type[Path(row["container"]).suffix.lower()].append(row)
    done = {}
    for suffix, rows in sorted(by_type.items()):
        row = _pick(p.ws, rows)
        if row is not None:
            done[suffix or "(none)"] = {"file": row["path"], "how": _change(p.ws / row["path"])}
    return done


def _pick(workspace: Path, rows: list[dict]) -> dict | None:
    rank = {"png": 0, "txt": 1, "json": 1, "xml": 1, "lua": 1, "rpy": 1}
    rows = [r for r in rows if (workspace / r["path"]).is_file()]
    rows.sort(key=lambda r: (rank.get(Path(r["path"]).suffix.lower()[1:], 2), r["path"]))
    return rows[0] if rows else None


def _change(path: Path) -> str:
    ext = path.suffix.lower()[1:]
    if ext == "png":
        from PIL import Image, ImageDraw

        with Image.open(path) as img:
            img = img.convert("RGBA")
        ImageDraw.Draw(img).rectangle((0, 0, img.width // 3, img.height // 3), fill="red")
        img.save(path)
        return "red square"
    if ext in ("txt", "json", "xml", "lua", "rpy"):
        with open(path, "ab") as fh:
            fh.write(b"\n" if ext == "json" else b"\n-- viwo deep pass\n")
        return "a line added"
    data = bytearray(path.read_bytes())
    if data:
        data[len(data) // 2] ^= 0xFF
        path.write_bytes(bytes(data))
    return "one byte changed"


def _patch_and_mod(p, exe: Path, copy: Path) -> None:
    patched = DOS.replace(b"DOS", b"D0S")
    patch = {"schema": 1, "title": "deep pass", "patches": [{
        "file": exe.relative_to(p.game).as_posix(), "pattern": DOS.hex(" "), "at": 0,
        "patched": patched.hex(" ")}]}  # fmt: skip
    path = p.out / "deep.patch.json"
    path.write_text(json.dumps(patch), encoding="utf-8")
    p.run("patch_plan", ["patch", str(p.game), str(path), "--plan"])
    p.run("patch_apply", ["patch", str(p.game), str(path), "--out", str(copy)])
    written = (copy / exe.relative_to(p.game)).read_bytes() if copy.is_dir() else b""
    p.steps["patch_apply"]["readBack"] = patched in written
    mod = p.out / "deep-mod.zip"
    p.run("mod_pack", ["mod", "pack", str(p.game), str(mod), "--copy", str(copy)])
    p.run("mod_check", ["mod", "check", str(p.game), str(mod)])
    p.run("mod_apply", ["mod", "apply", str(p.game), str(mod), "--copy", str(copy)])


def dynamic(p, exe: Path | None) -> None:
    exe = main_exe(p.game, exe)
    if exe is None:
        p.steps["dynamic"] = {"ok": False, "seconds": 0, "error": "no executable"}
        return
    base = ["--workspace", str(p.ws)]
    p.run("capture", [*DYNAMIC, "capture", str(p.game), "--exe", str(exe), *base, "--confirm",
                      "--auto", "45"])  # fmt: skip
    p.run("agent", [*DYNAMIC, "agent", str(p.game), "--exe", str(exe), *base, "--timeout", "300"])
    game = subprocess.Popen([str(exe)], cwd=exe.parent)
    try:
        time.sleep(45)  # past the splash screens: the game is loaded
        p.run("dump", [*DYNAMIC, "dump", "--name", exe.name, *base])
        p.run("trace", [*DYNAMIC, "trace", "--name", exe.name, *base, "--seconds", "15"])
        p.run("record", [*DYNAMIC, "record", *base, "--seconds", "15"])
    finally:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/IM", exe.name], capture_output=True)
        game.kill()
