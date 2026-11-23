"""The zip layer an APK's way back needs and Python's zipfile does not give: the central
directory read as raw records (names as stored, extras, comments, offsets), and a rebuild that
copies every member's compressed bytes unchanged, in their order, with each stored member's data
aligned (zipalign: 4 bytes, 4096 for `.so` when the original page-aligned them) through the
alignment extra field apksigner writes (0xD935). Zip64 is refused by name (an APK never is)."""

import struct
import zlib
from dataclasses import dataclass, replace

END = b"PK\x05\x06"
CENTRAL = b"PK\x01\x02"
LOCAL = b"PK\x03\x04"
ALIGN_EXTRA = 0xD935
STORED, DEFLATED = 0, 8
PAGE = 4096


@dataclass(frozen=True)
class Entry:
    name: bytes
    made_by: int
    needed: int
    flags: int
    method: int
    time: int
    date: int
    crc: int
    csize: int
    usize: int
    extra: bytes
    comment: bytes
    internal: int
    external: int
    offset: int

    @property
    def text(self) -> str:
        return self.name.decode("utf-8" if self.flags & 0x800 else "cp437")


def _end_record(fh, size: int) -> tuple[int, int, int, bytes]:
    """(entries, central directory size, its offset, the archive comment)."""
    fh.seek(max(0, size - 65557))
    tail = fh.read()
    at = tail.rfind(END)
    if at < 0 or at + 22 > len(tail):
        raise ValueError("no zip end record")
    _, _, _, count, cd_size, cd_at, length = struct.unpack_from("<4HIIH", tail, at + 4)
    if count == 0xFFFF or cd_at == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        raise ValueError("a zip64 archive (over 4 GB or 65,535 members): not rebuilt")
    return count, cd_size, cd_at, tail[at + 22 : at + 22 + length]


def read_entries(fh, size: int) -> tuple[list[Entry], bytes]:
    """(every central directory record in order, the archive comment)."""
    count, cd_size, cd_at, comment = _end_record(fh, size)
    if cd_at + cd_size > size:
        raise ValueError("the central directory lies past the end of the file")
    fh.seek(cd_at)
    raw, at, out = fh.read(cd_size), 0, []
    for _ in range(count):
        if raw[at : at + 4] != CENTRAL:
            raise ValueError(f"central directory record {len(out)} is damaged")
        fields = struct.unpack_from("<6H3I5H2I", raw, at + 4)
        n, m, k = fields[9:12]
        name = raw[at + 46 : at + 46 + n]
        extra, note = raw[at + 46 + n : at + 46 + n + m], raw[at + 46 + n + m : at + 46 + n + m + k]
        made, need, flags, method, time, date, crc, csize, usize = fields[:9]
        out.append(Entry(name, made, need, flags, method, time, date, crc, csize, usize,
                         extra, note, fields[13], fields[14], fields[15]))  # fmt: skip
        at += 46 + n + m + k
    return out, comment


def data_at(fh, entry: Entry) -> tuple[int, bytes]:
    """(where the member's data starts, its local extra field)."""
    fh.seek(entry.offset)
    head = fh.read(30)
    if len(head) < 30 or head[:4] != LOCAL:
        raise ValueError(f"{entry.text}: no local header where the directory says")
    n, m = struct.unpack_from("<HH", head, 26)
    fh.seek(entry.offset + 30 + n)
    return entry.offset + 30 + n + m, fh.read(m)


def records(extra: bytes) -> bytes:
    """The extra field without an alignment record or zipalign's zero padding."""
    out, at = b"", 0
    while at + 4 <= len(extra):
        tag, size = struct.unpack_from("<HH", extra, at)
        if tag == 0 or at + 4 + size > len(extra):
            break  # zero padding, or a record cut short: the rest is padding
        if tag != ALIGN_EXTRA:
            out += extra[at : at + 4 + size]
        at += 4 + size
    return out


def aligned(extra: bytes, data_start: int, align: int) -> bytes:
    """`extra` plus an alignment record so the data that follows starts on `align`."""
    if data_start % align == 0:
        return extra
    pad = (-(data_start + 6)) % align
    return extra + struct.pack("<HHH", ALIGN_EXTRA, 2 + pad, align) + bytes(pad)


def page_aligned(fh, entries: list[Entry]) -> bool:
    """Whether every stored `.so` of the original starts on a page (zipalign -p)."""
    libs = [e for e in entries if e.method == STORED and e.text.endswith(".so")]
    return bool(libs) and all(data_at(fh, e)[0] % PAGE == 0 for e in libs)


def packed(entry: Entry, data: bytes) -> tuple[Entry, bytes]:
    """An edited member's record and bytes: its own method kept (stored or deflated; another
    method is deflated, said by the caller)."""
    method = STORED if entry.method == STORED else DEFLATED
    body = data
    if method == DEFLATED:
        squeeze = zlib.compressobj(9, zlib.DEFLATED, -15)
        body = squeeze.compress(data) + squeeze.flush()
    crc, needed = zlib.crc32(data) & 0xFFFFFFFF, max(entry.needed, 20 if method else 10)
    fields = {"method": method, "crc": crc, "csize": len(body), "usize": len(data)}
    fields["flags"] = entry.flags & ~0x1  # written in the clear, whatever the original was
    return replace(entry, needed=needed, **fields), body


def new_entry(name: str, data: bytes, method: int) -> tuple[Entry, bytes]:
    base = Entry(name.encode("utf-8"), 20, 20, 0x800, method, 0, 0x21, 0, 0, 0, b"", b"", 0, 0, 0)
    return packed(base, data)


def local_header(entry: Entry, extra: bytes) -> bytes:
    flags = entry.flags & ~0x8  # sizes in the header: no data descriptor follows
    fixed = (entry.needed, flags, entry.method, entry.time, entry.date, entry.crc)
    sizes = (entry.csize, entry.usize, len(entry.name), len(extra))
    return LOCAL + struct.pack("<5HI2I2H", *fixed, *sizes) + entry.name + extra


def central_record(entry: Entry) -> bytes:
    fixed = (entry.made_by, entry.needed, entry.flags & ~0x8, entry.method, entry.time)
    sizes = (entry.date, entry.crc, entry.csize, entry.usize, len(entry.name), len(entry.extra))
    rest = (len(entry.comment), 0, entry.internal, entry.external, entry.offset)
    head = CENTRAL + struct.pack("<6H3I5H2I", *fixed, *sizes, *rest)
    return head + entry.name + entry.extra + entry.comment


def end_record(count: int, cd_size: int, cd_at: int, comment: bytes) -> bytes:
    if count > 0xFFFF or cd_at + cd_size > 0xFFFFFFFF:
        raise ValueError("the rebuilt archive needs zip64: not written")
    return END + struct.pack("<4HIIH", 0, 0, count, count, cd_size, cd_at, len(comment)) + comment
