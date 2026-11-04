"""GameProbe implementation: one bounded scan shared by all plugins (doc 2.3)."""

from __future__ import annotations

import fnmatch
from functools import lru_cache
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.types import DetectionResult


class FolderProbe:
    def __init__(self, root: Path, limit: int = 50000) -> None:
        self._root = root
        # (lowercased relative posix path, is_dir, real relative path): matching is
        # case-insensitive, the paths handed back keep their case (Linux is case-sensitive)
        self._rel: list[tuple[str, bool, str]] = []
        self.truncated = False
        for dirpath, dirnames, filenames in ws.walk(root):
            base = Path(dirpath).relative_to(root).as_posix()
            prefix = "" if base == "." else f"{base}/"
            entries = [(f"{prefix}{d}".lower(), True, f"{prefix}{d}") for d in dirnames]
            entries += [(f"{prefix}{f}".lower(), False, f"{prefix}{f}") for f in filenames]
            self._rel += entries
            if len(self._rel) >= limit:
                self.truncated = True
                break
        self._names = {rel.rsplit("/", 1)[-1] for rel, _, _ in self._rel}

    @property
    def root(self) -> Path:
        return self._root

    def has_name(self, *names: str) -> bool:
        return any(name.lower() in self._names for name in names)

    def find(self, pattern: str, limit: int = 100) -> list[Path]:
        """Case-insensitive glob on basenames, or on relative paths when it has a '/'."""
        pat = pattern.lower().removeprefix("**/")
        on_path = "/" in pat
        hits = []
        for rel, _, real in self._rel:
            subject = rel if on_path else rel.rsplit("/", 1)[-1]
            if fnmatch.fnmatchcase(subject, pat):
                hits.append(self._root / real)
                if len(hits) >= limit:
                    break
        return hits

    def with_suffix(self, *suffixes: str) -> list[Path]:
        wanted = tuple(s.lower() for s in suffixes)
        return [
            self._root / real
            for rel, is_dir, real in self._rel
            if not is_dir and rel.endswith(wanted)
        ]

    def head(self, path: Path, size: int = 64) -> bytes:
        return _read(path, size, False)

    def tail(self, path: Path, size: int = 64) -> bytes:
        return _read(path, size, True)


def _read(path: Path, size: int, from_end: bool) -> bytes:
    """Head or tail bytes; cached per (path, size, mtime), so a changed file (a game update,
    a rebuilt patched copy) is read again in a long-running server."""
    try:
        st = path.stat()
    except OSError:
        return b""
    return _cached(path, st.st_size, st.st_mtime_ns, size, from_end)


@lru_cache(maxsize=4096)
def _cached(path: Path, length: int, _mtime: int, size: int, from_end: bool) -> bytes:
    try:
        with open(path, "rb") as fh:
            if from_end:
                fh.seek(max(0, length - size))
            return fh.read(size)
    except OSError:
        return b""


def detect_all(rt, probe: FolderProbe) -> dict[str, DetectionResult]:
    found = {}
    for plugin_id, plugin in rt.plugins.items():
        try:
            found[plugin_id] = plugin.detect(probe)
        except Exception as exc:  # detect must never take the run down
            found[plugin_id] = DetectionResult(
                plugin_id, 0.0, (f"detect failed: {exc}",), plugin_id
            )
    return found
