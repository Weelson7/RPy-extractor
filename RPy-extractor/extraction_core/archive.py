"""Archive extraction helpers."""
import shutil
import sys
import tarfile
import uuid
import zipfile
from collections import deque
from pathlib import Path
from typing import Callable

from models import ARCHIVE_SUFFIXES, PYTHON_ARCHIVE_SUFFIXES

from .runtime import run, command_exists, log_append


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

    if suffix == ".unitypackage":
        try:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(output_dir)
            return True, ""
        except Exception as exc:
            return False, str(exc)

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
            log_append(logs, f"[Archive {found_count}] FAILED: {archive.name} - {err[:150]}", progress)
            continue

        files_in_archive = sum(1 for _ in subdir.rglob("*") if _.is_file())
        total_files_extracted += files_in_archive
        log_append(logs, f"[Archive {found_count}] SUCCESS: {archive.name} ({files_in_archive} files)", progress)
        extracted_count += 1

        nested = list_archive_files(subdir)
        if nested:
            log_append(logs, f"[Archive {found_count}] Found {len(nested)} nested archive(s) to extract", progress)
            for nested_archive in nested:
                queue.append(nested_archive)

    log_append(logs, f"EXTRACTION COMPLETE: {extracted_count}/{found_count} succeeded ({total_files_extracted} total files)", progress)
    return extracted_count, found_count, logs
