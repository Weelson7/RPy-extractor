"""T1 patch sets (doc 16.2b, patching arm): byte patches written into a marked patched copy of the
game, never into the game. A patch set is JSON (`*.patch.json`):

    {"schema": 1, "title": "...", "patches": [
      {"file": "Game.exe", "offset": "0x1a2b", "original": "74 05", "patched": "EB 05"},
      {"file": "Game.exe", "pattern": "74 ?? 8B 45 FC", "at": 0, "patched": "EB"},
      {"file": "Game.exe", "rva": "0x1010", "asm": "jmp 0x401020; nop"}]}

An offset patch writes only where the original bytes are found; a pattern (AOB, `??` = any byte)
must match exactly once, so it survives game updates that move the code; `rva` addresses a PE
image, and `asm` is assembled at the edit's address (Keystone, a separate process). Bytes that
already read as `patched` are reported `already` (re-applying a set is harmless). Every write is
read back. The set is the user's content: ViWo applies bytes, it does not author them."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

from .patch_tools import around, assemble, pe, rva_to_offset, signature
from .roundtrip import MARKER, prepare_copy
from .steps import tell
from .workspace import write_atomic

HEX = re.compile(r"^([0-9A-Fa-f]{2}|\?\?)$")


def _bytes(text: str, wild: bool = False) -> tuple[bytes, list[bool]]:
    """`74 ?? 8B` -> (bytes, mask); `??` only where wild is allowed."""
    data, mask = bytearray(), []
    for token in str(text).split():
        if not HEX.match(token) or (token == "??" and not wild):
            raise ViwoError("invalid_request", f"bad byte {token!r} in {text!r}")
        data.append(0 if token == "??" else int(token, 16))
        mask.append(token != "??")
    if not data:
        raise ViwoError("invalid_request", "empty byte string in a patch")
    return bytes(data), mask


def load(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ViwoError("invalid_request", f"cannot read the patch set {path}: {exc}") from exc
    if data.get("schema") != 1 or not isinstance(data.get("patches"), list) or not data["patches"]:
        raise ViwoError(
            "invalid_request", "a patch set needs schema 1 and a non-empty patches list"
        )
    return data


def _hits(data: bytes, pattern: bytes, mask: list[bool]) -> list[int]:
    rx = b"".join(re.escape(bytes([b])) if m else b"." for b, m in zip(pattern, mask))
    return [m.start() for m in re.finditer(rx, data, re.DOTALL)]


def _offset(data: bytes, patch: dict) -> int | str:
    """Where the patch goes, or why it cannot. A pattern that the patch itself overwrites is
    also looked for in its patched form, so an applied set is found again (`already`)."""
    try:
        if "rva" in patch:
            return rva_to_offset(data, int(str(patch["rva"]), 0))
        if "pattern" not in patch:
            return int(str(patch["offset"]), 0)
    except (KeyError, ValueError):
        return "give an offset, an rva or a pattern (a number such as 0x1a2b)"
    pattern, mask = _bytes(patch["pattern"], wild=True)
    at = int(patch.get("at", 0))
    new = _bytes(patch["patched"])[0] if "patched" in patch else b""  # asm: no patched form
    hits = _hits(data, pattern, mask)
    if not hits and new:
        after = bytearray(pattern), list(mask)
        for i, b in enumerate(new):
            if 0 <= at + i < len(pattern):
                after[0][at + i], after[1][at + i] = b, True
        hits = _hits(data, bytes(after[0]), after[1])
    if len(hits) != 1:
        return f"pattern matches {len(hits)} times (needs exactly one)"
    return hits[0] + at


def _file(game: Path, patch: dict) -> Path | None:
    path = ws.member_path(game, str(patch.get("file", "")))
    return path if path is not None and path.is_file() else None


def locate(game: Path, patch: dict, host=None) -> dict:
    """One patch checked against a folder: offset, the old and new bytes (an `asm` edit is
    assembled at its address through `host`), their disassembly for a PE, and a status:
    ready, already, mismatch or missing."""
    out = {"file": str(patch.get("file", "")), "status": "missing", "offset": None, "reason": ""}
    path = _file(game, patch)
    if path is None:
        return {**out, "reason": "no such file in the game folder"}
    data = path.read_bytes()
    where = _offset(data, patch)
    if isinstance(where, str):
        return {**out, "status": "mismatch", "reason": where}
    new = (
        assemble(host, patch["asm"], data, where) if "asm" in patch else _bytes(patch["patched"])[0]
    )
    if where < 0 or where + len(new) > len(data):  # never grow or underrun the binary
        reason = f"out of range: {len(new)} byte(s) at {where:#x} in a {len(data):#x}-byte file"
        return {**out, "status": "mismatch", "offset": where, "reason": reason}
    current = data[where : where + len(new)]
    original = _bytes(patch["original"])[0] if "original" in patch else current
    status = "already" if current == new else "ready" if current == original else "mismatch"
    reason = "" if status != "mismatch" else f"found {current.hex(' ')} at {where:#x}"
    found = {
        "status": status,
        "offset": where,
        "reason": reason,
        "old": current.hex(" "),
        "new": new.hex(" "),
    }
    if pe(data):
        found["disasm"] = around(data, where, new)
    return {**out, **found}


def plan(game: Path, patch_set: dict, host=None) -> dict:
    results = [locate(game, p, host) for p in patch_set["patches"]]
    ok = all(r["status"] in ("ready", "already") for r in results)
    return {"title": patch_set.get("title", ""), "game": str(game), "results": results, "ok": ok}


def write(target: Path, patch: dict, result: dict) -> bool:
    """Write the edit, then re-read the whole file: the range holds the new bytes and every
    other byte is what it was (doc 18.8 VERIFY)."""
    where, new = result["offset"], bytes.fromhex(result["new"])
    path = _file(target, patch)
    if path is None:  # the copy step could not copy it (an antivirus hold): this patch fails
        return False
    before = path.read_bytes()
    with open(path, "r+b") as fh:
        fh.seek(where)
        fh.write(new)
    after, end = path.read_bytes(), where + len(new)
    return (
        after[where:end] == new and after[:where] == before[:where] and after[end:] == before[end:]
    )


def export(game: Path, patch_set: dict, report: dict, folder: Path, name: str) -> None:
    """The portable forms (doc 18.8 EXPORT): a byte diff and an AOB patch set whose patterns
    are unique in this version, so the edits resolve again after an update."""
    lines, aob = [], {"schema": 1, "title": f"{patch_set.get('title', name)} (AOB)", "patches": []}
    for patch, r in zip(patch_set["patches"], report["results"]):
        lines.append(f"{r['file']} {r['offset']:#x}: {r['old']} -> {r['new']}")
        path = _file(game, patch)
        if path is None:
            lines.append("  no AOB: the file is not in this folder")
            continue
        try:
            pattern, at = signature(path.read_bytes(), r["offset"])
        except ViwoError as exc:
            lines.append(f"  no AOB: {exc.message}")
            continue
        aob["patches"].append(
            {"file": r["file"], "pattern": pattern, "at": at, "patched": r["new"]}
        )
    (folder / f"{name}.diff.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / f"{name}.aob.patch.json").write_text(json.dumps(aob, indent=1), encoding="utf-8")


def apply(rt, game: Path, set_path: Path, target: Path, say=None) -> dict:
    """Plan against the game; copy it to `target` (or reuse target when it is already a ViWo
    patched copy, so edits and patches stack), write every ready patch, read it back."""
    patch_set = load(set_path)
    reuse = (target / MARKER).is_dir()
    report = plan(target if reuse else game, patch_set, rt.os)  # the folder that gets written
    if not report["ok"]:
        bad = [
            f"{r['file']}: {r['status']} ({r['reason']})"
            for r in report["results"]
            if r["status"] not in ("ready", "already")
        ]
        raise ViwoError("failed", "the patch set does not fit this game: " + "; ".join(bad[:5]))
    report["notCopied"] = prepare_copy(rt, game, target, say, "patch", reuse=True)
    for patch, result in zip(patch_set["patches"], report["results"]):
        if result["status"] == "ready":
            result["written"] = write(target, patch, result)
    report["verified"] = all(r.get("written", True) for r in report["results"])
    name = Path(set_path).name.removesuffix(".json")
    export(game, patch_set, report, target / MARKER, name.removesuffix(".patch"))
    write_atomic(target / MARKER / f"{name}.report.json", json.dumps(report, indent=2))
    shutil.copy2(set_path, target / MARKER / Path(set_path).name)  # the set travels with the copy
    tell(say, f"Patched copy ready: {len(report['results'])} patch(es)", "patch")
    return report
