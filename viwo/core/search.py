"""Content search (static arm, doc 6.7): a string, a number or a byte pattern (the needles of
core/search_query.py) found in a workspace's extracted files, a game folder or one file, which
are only read. A file streams in 8 MB chunks that overlap by the longest needle less one byte,
so a match across two chunks is found once and memory stays at one chunk whatever the size.
Hits are capped per file and overall, and a cap that drops a hit is said; a file or folder that
cannot be read is named and counted, never skipped silently. Every hit carries a few bytes of
context, in an executable its section, RVA and virtual address (patch_tools `pe`, `address_of`),
and for the first ones of a file the unique AOB signature of `patch.sig` (patch_tools
`signature`), so it goes straight into a patch set (doc 18.8). Reports land in `.search/`."""

import json
import mmap
import os
import struct
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

from .patch_tools import address_of, pe, signature
from .pipeline.guard import outside_games, refuse_writes_inside
from .pipeline.ticker import Ticker, clock
from .search_query import Query
from .steps import tell
from .workspace import claim, write_atomic

CHUNK = 8 << 20
BIG = 64 << 20  # a file this large is said by name, with its own progress in MB
FOLDER = ".search"
NAMED = 20  # unreadable files named one by one in the log; the report names them all
STAGE = "search"


@dataclass(frozen=True)
class Limits:
    per_file: int = 100
    total: int = 1000
    context: int = 16  # bytes before and after a hit
    signatures: int = 8  # per file: finding a unique one reads the file again

    def __post_init__(self) -> None:
        if min(self.per_file, self.total) < 1 or not 0 <= self.context <= 4096:
            raise ViwoError("invalid_request", "hit caps start at 1, context is 0 to 4096 bytes")
        if self.signatures < 0:
            raise ViwoError("invalid_request", "signatures per file start at 0")


@dataclass
class _Run:
    query: Query
    limits: Limits
    sink: object = None
    cancel: object = None
    hits: list = field(default_factory=list)
    unreadable: list = field(default_factory=list)
    capped: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    searched: int = 0
    read: int = 0

    def say(self, message: str, level: str = "info") -> None:
        if level == "warn":
            self.warnings.append(message)
        tell(self.sink, message, STAGE, level)

    def stop(self) -> None:
        if self.cancel is not None and self.cancel.cancelled:
            raise ViwoError("cancelled", "search cancelled")


def search(target: Path, query: Query, limits=None, sink=None, cancel=None, save_to=None):
    """Search `target` (a file or a folder) for `query`; the report, saved under `save_to`
    (a workspace, results_folder) when one is given."""
    started, run = time.monotonic(), _Run(query, limits or Limits(), sink, cancel)
    kind, items = targets(target, run)
    sizes = [_size(path) for path, _ in items]
    total = _mb(sum(sizes))
    run.say(f"Searching {len(items):,} file(s), {total} in {target} ({kind}): {query.describe()}")
    for note in query.notes:
        run.say(note)
    ticker = Ticker(run.say, "Searched files:", len(items))
    for i, ((path, rel), size) in enumerate(zip(items, sizes)):
        run.stop()
        if _one(run, path, rel, size):  # the overall cap dropped a hit: the rest is not read
            if left := len(items) - i - 1:
                run.say(f"{left:,} file(s) after {rel} not searched (overall cap)", "warn")
            break
        ticker.tick(note=f"{len(run.hits):,} hit(s), {_mb(run.read)} / {total}")
    return _report(run, target, kind, len(items), time.monotonic() - started, save_to)


