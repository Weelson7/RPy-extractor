"""Coverage floors (contract doc 17.5), checked against a `coverage json` report.

Usage: python tools/coverage_check.py coverage.json
Floors are per layer, on line coverage of the L0-L4 suite (fakes and synthetic fixtures; the
L5 real-tool and L6 browser tests add nothing the floors count on). Floors only move up: raise
one here together with the test that earned it. Exit 1 when a layer is below its floor.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FLOORS = {  # doc 17.5 ratchet (measured 2026-11-03 on Windows, 1.1.x): see the doc for the plan
    "viwo/contracts": 90,
    "viwo/core": 86,
    "viwo/plugins": 80,
    "viwo/os": 60,
    "viwo": 75,
}


def percent(files: dict, prefix: str) -> float | None:
    covered = total = 0
    for name, data in files.items():
        rel = name.replace("\\", "/")
        rel = rel[rel.find("viwo/") :] if "viwo/" in rel else rel
        if rel == prefix or rel.startswith(prefix.rstrip("/") + "/"):
            covered += data["summary"]["covered_lines"]
            total += data["summary"]["num_statements"]
    return 100.0 * covered / total if total else None


def check(report: Path) -> int:
    files = json.loads(report.read_text(encoding="utf-8"))["files"]
    failures = 0
    for prefix, floor in FLOORS.items():
        value = percent(files, prefix)
        state = "n/a" if value is None else f"{value:5.1f}%"
        below = value is not None and value < floor
        failures += below
        print(f"{'BELOW' if below else 'ok   '} {state} >= {floor}%  {prefix}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(check(Path(sys.argv[1] if len(sys.argv) > 1 else "coverage.json")))
