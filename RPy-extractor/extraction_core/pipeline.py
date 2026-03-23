"""Top-level extraction pipeline orchestration."""
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from models import RPA_TEMP_PREFIX, SKIP_DIRS

from .archive import list_rpa_files, extract_archives
from .file_ops import safe_suffix, ext_folder_name, move_one, walk_files, collect_source_roots
from .runtime import log_append


def logic_check_summary(
    archives_found: int,
    archives_extracted: int,
    scanned_files: int,
    copied_files: int,
    copied_by_ext: dict[str, int],
    output_dir: Path,
) -> list[str]:
    """Generate logic check warnings."""
    warnings: list[str] = []
    copied_sum = sum(copied_by_ext.values())

    if archives_found > 0 and archives_extracted == 0:
        warnings.append("Archives were discovered but none extracted successfully.")
    if scanned_files == 0:
        warnings.append("No files were scanned from source roots.")
    if copied_files == 0:
        warnings.append("No files were copied into the output folder.")
    if copied_sum != copied_files:
        warnings.append(f"copiedByExt sum ({copied_sum}) does not match copiedFiles ({copied_files}).")
    if not output_dir.exists():
        warnings.append("Output directory does not exist after extraction.")
    else:
        real_files = sum(1 for p in output_dir.rglob("*") if p.is_file())
        if real_files < copied_files:
            warnings.append(f"Output files on disk ({real_files}) are fewer than copiedFiles ({copied_files}).")

    return warnings


def extract_assets(
    game_root: Path,
    output_dir: Path,
    selected_exts: set[str] | None,
    temp_root: Path,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Extract and organize assets from game with comprehensive logging."""
    if not game_root.exists() or not game_root.is_dir():
        raise ValueError(f"Game path does not exist or is not a folder: {game_root}")

    if progress:
        progress(f"[PHASE 0] Preparing output folder: {output_dir}")
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    has_rpa_archives = len(list_rpa_files(game_root)) > 0
    if has_rpa_archives:
        from startup import ensure_unrpa
        if not ensure_unrpa():
            raise RuntimeError("Could not install or run 'unrpa'.")

    if progress:
        progress(f"[PHASE 1] Extracting archives from: {game_root}")

    staging = Path(tempfile.mkdtemp(prefix=RPA_TEMP_PREFIX, dir=str(temp_root)))

    try:
        extracted_count, found_count, logs = extract_archives(game_root, staging, progress)

        if progress:
            progress("[PHASE 2] Scanning files by extension")

        moved_by_ext: dict[str, int] = {}
        files_by_ext: dict[str, int] = {}
        skipped_by_ext: dict[str, int] = {}
        total_scanned = 0

        for source_root in collect_source_roots(game_root, staging):
            if progress:
                progress(f"  Scanning source: {source_root.name}")

            for src in walk_files(source_root, SKIP_DIRS):
                total_scanned += 1
                if progress and total_scanned % 500 == 0:
                    progress(f"  Progress: {total_scanned} files scanned so far...")

                ext = safe_suffix(src)
                folder = ext_folder_name(ext)
                files_by_ext[folder] = files_by_ext.get(folder, 0) + 1

                if selected_exts is not None and ext not in selected_exts:
                    skipped_by_ext[folder] = skipped_by_ext.get(folder, 0) + 1
                    continue

                move_one(src, output_dir, moved_by_ext, selected_exts)

        log_append(logs, "FILE DISCOVERY", progress)
        log_append(logs, f"Total files scanned: {total_scanned}", progress)
        for ext in sorted(files_by_ext.keys()):
            log_append(logs, f"  .{ext}: {files_by_ext[ext]} file(s) discovered", progress)

        if skipped_by_ext:
            log_append(logs, "FILTERED OUT (not selected)", progress)
            for ext in sorted(skipped_by_ext.keys()):
                log_append(logs, f"  .{ext}: {skipped_by_ext[ext]} file(s) skipped", progress)

        log_append(logs, "FILES MOVED TO ASSETS", progress)
        log_append(logs, f"Total files moved: {sum(moved_by_ext.values())}", progress)
        for ext in sorted(moved_by_ext.keys()):
            log_append(logs, f"  .{ext}: {moved_by_ext[ext]} file(s) moved", progress)

        if progress:
            progress("[PHASE 3] Running validation checks")

        checks = logic_check_summary(
            archives_found=found_count,
            archives_extracted=extracted_count,
            scanned_files=total_scanned,
            copied_files=sum(moved_by_ext.values()),
            copied_by_ext=moved_by_ext,
            output_dir=output_dir,
        )

        return {
            "success": True,
            "archivesFound": found_count,
            "archivesExtracted": extracted_count,
            "scannedFiles": total_scanned,
            "copiedFiles": sum(moved_by_ext.values()),
            "copiedByExt": dict(sorted(moved_by_ext.items())),
            "checks": {
                "ok": len(checks) == 0,
                "warnings": checks,
            },
            "logs": logs,
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)
