"""Human-readable CLI output (`--json` keeps the machine envelope)."""

from __future__ import annotations

from typing import Any


def _bar(value: float, width: int = 20) -> str:
    filled = round(max(0.0, min(1.0, value)) * width)
    return "#" * filled + "." * (width - filled)


def detect(data: dict) -> str:
    rows = sorted(data.items(), key=lambda kv: -kv[1]["confidence"])
    lines = ["ENGINE      CONFIDENCE                  EVIDENCE"]
    for plugin, d in rows:
        evidence = ", ".join(d["evidence"]) or "-"
        lines.append(f"{plugin:<11} {_bar(d['confidence'])} {d['confidence']:.2f}  {evidence}")
    return "\n".join(lines)


def slots(data: dict) -> str:
    lines = ["SLOT                     MAIN                 SPARE"]
    for slot_id, b in sorted(data.get("slots", data.get("bindings", {})).items()):
        main = b["main"] or "-- unbound --"
        flag = " (promoted)" if b.get("promoted") else ""
        lines.append(f"{slot_id:<24} {main + flag:<20} {b.get('spare') or '-'}")
    deps = data.get("dependencies")
    if deps:
        lines += ["", "DEPENDENCY        STATUS     WHERE / HOW"]
        for d in deps:
            state = "found" if d["available"] else "missing"
            lines.append(f"{d['id']:<17} {state:<10} {d['location'] or d['hint']}")
    return "\n".join(lines)


def info(data: dict) -> str:
    head = [
        f"OS layer : {data['os']}",
        f"Startup  : {data['ini']}",
        f"Plugins  : {', '.join(data['plugins'])}",
        "",
    ]
    tail = ["", "Notes:", *[f"  - {p}" for p in data["problems"]]] if data["problems"] else []
    return "\n".join(head) + "\n" + slots(data) + "\n".join(tail)


def extraction(data: dict) -> str:
    plugins = ", ".join(p["id"] for p in data.get("plugins", [])) or data["extractorType"]
    lines = [
        f"Extracted with: {plugins} ({data.get('mode', 'auto')})",
        f"Archives      : {data['archivesExtracted']}/{data['archivesFound']} unpacked",
        f"Files         : {data['copiedFiles']} collected from {data['scannedFiles']} scanned",
    ]
    groups = ", ".join(f"{k} {v}" for k, v in data["copiedByExt"].items())
    if data.get("carvedFiles"):
        lines.append(
            f"Carved        : {data['carvedFiles']} embedded file(s) from unrecognized data"
        )
    lines.append(f"Groups        : {groups or '-'}")
    if data.get("byBackend"):
        lines.append(
            "Backends      : " + ", ".join(f"{k} x{v}" for k, v in data["byBackend"].items())
        )
    for warning in data["checks"]["warnings"]:
        lines.append(f"WARNING       : {warning}")
    lines.append(f"Run record    : {data.get('runRecord', '-')}")
    return "\n".join(lines)


def unpack(data: dict) -> str:
    backends = ", ".join(f"{k} x{v}" for k, v in data["byBackend"].items())
    lines = [
        f"Unpacked {data['archives']} archive(s), {data['files']} file(s) -> {data['out']}",
        f"Backends: {backends}",
    ]
    return "\n".join(lines + [f"FAILED  : {f}" for f in data["failures"]])


def _mb(size: int) -> str:
    return f"{size / 1e6:,.1f} MB"


def survey(data: dict) -> str:
    lines = []
    for g in data["games"]:
        lines.append(f"\n{g['path']}")
        cover = f"{_bar(g['coverage'])} {g['coverage']:.0%}"
        lines.append(f"  engine   {g['engine']} ({g['confidence']:.2f})  coverage {cover}")
        for cat, c in g["categories"].items():
            lines.append(f"  {cat:<18} {c['files']:>7} files  {_mb(c['bytes']):>12}")
        for u in g["unknown"]:
            kind = "dense: encrypted/compressed" if u["dense"] else "structured: try --deep"
            lines.append(f"  ? {u['file']}  {_mb(u['bytes'])}  ({kind})")
        lines += [f"  missing: {m}" for m in g["missingTools"]]
    covered = sum(1 for g in data["games"] if g["coverage"] >= 0.99)
    return "\n".join(lines + [f"\n{covered}/{len(data['games'])} game(s) fully covered"])


def repack(data: dict) -> str:
    lines = [f"Game    : {data['game']}", f"Edits   : {data['edits']} file(s)"]
    for item in data["plan"]:
        where = item["container"] or "loose files"
        lines.append(f"Plan    : {where} -> {item['slot']} ({len(item['members'])} member(s))")
    for r in data.get("results", []):
        state = "verified" if not r["failed"] else f"FAILED: {', '.join(r['failed'][:5])}"
        lines.append(f"Packed  : {r.get('output') or r['container'] or 'loose files'} {state}")
    lines += [f"Skipped : {s}" for s in data["skipped"]] + [
        f"Warning : {w}" for w in data["warnings"]
    ]
    if "verified" in data:
        lines.append(
            f"Result  : {data['target']} ({'verified' if data['verified'] else 'NOT verified'})"
        )
    return "\n".join(lines)


def sanitize(data: dict) -> str:
    if "restored" in data:
        return f"Restored {data['restored']} file(s)"
    lines = [f"{f['action']:<7} {f['path']}  ({f['message']})" for f in data["findings"]]
    lines.append(
        f"{len(data['findings'])} finding(s) in {data['scanned']} file(s), plan {data['planId']}"
    )
    if "applied" in data:
        done = data["applied"]
        lines.append(f"Applied {done['applied']} action(s); undo with --undo {done['undoToken']}")
    return "\n".join(lines)


def error(err: dict) -> str:
    if err["code"] == "needs_decision":
        err = {**err, "hint": "re-run with --on-existing new | replace | cancel"}
    hint = f"\n  hint: {err['hint']}" if err.get("hint") else ""
    return f"viwo: {err['code']}: {err['message']}{hint}"


WELCOME = """ViWo // Vidya Wormhole - game asset extraction, local only.

  viwo serve                         open the web UI in your browser
  viwo survey <games folder>         what ViWo can pull from each game (read-only)
  viwo extract <game> --workspace W  extract one game
  viwo slots                         which optional tools are installed

Run `viwo -h` for every command, `viwo <command> -h` for its options."""

FORMATTERS: dict[str, Any] = {
    "detect": detect,
    "survey": survey,
    "repack": repack,
    "sanitize": sanitize,
    "config": lambda d: (
        f"Wrote {len(d['written'])} distro file(s) to {d['folder']}"
        if "written" in d
        else "OK: " + ", ".join(d["checked"])
    ),
    "capture": lambda d: (
        f"Captured {d['gathered']} file(s) with {d['backend']}; "
        f"{d['newVsStatic']} not found by static extraction"
    ),
    "slots": slots,
    "info": info,
    "extract": extraction,
    "replay": extraction,
    "unpack": unpack,
}
