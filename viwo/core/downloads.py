"""Pinned files fetched and placed (third_party tools, QuickBMS scripts, indexes releases):
an HTTPS download that returns its sha256, archive members unpacked only inside their folder
(no links, devices or traversal), and a folder swap that never leaves half an install."""

import hashlib
import http.client
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
    """Fetch url into target; returns the sha256. A link that drops is picked up where it
    stopped (a Range request; from the start when the server will not), for as long as each
    try brings the file further: three tries in a row that do not, and it is a failure."""
    if not url.startswith(("https://", "file://")):  # file: fixtures in tests
        raise ViwoError("refused", f"{target.name}: downloads must use https")
    target.unlink(missing_ok=True)
    digest, got, best, idle = hashlib.sha256(), 0, 0, 0
    while True:
        digest, got = _fetch_more(url, target, (digest, got), (size, say, cancel))
        if got == size or not size:
            return digest.hexdigest()
        best, idle = max(best, got), 0 if got > best else idle + 1
        last = f"{target.name}: incomplete download ({got} of {size} bytes)"
        if idle >= 3:
            raise ViwoError("failed", last, hint="check the connection and try again")
        if say:
            say(last + ", retrying from there")


def _fetch_more(url: str, target: Path, done: tuple, job: tuple) -> tuple:
    """One request for what is still missing: (digest, bytes in the file). A server that
    answers with the whole file (no 206) starts it again."""
    (digest, got), (size, say, cancel) = done, job
    headers = {"User-Agent": f"ViWo/{__version__}"}  # some build servers refuse Python's
    # default agent (builds.bepinex.dev answers 403)
    headers |= {"Range": f"bytes={got}-"} if got else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
            if got and getattr(r, "status", 200) != 206:
                digest, got = hashlib.sha256(), 0
            ticker = Ticker(say, f"Downloading {target.name}, KB:", size // 1024)
            ticker.tick(got // 1024)
            with open(target, "ab" if got else "wb") as out:
                while chunk := r.read(1 << 20):
                    if cancel is not None and cancel.cancelled:
                        raise ViwoError("cancelled", "download cancelled")
                    out.write(chunk)
                    digest.update(chunk)
                    got += len(chunk)
                    ticker.tick(len(chunk) // 1024)
    except (OSError, http.client.HTTPException) as exc:  # the link dropped: what came is kept
        if say:
            say(f"{target.name}: the connection dropped ({type(exc).__name__})")
    return digest, got


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
