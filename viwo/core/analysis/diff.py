"""A3 version diff (doc 16.2b, update resilience): two Ghidra exports of the same binary from
two game versions, function by function. Named functions pair by name; unnamed ones
(`FUN_<address>`) pair by their instruction fingerprint when it is unique on both sides, which
survives relocation; a name seen twice (overloads) pairs by fingerprint too. Each pair is
`same` or `changed`; the rest is `added` or `removed`.
BinDiff has no pinnable release, so this is ViWo's own, on the data the export already writes."""

import json
from collections import Counter
from pathlib import Path

from viwo.contracts.errors import ViwoError

UNNAMED = ("FUN_", "thunk_FUN_", "LAB_", "SUB_")


def load(folder: Path) -> list[dict]:
    """functions.csv rows (address, name, size, fingerprint); names may contain commas."""
    path = Path(folder) / "functions.csv"
    if not path.is_file():
        raise ViwoError("not_found", f"no functions.csv in {folder}", hint="run the analysis first")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        address, _, rest = line.partition(",")
        parts = rest.rsplit(",", 2)
        if len(parts) == 2:  # exports older than 1.4.5 carry no fingerprint
            parts.append("")
        name, size, print_ = parts
        rows.append({"address": address, "name": name, "size": size, "fingerprint": print_})
    return rows


def _pair_by_fingerprint(old: list[dict], new: list[dict]) -> list[tuple[dict, dict]]:
    count_old = Counter(f["fingerprint"] for f in old if f["fingerprint"])
    count_new = Counter(f["fingerprint"] for f in new if f["fingerprint"])
    unique_new = {f["fingerprint"]: f for f in new if count_new[f["fingerprint"]] == 1}
    return [
        (f, unique_new[f["fingerprint"]])
        for f in old
        if f["fingerprint"] and count_old[f["fingerprint"]] == 1 and f["fingerprint"] in unique_new
    ]


def diff(old_dir: Path, new_dir: Path) -> dict:
    old, new = load(old_dir), load(new_dir)
    once_old = Counter(f["name"] for f in old)
    once_new = Counter(f["name"] for f in new)
    named_new = {
        f["name"]: f for f in new if not f["name"].startswith(UNNAMED) and once_new[f["name"]] == 1
    }
    pairs = [
        (f, named_new[f["name"]])
        for f in old
        if f["name"] in named_new and once_old[f["name"]] == 1
    ]
    taken_old = {id(a) for a, _ in pairs}
    taken_new = {id(b) for _, b in pairs}
    rest_old = [f for f in old if id(f) not in taken_old]
    rest_new = [f for f in new if id(f) not in taken_new]
    pairs += _pair_by_fingerprint(rest_old, rest_new)
    taken_old |= {id(a) for a, _ in pairs}
    taken_new |= {id(b) for _, b in pairs}
    rows = [
        {"status": _status(a, b), "old": a["address"], "new": b["address"], "name": b["name"]}
        for a, b in pairs
    ]
    rows += [
        {"status": "removed", "old": f["address"], "new": "", "name": f["name"]}
        for f in old
        if id(f) not in taken_old
    ]
    rows += [
        {"status": "added", "old": "", "new": f["address"], "name": f["name"]}
        for f in new
        if id(f) not in taken_new
    ]
    summary = Counter(r["status"] for r in rows)
    return {"old": str(old_dir), "new": str(new_dir), "summary": dict(summary), "functions": rows}


def _status(a: dict, b: dict) -> str:
    if a["fingerprint"] and b["fingerprint"]:
        return "same" if a["fingerprint"] == b["fingerprint"] else "changed"
    return "same" if a["size"] == b["size"] else "changed"  # exports without fingerprints


def write(report: dict, out: Path) -> Path:
    """diff.json (everything) and diff.txt (one line per function that is not `same`)."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "diff.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    lines = [f"{k}: {v}" for k, v in sorted(report["summary"].items())]
    lines += [
        f"{r['status']:8} {r['old'] or '-':>12} -> {r['new'] or '-':<12} {r['name']}"
        for r in report["functions"]
        if r["status"] != "same"
    ]
    (out / "diff.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
