"""Linux thread sampling for profile.sample: the modules from /proc/<pid>/maps, the samples from
perf (`perf record -p`, then `perf script -F tid,ip`). perf needs perf_event_paranoid <= 1 or
CAP_PERFMON; without it the error says so (nothing on the system is changed)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def modules_of(pid: int) -> list[tuple[int, int, str]]:
    """(load base, span, path) per mapped file."""
    spans: dict[str, list[int]] = {}
    for line in Path(f"/proc/{pid}/maps").read_text().splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) == 6 and parts[5].startswith("/"):
            start, end = (int(x, 16) for x in parts[0].split("-"))
            base = start - int(parts[2], 16)
            low, high = spans.setdefault(parts[5], [base, end])
            spans[parts[5]] = [min(low, base), max(high, end)]
    return [(low, high - low, path) for path, (low, high) in spans.items()]


def parse(script: str) -> list[tuple[int, int]]:
    """`perf script -F tid,ip` lines: '<tid> <ip hex>'."""
    out = []
    for line in script.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            out.append((int(parts[0]), int(parts[1], 16)))
    return out


def sample_threads(pid: int, seconds: float, cancel=None) -> tuple[list, list]:
    perf = shutil.which("perf")
    if perf is None:
        raise OSError(2, "perf is not installed (the linux-tools package of this kernel)")
    modules = modules_of(pid)
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "perf.data"
        record = [perf, "record", "-F", "999", "-p", str(pid), "-o", str(data)]
        done = subprocess.run(
            [*record, "--", "sleep", str(seconds)], capture_output=True, text=True
        )
        if done.returncode or not data.is_file():
            why = done.stderr.strip()[-300:]
            raise OSError(1, f"perf record failed (perf_event_paranoid?): {why}")
        script = [perf, "script", "-i", str(data), "-F", "tid,ip"]
        listed = subprocess.run(script, capture_output=True, text=True, timeout=300)
    return parse(listed.stdout), modules