def targets(target: Path, run: _Run) -> tuple[str, list[tuple[Path, str]]]:
    """(kind, [(file, its path relative to what is searched, POSIX)]): one file, a ViWo
    workspace (its dot entries left out: trash, metadata, earlier results) or any folder (a
    game: every file; links are never followed, an unreadable folder is named)."""
    if target.is_file():
        return "file", [(target, target.name)]
    if not target.is_dir():
        raise ViwoError("not_found", f"nothing to search at {target}", hint="a file or a folder")
    owned, found = ws.has_marker(target), []
    for dirpath, dirnames, names in os.walk(target, onerror=lambda e: _unreadable(run, e, target)):
        top = owned and Path(dirpath) == target
        dirnames[:] = [d for d in dirnames if not ws.link_like(os.path.join(dirpath, d))]
        dirnames[:] = [d for d in dirnames if not (top and ws.is_reserved(d))]
        found += [Path(dirpath, n) for n in names if not (top and ws.is_reserved(n))]
    rows = [(p, p.relative_to(target).as_posix()) for p in found]
    return ("workspace" if owned else "folder"), sorted(rows, key=lambda row: row[1])


def _one(run: _Run, path: Path, rel: str, size: int) -> bool:
    """One file into the run; True when the overall cap dropped one of its hits."""
    room = min(run.limits.per_file, run.limits.total - len(run.hits))
    progress = None
    if size >= BIG:
        run.say(f"Searching {rel} ({size >> 20:,} MB)")
        progress = Ticker(run.say, f"{rel}, MB:", size >> 20).tick
    try:
        with open(path, "rb") as fh:
            found, dropped = _scan(fh, run, room, progress)
        rows = _detail(path, rel, found, run.limits) if found else []
    except (OSError, ValueError) as exc:  # refused, locked, gone, or shrunk before its mapping
        _unreadable(run, exc, path.parent, rel)
        return False
    run.searched, run.read, run.hits = run.searched + 1, run.read + size, run.hits + rows
    if dropped is None:
        return False
    overall = room < run.limits.per_file
    cap = f"the overall cap of {run.limits.total:,}" if overall else f"{room:,} per file"
    run.capped.append({"file": rel, "at": dropped, "overall": overall})
    said = f"{rel}: hits capped at {cap}; the hit at {dropped:#x} and the rest were not kept"
    run.say(said, "warn")
    return overall


def _scan(fh, run: _Run, room: int, progress=None) -> tuple[list, int | None]:
    """Up to `room` hits (start, end, encoding) in file order, and the offset of the first hit
    past them (None when there is none)."""
    keep = max(n.size for n in run.query.needles) - 1
    hits, base, buf = [], 0, b""
    while True:
        run.stop()
        chunk = fh.read(CHUNK)
        buf, last = buf + chunk, len(chunk) < CHUNK
        limit = len(buf) if last else max(0, len(buf) - keep)  # later starts: the next chunk
        found = _matches(buf, run.query.needles, limit, room + 1 - len(hits))
        hits += [(base + start, base + end, label) for start, end, label in found]
        if len(hits) > room:
            return hits[:room], hits[room][0]
        if progress is not None:
            progress(len(chunk) >> 20)
        if last:
            return hits, None
        base, buf = base + limit, buf[limit:]


def _matches(buf: bytes, needles, limit: int, want: int) -> list:
    """The first `want` matches of any needle that start before `limit`, overlapping ones too
    (a patch set's matcher counts them the same way)."""
    found = []
    for needle in needles:
        pos, end, mine = 0, limit + needle.size - 1, 0
        while mine < want and (span := needle.find(buf, pos, end)) and span[0] < limit:
            found.append((*span, needle.label))
            pos, mine = span[0] + 1, mine + 1
    return sorted(found)[:want]


def _detail(path: Path, rel: str, found: list, limits: Limits) -> list[dict]:
    with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as data:
        image = _pe(data)
        return [
            _row(data, image, (rel, *hit), i < limits.signatures, limits.context)
            for i, hit in enumerate(found)
        ]


def _row(data, image, hit: tuple, sig: bool, context: int) -> dict:
    rel, start, end, label = hit
    before, match = data[max(0, start - context) : start], data[start:end]
    after = data[end : end + context]
    row = {"file": rel, "offset": start, "length": end - start, "encoding": label}
    row |= {"before": before.hex(" "), "match": match.hex(" "), "after": after.hex(" ")}
    row["text"] = "".join(chr(b) if 32 <= b < 127 else "." for b in before + match + after)
    if image is not None:
        row |= _address(data, image, start)
    if sig:
        row["signature"] = _signature(data, start)
    row["patch"] = {"file": rel, "offset": hex(start), "original": row["match"]}
    return row


