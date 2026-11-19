"""The XNB container (XNA Game Studio 4.0's compiled content format, as FNA and MonoGame read
it): `XNB`, the target platform, format version 5, flags (0x01 HiDef, 0x80 LZX, 0x40 LZ4), the
file's size; when compressed, the size of the data; then the data: the type readers (7-bit
length-prefixed names and a version each), the shared resource count, and the primary object (a
7-bit reader index, then its content). Uncompressed, LZ4 (MonoGame's raw LZ4 block) and LZX
(XNA's XMemCompress, `lzx.py`, first-party) are read; an edited file is written uncompressed when
the original was LZX (ViWo has no LZX compressor) and as LZ4 when it was LZ4. The format versions
of XNA 3.x and older are refused by name."""

import struct
from dataclasses import dataclass

MAGIC = b"XNB"
LZX, LZ4, VERSION = 0x80, 0x40, 5
READERS = ("Texture2DReader", "SoundEffectReader")  # the primary objects ViWo converts


@dataclass
class Xnb:
    head: bytes  # platform, version and flags
    body: bytes  # the data, uncompressed
    start: int  # where the primary object's content starts in body
    reader: str  # its reader's short name ("Texture2DReader"), "" for a null object


def refusal(head: bytes, lz4) -> str:
    """Why this XNB cannot be read, from its first bytes; "" when it can."""
    if len(head) < 10 or not head.startswith(MAGIC):
        return "not an XNB file"
    if head[4] != VERSION:
        return f"XNB format version {head[4]} (XNA 3.1 or older): not read"
    if head[5] & LZ4 and lz4 is None:
        return "LZ4-compressed XNB: needs the 'lz4' Python package"
    return ""


def uleb(data: bytes, at: int) -> tuple[int, int]:
    """.NET's 7-bit encoded int."""
    value = shift = 0
    while True:
        byte = data[at]
        value, at, shift = value | (byte & 0x7F) << shift, at + 1, shift + 7
        if byte < 0x80:
            return value, at
        if shift > 28:
            raise ValueError("a 7-bit encoded number is too long")


def _readers(body: bytes) -> tuple[list[str], int]:
    count, at = uleb(body, 0)
    names = []
    for _ in range(count):
        size, at = uleb(body, at)
        names.append(body[at : at + size].decode("utf-8"))
        at += size + 4  # the reader's version
    if at > len(body):
        raise ValueError("the type readers run past the end")
    return names, at


def _body(data: bytes, lz4) -> bytes:
    if not data[5] & (LZ4 | LZX):
        return data[10:]
    (size,) = struct.unpack_from("<I", data, 10)
    if data[5] & LZX:
        from .lzx import decompress

        return decompress(data, size)  # XNA's XMemCompress, first-party
    try:  # bounded by the declared size
        body = lz4.block.decompress(data[14:], uncompressed_size=max(size, 1))
    except lz4.block.LZ4BlockError as exc:
        raise ValueError(f"damaged LZ4 data: {exc}") from None
    if len(body) != size:
        raise ValueError("the LZ4 data does not inflate to its declared size")
    return body


def read_xnb(data: bytes, lz4) -> Xnb:
    """The container; ValueError when it cannot be read (see refusal)."""
    why = refusal(data[:10], lz4)
    if why:
        raise ValueError(why)
    (size,) = struct.unpack_from("<I", data, 6)
    if size != len(data):
        raise ValueError(f"the header says {size} bytes, the file has {len(data)}")
    body = _body(data, lz4)
    try:
        names, at = _readers(body)
        _, at = uleb(body, at)  # shared resources: kept as they are
        index, at = uleb(body, at)
    except (IndexError, UnicodeDecodeError) as exc:
        raise ValueError(f"damaged XNB: {exc}") from None
    if index > len(names):
        raise ValueError(f"reader {index} of {len(names)}")
    reader = names[index - 1].split(",")[0].split("`")[0].rsplit(".", 1)[-1] if index else ""
    return Xnb(data[3:6], body, at, reader)


def write_xnb(xnb: Xnb, content: bytes, end: int, lz4) -> bytes:
    """The file with the primary object's content (body[start:end]) replaced; LZ4 again as the
    original was, LZX rewritten uncompressed (ViWo has no LZX compressor: the flag is cleared)."""
    body, flags = xnb.body[: xnb.start] + content + xnb.body[end:], xnb.head[2]
    if flags & LZ4:
        packed = lz4.block.compress(body, mode="high_compression", store_size=False)
        body = struct.pack("<I", len(body)) + packed
    elif flags & LZX:
        flags &= ~LZX
    head = xnb.head[:2] + bytes([flags])
    return MAGIC + head + struct.pack("<I", 10 + len(body)) + body
