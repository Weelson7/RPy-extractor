"""Archive extraction and asset collection logic."""
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
import zipfile
from collections import deque
from pathlib import Path
from typing import Callable
from models import (
    DEFAULT_COMMON_EXTS, ARCHIVE_SUFFIXES, PYTHON_ARCHIVE_SUFFIXES,
    SKIP_DIRS, RPA_TEMP_PREFIX, IMAGE_EXTS, AUDIO_EXTS, VIDEO_EXTS
)
from logging_utils import emit_log


def tlog(message: str) -> None:
    """Log with timestamp."""
    emit_log(message)


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run subprocess and capture output."""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def command_exists(name: str) -> bool:
    """Check if command exists."""
    import shutil
    return shutil.which(name) is not None


def safe_suffix(path: Path) -> str:
    """Get file extension safely."""
    ext = path.suffix.lower().strip()
    if ext:
        return ext
    return ".noext"


def ext_folder_name(ext: str) -> str:
    """Convert extension to folder name."""
    return ext[1:] if ext.startswith(".") else ext


def list_rpa_files(root: Path) -> list[Path]:
    """Find all .rpa files recursively."""
    return sorted(path for path in root.rglob("*.rpa"))


def archive_suffix(path: Path) -> str:
    """Get archive suffix if file is an archive."""
    name = path.name.lower()
    for suffix in sorted(ARCHIVE_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix):
            return suffix
    return ""


def is_archive_file(path: Path) -> bool:
    """Check if file is an archive."""
    return archive_suffix(path) != ""


def list_archive_files(root: Path) -> list[Path]:
    """Find all archive files recursively."""
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and is_archive_file(path):
            files.append(path)
    return sorted(files)


def try_external_archive_extract(archive: Path, output_dir: Path) -> tuple[bool, str]:
    """Extract archive using external tools (7z, unrar)."""
    if archive_suffix(archive) == ".7z":
        last_error = ""
        for tool in ("7z", "7za", "7zr"):
            if not command_exists(tool):
                continue
            code, _, stderr = run([tool, "x", "-y", f"-o{output_dir}", str(archive)])
            if code == 0:
                return True, ""
            last_error = stderr.strip()[:300]
        return False, last_error or "No supported external extractor found (install 7z/unrar)."

    if archive_suffix(archive) == ".rar":
        last_error = ""
        for tool, args in (("unrar", ["x", "-o+", str(archive), str(output_dir)]), ("7z", ["x", "-y", f"-o{output_dir}", str(archive)])):
            if not command_exists(tool):
                continue
            code, _, stderr = run([tool, *args])
            if code == 0:
                return True, ""
            last_error = stderr.strip()[:300]
        return False, last_error or "No supported external extractor found (install 7z/unrar)."

    return False, "No supported external extractor found (install 7z/unrar)."


def try_python_archive_extract(archive: Path, output_dir: Path) -> tuple[bool, str]:
    """Extract archive using Python (zip, tar)."""
    suffix = archive_suffix(archive)
    if suffix not in PYTHON_ARCHIVE_SUFFIXES:
        return False, "Unsupported Python archive type."

    try:
        shutil.unpack_archive(str(archive), str(output_dir))
        return True, ""
    except Exception:
        pass

    try:
        if suffix == ".zip":
            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(output_dir)
            return True, ""
        with tarfile.open(archive, "r:*") as tf:
            tf.extractall(output_dir)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def extract_single_archive(archive: Path, output_dir: Path) -> tuple[bool, str]:
    """Extract single archive file."""
    suffix = archive_suffix(archive)
    if suffix == ".rpa":
        code, _, stderr = run([sys.executable, "-m", "unrpa", "-m", "-p", str(output_dir), str(archive)])
        if code == 0:
            return True, ""
        return False, stderr.strip()[:300]

    ok, err = try_python_archive_extract(archive, output_dir)
    if ok:
        return True, ""

    ok, external_err = try_external_archive_extract(archive, output_dir)
    if ok:
        return True, ""

    final_err = external_err or err or "Unknown extraction error."
    return False, final_err


def log_append(logs: list[str], message: str, progress: Callable[[str], None] | None = None) -> None:
    """Add to log and call progress callback."""
    logs.append(message)
    if progress:
        progress(message)


def extract_archives(game_root: Path, staging_dir: Path, progress: Callable[[str], None] | None = None) -> tuple[int, int, list[str]]:
    """Extract all archives recursively with detailed logging."""
    logs: list[str] = []
    initial_archives = list_archive_files(game_root)
    if not initial_archives:
        log_append(logs, "No archives found in game directory.", progress)
        return 0, 0, logs

    log_append(logs, f"EXTRACTION START: Found {len(initial_archives)} initial archive(s) to process", progress)
    queue = deque(initial_archives)
    seen: set[str] = set()
    extracted_count = 0
    found_count = 0
    total_files_extracted = 0

    while queue:
        archive = queue.popleft()
        try:
            key = str(archive.resolve())
        except Exception:
            key = str(archive)

        if key in seen:
            continue
        seen.add(key)
        found_count += 1

        subdir = staging_dir / f"archive_{found_count:05d}_{uuid.uuid4().hex[:8]}"
        subdir.mkdir(parents=True, exist_ok=True)

        log_append(logs, f"[Archive {found_count}] Extracting: {archive.name}", progress)
        ok, err = extract_single_archive(archive, subdir)
        if not ok:
            log_append(logs, f"[Archive {found_count}] ✗ FAILED: {archive.name} - {err[:150]}", progress)
            continue

        # Count files in this archive's extraction
        files_in_archive = sum(1 for _ in subdir.rglob("*") if _.is_file())
        total_files_extracted += files_in_archive
        log_append(logs, f"[Archive {found_count}] ✓ SUCCESS: {archive.name} ({files_in_archive} files)", progress)
        extracted_count += 1

        # Check for nested archives
        nested = list_archive_files(subdir)
        if nested:
            log_append(logs, f"[Archive {found_count}] Found {len(nested)} nested archive(s) to extract", progress)
            for nested_archive in nested:
                queue.append(nested_archive)

    log_append(logs, f"EXTRACTION COMPLETE: {extracted_count}/{found_count} succeeded ({total_files_extracted} total files)", progress)
    return extracted_count, found_count, logs


def walk_files(root: Path, skip_dirs: set[str]) -> list[Path]:
    """Walk directory tree, skipping specified directories."""
    import os
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for filename in filenames:
            files.append(current / filename)
    return files


def move_one(src: Path, assets_dir: Path, moved_by_ext: dict[str, int], selected_exts: set[str] | None) -> bool:
    """Move single file to assets directory."""
    ext = safe_suffix(src)
    if selected_exts is not None and ext not in selected_exts:
        return False

    try:
        folder = ext_folder_name(ext)
        dst_dir = assets_dir / folder
        dst_dir.mkdir(parents=True, exist_ok=True)

        base = src.stem
        candidate = dst_dir / src.name
        src_stat = src.stat()
        src_size = src_stat.st_size
        src_mtime = int(src_stat.st_mtime)

        index = 1
        while candidate.exists():
            try:
                dst_stat = candidate.stat()
                if src_size == dst_stat.st_size and src_mtime == int(dst_stat.st_mtime):
                    return False
            except OSError:
                pass

            candidate = dst_dir / f"{base}__{index}{src.suffix}"
            index += 1

        shutil.move(str(src), str(candidate))
        moved_by_ext[folder] = moved_by_ext.get(folder, 0) + 1
        return True
    except Exception as exc:
        tlog(f"[WARN] Failed to move {src}: {exc}")
        return False


def remove_unselected_files(output_dir: Path, selected_exts: set[str] | None) -> dict[str, int]:
    """Remove files with unselected extensions."""
    removed_by_ext: dict[str, int] = {}
    if output_dir is None or not output_dir.exists():
        return removed_by_ext

    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        if ".trash" in path.parts:
            continue

        ext = safe_suffix(path)
        if selected_exts is not None and ext in selected_exts:
            continue

        folder = ext_folder_name(ext)
        try:
            path.unlink()
            removed_by_ext[folder] = removed_by_ext.get(folder, 0) + 1
        except OSError:
            continue

    return dict(sorted(removed_by_ext.items()))


def detect_extensions_in_dir(root: Path, max_scan: int = 200000) -> list[str]:
    """Detect all file extensions in directory."""
    seen: set[str] = set()
    if not root.exists():
        return []
    count = 0
    for file_path in walk_files(root, {".trash", "__pycache__"}):
        seen.add(safe_suffix(file_path))
        count += 1
        if count >= max_scan:
            break
    return sorted(seen)


def detect_extensions(game_root: Path, max_scan: int = 200000) -> list[str]:
    """Detect extensions in game root."""
    seen: set[str] = set(DEFAULT_COMMON_EXTS)
    count = 0
    for file_path in walk_files(game_root, SKIP_DIRS):
        seen.add(safe_suffix(file_path))
        count += 1
        if count >= max_scan:
            break
    return sorted(seen)


def collect_source_roots(game_root: Path, staging_dir: Path) -> list[Path]:
    """Collect roots to scan for files."""
    roots = [staging_dir]
    game_dir = game_root / "game"
    if game_dir.exists() and game_dir.is_dir():
        roots.append(game_dir)
    else:
        roots.append(game_root)
    return roots


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
        
        # Phase 2: Scan and categorize files
        if progress:
            progress("[PHASE 2] Scanning files by extension")
        
        moved_by_ext: dict[str, int] = {}
        files_by_ext: dict[str, int] = {}
        skipped_by_ext: dict[str, int] = {}
        total_scanned = 0
        total_copied = 0
        total_skipped = 0

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
                
                # Check if file should be moved
                if selected_exts is not None and ext not in selected_exts:
                    skipped_by_ext[folder] = skipped_by_ext.get(folder, 0) + 1
                    continue
                
                move_one(src, output_dir, moved_by_ext, selected_exts)

        total_skipped = sum(skipped_by_ext.values())
        
        # Log Phase 2 results
        if progress:
            progress(f"[PHASE 2 SUMMARY] Scanned {total_scanned} total files")
        
        log_append(logs, f"━━ FILE DISCOVERY ━━", progress)
        log_append(logs, f"Total files scanned: {total_scanned}", progress)
        for ext in sorted(files_by_ext.keys()):
            count = files_by_ext[ext]
            log_append(logs, f"  .{ext}: {count} file(s) discovered", progress)
        
        if skipped_by_ext:
            log_append(logs, f"━━ FILTERED OUT (not selected) ━━", progress)
            for ext in sorted(skipped_by_ext.keys()):
                count = skipped_by_ext[ext]
                log_append(logs, f"  .{ext}: {count} file(s) skipped", progress)
        
        log_append(logs, f"━━ FILES MOVED TO ASSETS ━━", progress)
        log_append(logs, f"Total files moved: {sum(moved_by_ext.values())}", progress)
        for ext in sorted(moved_by_ext.keys()):
            count = moved_by_ext[ext]
            log_append(logs, f"  .{ext}: {count} file(s) moved", progress)

        # Phase 3: Logic checks
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
        
        if checks:
            log_append(logs, f"━━ VALIDATION WARNINGS ━━", progress)
            for warning in checks:
                log_append(logs, f"⚠ {warning}", progress)
        else:
            log_append(logs, "✓ All validation checks passed", progress)

        log_append(logs, f"━━ EXTRACTION COMPLETE ━━", progress)

        return {
            "archivesFound": found_count,
            "archivesExtracted": extracted_count,
            "scannedFiles": total_scanned,
            # Keep key name for frontend compatibility.
            "copiedFiles": sum(moved_by_ext.values()),
            "skippedFiles": total_skipped,
            "copiedByExt": dict(sorted(moved_by_ext.items())),
            "filesDiscoveredByExt": dict(sorted(files_by_ext.items())),
            "checks": checks,
            "logs": logs,
            "assetsDir": str(output_dir),
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)
