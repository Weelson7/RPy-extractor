"""The string pool chunk Android's binary XML and `resources.arsc` share (ResStringPool): a
header, the offsets of every string and style, the strings (UTF-8 or UTF-16, each with its
length in front and a terminator behind) and the style spans. Read whole; written new (binary
XML's way back) or appended to with every byte of the original kept (the table's way back)."""

import struct
from dataclasses import dataclass, field

KIND = 0x0001
HEADER = 28
UTF8 = 0x100
SORTED = 0x1


@dataclass
class Pool:
    strings: list[str]
    flags: int
    style_count: int
    start: int  # the chunk's absolute offset in the file
    size: int  # the chunk's length
    styled: set[int] = field(default_factory=set)  # indexes of strings with style spans

    @property
    def utf8(self) -> bool:
        return bool(self.flags & UTF8)

    def get(self, index: int) -> str | None:
        """The string at index; None for the "no string" index (0xFFFFFFFF)."""
        if index == 0xFFFFFFFF:
            return None
        if not 0 <= index < len(self.strings):
            raise ValueError(f"string index {index} outside the pool's {len(self.strings)}")
        return self.strings[index]


def chunk_head(raw: bytes, at: int, end: int) -> tuple[int, int, int]:
    """(type, header size, size) of the chunk at `at`, checked to lie inside [at, end)."""
    kind, head, size = struct.unpack_from("<HHI", raw, at)
    if head < 8 or size < head or at + size > end:
        raise ValueError(f"chunk 0x{kind:04x} at {at} does not fit its file")
    return kind, head, size


def _length(raw: bytes, at: int, wide: bool) -> tuple[int, int]:
    """(length, position after it): one or two units, the high bit saying two."""
    if wide:
        (first,) = struct.unpack_from("<H", raw, at)
        if first & 0x8000:
            (second,) = struct.unpack_from("<H", raw, at + 2)
            return ((first & 0x7FFF) << 16) | second, at + 4
        return first, at + 2
    first = raw[at]
    if first & 0x80:
        return ((first & 0x7F) << 8) | raw[at + 1], at + 2
    return first, at + 1


def _string(raw: bytes, at: int, end: int, utf8: bool) -> str:
    if utf8:
        _, at = _length(raw, at, False)  # UTF-16 length, then the UTF-8 byte count
        count, at = _length(raw, at, False)
        data, width = raw[at : at + count], 1
    else:
        count, at = _length(raw, at, True)
        data, width = raw[at : at + count * 2], 2
    if at + count * width > end:
        raise ValueError("a string runs past its pool")
    return data.decode("utf-8" if utf8 else "utf-16-le")


def read_pool(raw: bytes, at: int, end: int) -> Pool:
    """The pool chunk at `at`; ValueError (or struct.error) on anything damaged."""
    kind, head, size = chunk_head(raw, at, end)
    if kind != KIND or head < HEADER:
        raise ValueError(f"expected a string pool at {at}, found chunk 0x{kind:04x}")
    count, styles, flags, strings_at, styles_at = struct.unpack_from("<5I", raw, at + 8)
    if head + 4 * (count + styles) > size or strings_at > size or styles_at > size:
        raise ValueError("the string pool's counts do not fit its chunk")
    offsets = struct.unpack_from(f"<{count}I", raw, at + head)
    limit = at + (styles_at if styles else size)
    base = at + strings_at
    strings = [_string(raw, base + o, limit, bool(flags & UTF8)) for o in offsets]
    return Pool(strings, flags, styles, at, size, set(range(min(styles, count))))


def _encoded(text: str, utf8: bool) -> bytes:
    units = len(text.encode("utf-16-le")) // 2
    if utf8:
        data = text.encode("utf-8")
        if units > 0x7FFF or len(data) > 0x7FFF:
            raise ValueError(f"a string of {len(data)} bytes is too long for a UTF-8 pool")
        return _short(units) + _short(len(data)) + data + b"\0"
    if units > 0x7FFFFFFF:
        raise ValueError("a string is too long for its pool")
    if units > 0x7FFF:
        size = struct.pack("<HH", 0x8000 | (units >> 16), units & 0xFFFF)
    else:
        size = struct.pack("<H", units)
    return size + text.encode("utf-16-le") + b"\0\0"


def _short(n: int) -> bytes:
    return bytes([n]) if n <= 0x7F else bytes([0x80 | (n >> 8), n & 0xFF])


def _pad(data: bytes) -> bytes:
    return data + b"\0" * (-len(data) % 4)


def write_pool(strings: list[str], utf8: bool) -> bytes:
    """A new pool of these strings, no styles."""
    offsets, data = [], b""
    for text in strings:
        offsets.append(len(data))
        data += _encoded(text, utf8)
    start = HEADER + 4 * len(strings)
    body = struct.pack(f"<{len(strings)}I", *offsets) + _pad(data)
    flags = UTF8 if utf8 else 0
    head = struct.pack("<HHI5I", KIND, HEADER, HEADER + len(body), len(strings), 0, flags, start, 0)
    return head + body


def append_pool(raw: bytes, pool: Pool, more: list[str]) -> bytes:
    """The pool chunk with `more` strings after its own: every original string, offset and
    style kept byte for byte (offsets count from the data's start, so they still hold); the
    sorted flag is dropped (the new strings are not in order)."""
    at, head = pool.start, struct.unpack_from("<H", raw, pool.start + 2)[0]
    count, styles, flags, strings_at, styles_at = struct.unpack_from("<5I", raw, at + 8)
    old_offsets = raw[at + head : at + head + 4 * count]
    style_offsets = raw[at + head + 4 * count : at + head + 4 * (count + styles)]
    data_end = styles_at if styles else pool.size
    data = _pad(raw[at + strings_at : at + data_end])
    added = []
    for text in more:
        added.append(len(data))
        data += _encoded(text, bool(flags & UTF8))
    data = _pad(data)
    style_data = raw[at + styles_at : at + pool.size] if styles else b""
    total = count + len(more)
    new_strings_at = head + 4 * (total + styles)
    new_styles_at = new_strings_at + len(data) if styles else 0
    offsets = old_offsets + struct.pack(f"<{len(more)}I", *added) + style_offsets
    extra = raw[at + HEADER : at + head]  # a header longer than the 28 bytes known: kept
    size = new_strings_at + len(data) + len(style_data)
    fields = (total, styles, flags & ~SORTED, new_strings_at, new_styles_at)
    return struct.pack("<HHI5I", KIND, head, size, *fields) + extra + offsets + data + style_data
