"""A host folder handed to a QEMU guest (doc 11.8): QEMU on Windows has no shared-folder device
(no 9p or virtiofs host), so the folder becomes a read-only CD. pycdlib (a pinned package) writes
it into the session folder as ISO 9660 with UDF 2.60, Rock Ridge and Joliet: Windows reads the
UDF names, Linux the Rock Ridge ones, both in full; the ISO 9660 names underneath are synthetic
(D000001, F000001) so no file name is refused, and Joliet's are cut to 64 bytes and kept
unique. The folder is read, never written; the image is a copy (said with its size) and is built
again only when the folder changed. A link or an unreadable file is skipped and said."""

import json
import os
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.types import DependencySpec

PYCDLIB = DependencySpec.of("pycdlib")
JOLIET = 64


def _signature(folder: Path) -> dict:
    count = size = newest = 0
    for root, _, files in os.walk(folder):
        for name in files:
            try:
                st = os.stat(os.path.join(root, name))
            except OSError:
                continue
            count, size, newest = count + 1, size + st.st_size, max(newest, int(st.st_mtime))
    return {"folder": str(folder), "files": count, "bytes": size, "newest": newest}


def _cut(name: str, limit: int) -> str:
    """`name` cut to `limit` UTF-8 bytes (pycdlib's measure), never inside a character."""
    return name.encode("utf-8")[:limit].decode("utf-8", "ignore")


def _joliet(name: str, taken: set[str]) -> str:
    """A Joliet component: at most 64 bytes, unique in its directory."""
    short, n = _cut(name, JOLIET), 1
    while short.lower() in taken:
        tail = f"~{n}"
        short, n = _cut(name, JOLIET - len(tail)) + tail, n + 1
    taken.add(short.lower())
    return short


class _Tree:
    def __init__(self, iso, log, fault) -> None:
        self.iso, self.log, self.n, self.skipped = iso, log, 0, 0
        self.fault = fault  # pycdlib's own exception: a name or size it refuses

    def _name(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{self.n:06d}"

    def add(self, folder: Path, paths: tuple[str, str, str]) -> None:
        """Add `folder`'s entries under (iso path, joliet path, udf path)."""
        iso_dir, jol_dir, udf_dir = paths
        taken: set[str] = set()
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError as exc:
            self.log(f"Share: {folder} skipped ({exc})", "warn")
            self.skipped += 1
            return
        for entry in entries:
            jol = f"{jol_dir}/{_joliet(entry.name, taken)}"
            udf = f"{udf_dir}/{entry.name}"
            if entry.is_symlink():
                self.log(f"Share: {entry.path} is a link, skipped", "warn")
                self.skipped += 1
            elif entry.is_dir():
                iso = f"{iso_dir}/{self._name('D')}"
                self.iso.add_directory(iso, rr_name=entry.name, joliet_path=jol, udf_path=udf)
                self.add(Path(entry.path), (iso, jol, udf))
            else:
                self._file(entry, f"{iso_dir}/{self._name('F')}.;1", jol, udf)

    def _file(self, entry, iso: str, jol: str, udf: str) -> None:
        try:
            with open(entry.path, "rb"):
                pass
            self.iso.add_file(entry.path, iso, rr_name=entry.name, joliet_path=jol, udf_path=udf)
        except (OSError, ValueError, self.fault) as exc:
            self.log(f"Share: {entry.path} skipped ({exc})", "warn")
            self.skipped += 1


def build(folder: Path, out: Path, log) -> Path:
    """The read-only CD image of `folder` at `out` (kept while the folder does not change)."""
    if not folder.is_dir():
        raise ViwoError("not_found", f"the folder to share is not there: {folder}")
    mark = out.with_suffix(".json")
    signature = _signature(folder)
    try:
        if out.is_file() and json.loads(mark.read_text(encoding="utf-8")) == signature:
            log(f"Share: {out.name} kept (the folder has not changed)", "info")
            return out
    except (OSError, ValueError):
        pass
    try:
        import pycdlib
    except ImportError as exc:
        raise ViwoError("unavailable", "sharing a folder with QEMU needs pycdlib",
                        hint="viwo install pycdlib") from exc  # fmt: skip
    log(f"Share: writing {folder} ({signature['files']} files, {signature['bytes'] >> 20} MB) "
        f"as a read-only CD at {out}", "info")  # fmt: skip
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, rock_ridge="1.09", udf="2.60", vol_ident="VIWO_SHARE")
    tree = _Tree(iso, log, pycdlib.pycdlibexception.PyCdlibException)
    tree.add(folder, ("", "", ""))
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        iso.write(str(out))
    finally:
        iso.close()
    mark.write_text(json.dumps(signature), encoding="utf-8")
    if tree.skipped:
        log(f"Share: {tree.skipped} entries skipped (said above)", "warn")
    return out
