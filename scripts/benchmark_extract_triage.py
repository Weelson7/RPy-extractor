"""Benchmark extraction and triage throughput on local sample datasets.

Usage:
  python scripts/benchmark_extract_triage.py --datasets samples/datasets --iterations 3
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path


def _configure_runtime_imports(repo_root: Path) -> None:
    runtime_root = repo_root / "RPy-extractor"
    if str(runtime_root) not in sys.path:
        sys.path.insert(0, str(runtime_root))


def _run_single_iteration(dataset: Path, workspace: Path) -> dict[str, float | int]:
    from extraction import extract_assets, walk_files  # type: ignore[import-not-found]
    from models import SKIP_DIRS  # type: ignore[import-not-found]
    from sorting import list_kept_files, move_to_trash, restore_from_trash  # type: ignore[import-not-found]

    output_dir = workspace / "assets"
    temp_root = workspace / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)

    extract_start = time.perf_counter()
    result = extract_assets(
        game_root=dataset,
        output_dir=output_dir,
        selected_exts=None,
        temp_root=temp_root,
    )
    extract_secs = max(time.perf_counter() - extract_start, 1e-9)

    copied_files = int(result.get("copiedFiles", 0))

    index_start = time.perf_counter()
    indexed_files = 0
    for _path in walk_files(output_dir, SKIP_DIRS):
        indexed_files += 1
    index_secs = max(time.perf_counter() - index_start, 1e-9)

    triage_start = time.perf_counter()
    triage_ops = 0
    kept_by_ext = list_kept_files(output_dir)
    candidate_exts = sorted(kept_by_ext.keys())[:5]
    for ext in candidate_exts:
        ok, _ = move_to_trash(output_dir, ext)
        if ok:
            triage_ops += 1
            restored, _ = restore_from_trash(output_dir, ext)
            if restored:
                triage_ops += 1
    triage_secs = max(time.perf_counter() - triage_start, 1e-9)

    return {
        "copiedFiles": copied_files,
        "indexedFiles": indexed_files,
        "triageOps": triage_ops,
        "extractSeconds": round(extract_secs, 6),
        "indexSeconds": round(index_secs, 6),
        "triageSeconds": round(triage_secs, 6),
        "extractFilesPerSec": round(copied_files / extract_secs, 2),
        "indexFilesPerSec": round(indexed_files / index_secs, 2),
        "triageOpsPerSec": round(triage_ops / triage_secs, 2),
    }


def _benchmark_dataset(dataset: Path, iterations: int) -> dict[str, object]:
    runs: list[dict[str, float | int]] = []

    for i in range(iterations):
        with tempfile.TemporaryDirectory(prefix=f"rpy_bench_{dataset.name}_{i}_") as td:
            run_workspace = Path(td)
            run_result = _run_single_iteration(dataset, run_workspace)
            runs.append(run_result)

    extract_rates = [float(run["extractFilesPerSec"]) for run in runs]
    triage_rates = [float(run["triageOpsPerSec"]) for run in runs]
    index_rates = [float(run["indexFilesPerSec"]) for run in runs]

    return {
        "dataset": dataset.name,
        "path": str(dataset),
        "iterations": iterations,
        "runs": runs,
        "summary": {
            "extractFilesPerSecAvg": round(statistics.fmean(extract_rates), 2),
            "indexFilesPerSecAvg": round(statistics.fmean(index_rates), 2),
            "triageOpsPerSecAvg": round(statistics.fmean(triage_rates), 2),
            "extractFilesPerSecMin": round(min(extract_rates), 2),
            "extractFilesPerSecMax": round(max(extract_rates), 2),
            "triageOpsPerSecMin": round(min(triage_rates), 2),
            "triageOpsPerSecMax": round(max(triage_rates), 2),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark extraction and triage throughput.")
    parser.add_argument("--datasets", default="samples/datasets", help="Folder containing dataset subfolders")
    parser.add_argument("--iterations", type=int, default=3, help="Number of runs per dataset")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    datasets_root = (repo_root / args.datasets).resolve() if not Path(args.datasets).is_absolute() else Path(args.datasets).resolve()

    if not datasets_root.exists() or not datasets_root.is_dir():
        print(f"[ERROR] Dataset folder not found: {datasets_root}")
        return 1

    _configure_runtime_imports(repo_root)

    datasets = sorted(path for path in datasets_root.iterdir() if path.is_dir())
    if not datasets:
        print(f"[ERROR] No datasets found under: {datasets_root}")
        return 1

    print(f"[BENCH] Datasets root: {datasets_root}")
    print(f"[BENCH] Iterations per dataset: {args.iterations}")

    all_results: list[dict[str, object]] = []
    overall_start = time.perf_counter()

    for dataset in datasets:
        print(f"[BENCH] Running dataset: {dataset.name}")
        bench = _benchmark_dataset(dataset, max(1, args.iterations))
        all_results.append(bench)
        summary = bench.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}
        print(
            "[BENCH] "
            f"extract avg={summary.get('extractFilesPerSecAvg', 'n/a')} files/s, "
            f"index avg={summary.get('indexFilesPerSecAvg', 'n/a')} files/s, "
            f"triage avg={summary.get('triageOpsPerSecAvg', 'n/a')} ops/s"
        )

    total_secs = round(time.perf_counter() - overall_start, 3)
    output = {
        "datasetsRoot": str(datasets_root),
        "iterations": max(1, args.iterations),
        "elapsedSeconds": total_secs,
        "results": all_results,
    }

    print("[BENCH] Complete")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