def _address(data, image: dict, offset: int) -> dict:
    """Where an executable loads the hit; None outside every section (headers, an overlay)."""
    for name, (_va, _size, raw, raw_size) in zip(image["names"], image["sections"]):
        if raw <= offset < raw + raw_size:
            address = address_of(data, offset)
            return {"section": name, "rva": address - image["base"], "va": address}
    return {"section": None, "rva": None, "va": None}


def _signature(data, offset: int) -> dict:
    """The unique AOB of `patch.sig` on the mapped file (a large file is never read whole)."""
    try:
        pattern, at = signature(data, offset)
    except ViwoError as exc:
        return {"error": exc.message}
    return {"pattern": pattern, "at": at}


def _pe(data) -> dict | None:
    try:
        return pe(data)
    except (struct.error, ValueError):  # a truncated header: no addresses, still searched
        return None


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0  # the open names it


def _unreadable(run: _Run, exc: Exception, root: Path, rel: str = "") -> None:
    """A file or folder that could not be read: in the report, and named in the log."""
    if not rel:
        try:
            rel = Path(exc.filename).relative_to(root).as_posix()
        except (AttributeError, TypeError, ValueError):
            rel = str(getattr(exc, "filename", "") or root)
    why = getattr(exc, "strerror", None) or str(exc)
    run.unreadable.append({"file": rel, "error": why})
    if len(run.unreadable) <= NAMED:
        run.say(f"Cannot read {rel}: {why}", "warn")


def _mb(size: int) -> str:
    return f"{size / 1e6:,.1f} MB"


def _report(run: _Run, target: Path, kind: str, files: int, seconds: float, save_to) -> dict:
    with_hits = len({h["file"] for h in run.hits})
    if len(run.unreadable) > NAMED:
        run.say(f"{len(run.unreadable) - NAMED:,} more unreadable file(s): see the report", "warn")
    said = f"Searched {run.searched:,} of {files:,} file(s), {_mb(run.read)} in {clock(seconds)}"
    run.say(f"{said}: {len(run.hits):,} hit(s) in {with_hits:,} file(s)")
    report = {"target": str(target), "kind": kind, "query": run.query.to_dict()}
    report |= {"limits": asdict(run.limits), "files": files, "searched": run.searched}
    report |= {"bytes": run.read, "hitCount": len(run.hits), "filesWithHits": with_hits}
    report |= {"capped": run.capped, "unreadable": run.unreadable, "warnings": run.warnings}
    report |= {"seconds": round(seconds, 2), "hits": run.hits}
    if save_to is not None:
        folder = Path(save_to) / FOLDER
        folder.mkdir(parents=True, exist_ok=True)
        path = ws.next_free(folder / f"{time.strftime('%Y%m%d-%H%M%S')}-{run.query.kind}.json")
        report["saved"] = str(path)
        write_atomic(path, json.dumps(report, indent=1))
        run.say(f"Results saved: {path}")
    return report


def results_folder(target: Path, workspace: Path | None) -> Path | None:
    """Where the report is saved: `workspace`, else the ViWo workspace searched or holding what
    is searched; None with neither. Never in what is searched (unless that is a workspace) or a
    game the guard knows (doc 3.1); a folder of someone else's files is refused, a new or empty
    one becomes a workspace."""
    target = target.resolve()
    home = next((p for p in (target, *target.parents) if ws.has_marker(p)), None)
    folder = workspace or home
    if folder is None:
        return None
    if home is None:
        searched = target if target.is_dir() else target.parent
        refuse_writes_inside(searched, **{"results folder": folder})
    outside_games(folder, "results folder")
    if not ws.has_marker(folder):
        if folder.is_dir() and any(folder.iterdir()):
            raise ViwoError(
                "refused",
                f"{folder} is not a ViWo workspace: no search results are written there",
                hint="give an empty folder or a ViWo workspace",
            )
        claim(folder)
    return folder
