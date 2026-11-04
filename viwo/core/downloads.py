"""Pinned files fetched and placed (third_party tools, QuickBMS scripts, indexes releases):
an HTTPS download that returns its sha256, archive members unpacked only inside their folder
(no links, devices or traversal), and a folder swap that never leaves half an install."""

from __future__ import annotations

import hashlib
import os
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from viwo import __version__
from viwo.contracts.errors import ViwoError
from viwo.contracts.workspace import safe_member
from viwo.os import host_os_id

from .pipeline.ticker import Ticker

POSIX = host_os_id() != "windows"


def download(url: str, target: Path, size: int, say, cancel) -> str:
    """Fetch url into target; returns the sha256. Short reads (flaky links) are retried."""
    if not url.startswith(("https://", "file://")):  # file: fixtures in tests
        raise ViwoError("refused", f"{target.name}: downloads must use https")
    last = ""
    for attempt in range(1, 4):
        digest, got = _fetch_once(url, target, size, say, cancel)
        if got == size or not size:
            return digest
        last = f"{target.name}: incomplete download ({got} of {size} bytes, attempt {attempt})"
        if say:
            say(last + ", retrying")
    raise ViwoError("failed", last, hint="check the connection and try again")


def _fetch_once(url: str, target: Path, size: int, say, cancel) -> tuple[str, int]:
    digest, ticker = hashlib.sha256(), Ticker(say, f"Downloading {target.name}, KB:", size // 1024)
    got = 0
    request = urllib.request.Request(url, headers={"User-Agent": f"ViWo/{__version__}"})  # some
    # build servers refuse Python's default agent (builds.bepinex.dev answers 403)
    with urllib.request.urlopen(request, timeout=60) as response, open(target, "wb") as out:
        while chunk := response.read(1 << 20):
            if cancel is not None and cancel.cancelled:
                raise ViwoError("cancelled", "download cancelled")
            out.write(chunk)
            digest.update(chunk)
            got += len(chunk)
            ticker.tick(len(chunk) // 1024)
    return digest.hexdigest(), got


def write(src, target: Path, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as dst:
        shutil.copyfileobj(src, dst)
    if POSIX and mode & 0o111:
        os.chmod(target, os.stat(target).st_mode | 0o111)


def unzip(file: Path, out: Path) -> None:
    with zipfile.ZipFile(file) as archive:
        for info in archive.infolist():
            rel = safe_member(info.filename)
            if rel is None or info.is_dir():
                continue
            with archive.open(info) as src:
                write(src, out.joinpath(*rel.parts), info.external_attr >> 16)


def untar(file: Path, out: Path) -> None:
    with tarfile.open(file) as archive:
        for member in archive.getmembers():
            rel = safe_member(member.name)
            if rel is None or not member.isfile():
                continue  # links, devices and traversal are never extracted
            with archive.extractfile(member) as src:
                write(src, out.joinpath(*rel.parts), member.mode)


def swap(out: Path, dest: Path) -> None:
    """dest replaced by out. The old folder is moved aside first, so a locked one (Windows: a
    running tool) is never half deleted: it stays installed and whole."""
    old = dest.with_name(f".{dest.name}.old")
    try:
        if old.exists():
            shutil.rmtree(old)
        if dest.exists():
            os.replace(dest, old)
        os.replace(out, dest)
    except OSError as exc:
        if old.exists() and not dest.exists():
            os.replace(old, dest)
        raise ViwoError(
            "busy",
            f"{dest.name}: cannot replace the installed folder ({exc.strerror or exc})",
            hint="close programs using this tool, then install again",
        )
    shutil.rmtree(old, ignore_errors=True)
