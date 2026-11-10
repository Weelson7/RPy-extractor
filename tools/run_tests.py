"""Run test modules in parallel (tools/version.py): each module is its own `python -m unittest`
process on a pool of workers, 80 % of the machine's logical processors, counted when the run
starts on any OS (VIWO_TEST_WORKERS overrides), the largest first. The modules in SERIAL run
after the pool, one at a time: they bind a fixed port, drive a browser, or time child
processes, and a loaded machine would make them flaky. A failing
module's whole output is printed; the exit code is 1 when any module failed.
Usage: python tools/run_tests.py [module ...]   (no module: every tests/test_*.py)"""

import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERIAL = {  # why each one runs alone
    "tests.test_ui_smoke": "a headless browser with time limits",
    "tests.test_server": "a fixed port (8123)",
    "tests.test_runtime_agents": "a fake game stopped after seconds",
    "tests.test_capture": "an unattended capture after 0.2 s",
    "tests.test_profile": "samples a process for a set time",
    "tests.test_os_layer": "kills process trees on a timer",
    "tests.test_os_shared": "kills process trees on a timer",
    "tests.test_runtime_tools": "kills a child process",
    "tests.test_thirdparty": "builds the wheel within a 5-minute limit",
}


def modules() -> list[str]:
    return sorted(f"tests.{p.stem}" for p in (ROOT / "tests").glob("test_*.py"))


def size(module: str) -> int:
    path = ROOT / Path(*module.split(".")).with_suffix(".py")
    return path.stat().st_size if path.is_file() else 0


def run(module: str) -> tuple[str, int, str, float]:
    start = time.monotonic()
    done = subprocess.run(
        [sys.executable, "-m", "unittest", module], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )  # fmt: skip
    return module, done.returncode, done.stdout + done.stderr, time.monotonic() - start


def counts(output: str) -> tuple[int, int]:
    ran = re.search(r"^Ran (\d+) tests?", output, re.M)
    skipped = re.search(r"skipped=(\d+)", output)
    return (int(ran.group(1)) if ran else 0), (int(skipped.group(1)) if skipped else 0)


def workers() -> int:
    """80 % of the logical processors this process may use (owner's cap), at least one."""
    if os.environ.get("VIWO_TEST_WORKERS"):
        return max(1, int(os.environ["VIWO_TEST_WORKERS"]))
    count = getattr(os, "process_cpu_count", os.cpu_count)() or 1  # 3.13+: the affinity's
    return max(1, int(count * 0.8))


def main(argv: list[str]) -> int:
    picked = argv or modules()
    workers_ = workers()
    pooled = sorted((m for m in picked if m not in SERIAL), key=size, reverse=True)
    start, results = time.monotonic(), []
    with ThreadPoolExecutor(workers_) as pool:
        results += pool.map(run, pooled)
    results += [run(m) for m in picked if m in SERIAL]
    failed = [r for r in results if r[1]]
    for module, _, output, _ in failed:
        print(f"\n===== {module} =====\n{output}", flush=True)
    ran = sum(counts(r[2])[0] for r in results)
    skipped = sum(counts(r[2])[1] for r in results)
    took = time.monotonic() - start
    verdict = f"FAILED: {', '.join(r[0] for r in failed)}" if failed else "OK"
    print(f"Ran {ran} tests in {len(results)} modules in {took:.0f}s on {workers_} workers "
          f"(skipped={skipped}); {verdict}")  # fmt: skip
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
