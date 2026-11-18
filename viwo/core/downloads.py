"""Pinned files fetched and placed (third_party tools, QuickBMS scripts, indexes releases):
an HTTPS download that returns its sha256, archive members unpacked only inside their folder
(no links, devices or traversal), and a folder swap that never leaves half an install."""

import hashlib
import http.client
import os
import shutil
import tarfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from viwo import __version__
from viwo.contracts.errors import ViwoError
from viwo.contracts.workspace import safe_member
from viwo.os import host_os_id

from .pipeline.ticker import Ticker

POSIX = host_os_id() != "windows"
HINTS = {  # an HTTP error answer: what the user can do about it
    404: "the release may have moved; report it",
    410: "the release may have moved; report it",
    401: "the server refuses this download; report it",
    403: "the server refuses this download; report it",
    429: "the server limits requests: wait a few minutes and try again",
}


@dataclass
class _Fetch:
    """One download's progress across its tries."""

    total: int  # the pinned size, else what the server said (Content-Length/Range); 0: unknown
    digest: object = field(default_factory=hashlib.sha256)
    got: int = 0  # bytes in the file
    whole: bool = False  # the last answer's body ended cleanly
    why: str = ""  # what ended the last try


def download(url: str, target: Path, size: int, say, cancel) -> str:
    """Fetch url into target; returns the sha256. A link that drops is picked up where it
    stopped (a Range request; from the start when the server will not), for as long as each
    try brings the file further: three tries in a row that do not, and it is a failure named by
    what ended it. An HTTP error answer (4xx) fails at once; a 5xx is tried again. Without a
    pinned size the server's length says when the file is whole; with none, a body that ends
    cleanly is, and one that drops is not."""
    if not url.startswith(("https://", "file://")):  # file: fixtures in tests
        raise ViwoError("refused", f"{target.name}: downloads must use https")
    target.unlink(missing_ok=True)
    state, best, idle = _Fetch(size), 0, 0
    while True:
        _fetch_more(url, target, state, (say, cancel))
        if state.got == state.total if state.total else state.whole:
            return state.digest.hexdigest()
        best, idle = max(best, state.got), 0 if state.got > best else idle + 1
        of = f"{state.got} of {state.total}" if state.total else f"{state.got}, size unknown,"
        last = f"{target.name}: incomplete download ({of} bytes)"
        if idle >= 3:
            why = state.why or "the answer ended before the file did"
            server = why.startswith("the server answered")
            hint = "the server is failing: try again later" if server else ""
            hint = hint or "check the connection and try again"
            raise ViwoError("failed", f"{last}: {why}", hint=hint)
        if say:
            say(last + ", retrying from there")


def _fetch_more(url: str, target: Path, state: _Fetch, job: tuple) -> None:
    """One request for what is still missing, into `state`. A server that answers with the
    whole file (no 206) starts it again; an HTTP error answer is named (4xx: raised)."""
    say, cancel = job
    headers = {"User-Agent": f"ViWo/{__version__}"}  # some build servers refuse Python's
    # default agent (builds.bepinex.dev answers 403)
    headers |= {"Range": f"bytes={state.got}-"} if state.got else {}
    state.whole, state.why = False, ""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
            _begin(r, state)
            ticker = Ticker(say, f"Downloading {target.name}, KB:", state.total // 1024)
            ticker.tick(state.got // 1024)
            with open(target, "ab" if state.got else "wb") as out:
                while chunk := r.read(1 << 20):
                    if cancel is not None and cancel.cancelled:
                        raise ViwoError("cancelled", "download cancelled")
                    out.write(chunk)
                    state.digest.update(chunk)
                    state.got += len(chunk)
                    ticker.tick(len(chunk) // 1024)
            state.whole = True
    except urllib.error.HTTPError as exc:  # an answer, not a drop: urlopen raises it
        _answered(exc, target, url, state)
    except (OSError, http.client.HTTPException) as exc:  # the link dropped: what came is kept
        state.why = f"the connection dropped ({type(exc).__name__})"
    if say and state.why:
        say(f"{target.name}: {state.why}")


def _total(r, partial: bool) -> int:
    """The whole file's size by the answer's headers: Content-Range of a 206 (or a 416),
    Content-Length of a 200; 0 when the server does not say."""
    headers = getattr(r, "headers", None) or {}
    if partial:
        text = str(headers.get("Content-Range") or "").rpartition("/")[2]
    else:
        text = str(headers.get("Content-Length") or "")
    return int(text) if text.isdigit() else 0


def _begin(r, state: _Fetch) -> None:
    """A Range request answered with the whole file (no 206) starts it again; an unpinned
    size is learnt from the answer."""
    partial = getattr(r, "status", 200) == 206
    if state.got and not partial:
        state.digest, state.got = hashlib.sha256(), 0
    if not state.total:
        state.total = _total(r, partial)


def _answered(exc, target: Path, url: str, state: _Fetch) -> None:
    """An HTTP error answer: 4xx fails at once with its status and a hint, a 5xx is named
    and tried again. A 416 to a Range from the end of a file of unknown size means it is
    whole."""
    code, reason = exc.code, str(exc.reason or "").strip()
    exc.close()
    if code == 416 and state.got and _total(exc, True) == state.got and not state.total:
        state.whole = True
        return
    answer = f"HTTP {code} {reason}".strip()
    if code < 500:
        hint = HINTS.get(code, "report it")
        raise ViwoError("failed", f"{target.name}: the URL answers {answer} ({url})", hint=hint)
    state.why = f"the server answered {answer}"


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
