"""pack.pyi (doc 18): a PyInstaller onefile exe rebuilt in the patched copy with edited CArchive
members (data files, binaries, top-level modules). The bootloader bytes before the archive and
the cookie's python version and lib name are kept; members are laid out again and the TOC and
cookie rewritten, so an unchanged exe comes back byte for byte. Modules inside the inner PYZ are
extracted read-only: editing one would mean rebuilding the PYZ, which is not done here (said).
The container is rewritten (PyInstaller unpacks to a temp dir at run, loading nothing loose over
it). Read back after writing."""

import struct
import zlib
from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from . import carchive as c

SLOT = SlotDefinition("pack.pyi", "pack", "pyfrozen", "pyi-writer")


def out_name(name: str, typ: bytes) -> str:
    """The workspace path a CArchive member is written to (mirrors the unarchiver)."""
    if typ in c.MODULE_TYPES:
        return name.replace(".", "/") + ".pyc"
    return name


def _member_data(raw, start, entry, edit: bytes | None):
    """(stored bytes, zlib flag, uncompressed length) for one entry, edited or original."""
    name, dpos, dlen, ulen, cflag, typ = entry
    if edit is None:
        return raw[start + dpos : start + dpos + dlen], cflag, ulen
    body = edit[16:] if typ in c.MODULE_TYPES and len(edit) >= 16 else edit
    return body, 0, len(body)


def build_archive(raw: bytes, edits: dict[str, bytes]) -> bytes:
    """`raw` rebuilt with edits (workspace path -> bytes); byte-identical when edits is empty."""
    start, toc_abs, toc_len, pylib = c.find_archive(raw)
    _, pkg_len, toc_pos, _, pyvers, _ = struct.unpack_from(c.COOKIE, raw, raw.rfind(c.PKG_MAGIC))
    entries = c.toc(raw, toc_abs, toc_len)
    body, table, at = bytearray(), bytearray(), 0
    for entry in entries:
        name, _, _, _, _, typ = entry
        data, cflag, ulen = _member_data(raw, start, entry, edits.get(out_name(name, typ)))
        raw_name = name.encode("utf-8") + b"\x00"
        slen = c.ENTRY_SIZE + len(raw_name)
        slen += (-slen) % 16  # PyInstaller pads the entry to a 16-byte boundary
        table += struct.pack(c.ENTRY, slen, at, len(data), ulen, cflag, typ)
        table += raw_name + b"\x00" * (slen - c.ENTRY_SIZE - len(raw_name))
        body += data
        at += len(data)
    toc_at = len(body)
    total = toc_at + len(table) + c.COOKIE_SIZE
    cookie = struct.pack(c.COOKIE, c.PKG_MAGIC, total, toc_at, len(table), pyvers, pylib)
    return raw[:start] + bytes(body) + bytes(table) + cookie


class PyiWriter(Packer):
    backend_id, owner, license = "pyi-writer", "pyfrozen", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: the read-back parses the written archive

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        try:
            raw = container.read_bytes()
            names = {out_name(n, typ) for n, *_, typ in _entries(raw)}
            edits = {m.replace("\\", "/"): s.read_bytes() for m, s in members.items()}
            unknown = sorted(set(edits) - names)
            container.write_bytes(
                build_archive(raw, {m: d for m, d in edits.items() if m in names})
            )
        except (OSError, ValueError, zlib.error, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"PyInstaller exe not rebuilt: {exc}"[:300])
        notes = [f"{len(unknown)} member(s) not in the archive (PYZ-interior?): not added"] * bool(
            unknown
        )
        return Outcome(OutcomeKind.OK, len(edits) - len(unknown), notes=tuple(notes))


def _entries(raw: bytes):
    start, toc_abs, toc_len, _ = c.find_archive(raw)
    return c.toc(raw, toc_abs, toc_len)
