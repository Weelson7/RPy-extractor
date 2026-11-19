"""The way back for decode.vtf (doc 18.3): an edited PNG written as the original texture again.

The original's header is kept (version, flags, reflectivity, bump scale, the low-resolution
thumbnail, the resources that carry no data) with the PNG's size; the image is stored
uncompressed: in the original's own format when it is an 8-bit-per-channel one the decoder
reads, else (DXT1/3/5) as BGRA8888, the engine's native 32-bit layout, which every Source game
and VTFEdit read; nothing is lost and no compressor is needed. Mipmaps are rebuilt (box filter)
when the original had them. One frame, one face: an animated, cube or volume texture is refused
by name. The CRC resource is dropped (it no longer matches); every other data resource too."""

import io
import struct

from .vtf import ENVMAP, RAW, _size, header

BGRA = 12
NO_DATA = 0x02  # resource entry flag: the value sits in the offset field


def _pixels(image, fmt: int) -> bytes:
    """One mip level in the VTF format `fmt` (a RAW one)."""
    _, mode, raw = RAW[fmt]
    if mode == "RGBA":  # a byte order Pillow may not pack (ARGB): permuted by hand
        rgba = image.convert("RGBA").tobytes()
        out = bytearray(len(rgba))
        for i, channel in enumerate(raw):
            out[i::4] = rgba["RGBA".index(channel) :: 4]
        return bytes(out)
    return image.convert(mode).tobytes("raw", raw)


def _chain(image, mips: int, fmt: int) -> bytes:
    """Every mip level, smallest first (the VTF order)."""
    from PIL import Image

    levels = []
    for level in range(mips):
        w, h = max(1, image.width >> level), max(1, image.height >> level)
        shrunk = image if level == 0 else image.resize((w, h), Image.Resampling.BOX)
        levels.append(_pixels(shrunk, fmt))
    return b"".join(reversed(levels))


def _thumbnail(blob: bytes, info: dict, minor: int) -> bytes:
    """The original's low-resolution image, kept as it is (a stale preview is still valid)."""
    hsize = struct.unpack_from("<I", blob, 12)[0]
    low_fmt, low_w, low_h = struct.unpack_from("<iBB", blob, 57)
    if low_fmt < 0 or not low_w:
        return b""
    at = hsize
    if minor >= 3:
        for tag, offset in _resources(blob):
            at = offset if tag == b"\x01\0\0" else at
    size = _size(low_fmt, low_w, low_h)
    return blob[at : at + size] if at + size <= len(blob) else b""


def _resources(blob: bytes) -> list[tuple[bytes, int]]:
    (count,) = struct.unpack_from("<I", blob, 68)
    return [struct.unpack_from("<3sxI", blob, 80 + 8 * i) for i in range(min(count, 32))]


def _kept_resources(blob: bytes) -> list[bytes]:
    """The original's resource entries that hold no data (LOD, flags...), CRC left out."""
    out = []
    for i in range(min(struct.unpack_from("<I", blob, 68)[0], 32)):
        entry = blob[80 + 8 * i : 88 + 8 * i]
        if entry[3] & NO_DATA and entry[:3] != b"CRC":
            out.append(entry)
    return out


def refusal(head: bytes) -> str:
    """Why a VTF (its first 512 bytes do) cannot go back, "" when it can."""
    try:
        info = header(head)
        flags, frames = struct.unpack_from("<IH", head, 20)
    except (ValueError, struct.error) as exc:
        return str(exc)
    if info["layers"] != 1 or flags & ENVMAP or frames > 1:
        return "an animated, cube or volume texture: only single images go back"
    return ""


def write_vtf(png: bytes, original: bytes) -> bytes:
    """The VTF for an edited PNG, shaped on `original` (see the module)."""
    from PIL import Image

    if why := refusal(original):
        raise ValueError(why)
    info = header(original)
    (minor,) = struct.unpack_from("<I", original, 8)
    with Image.open(io.BytesIO(png)) as opened:
        image = opened.convert("RGBA")
    w, h = image.size
    if not (0 < w <= 0xFFFF and 0 < h <= 0xFFFF):
        raise ValueError(f"size {w}x{h} does not fit a VTF")
    fmt = info["format"] if info["format"] in RAW else BGRA
    mips = 1 if info["mips"] <= 1 else max(w, h).bit_length()
    thumb, data = _thumbnail(original, info, minor), _chain(image, mips, fmt)
    head = bytearray(original[:80].ljust(80, b"\0"))
    struct.pack_into("<HH", head, 16, w, h)
    struct.pack_into("<iB", head, 52, fmt, mips)
    if not thumb:
        struct.pack_into("<iBB", head, 57, -1, 0, 0)
    if minor < 3:  # the image follows the header and the thumbnail
        hsize = struct.unpack_from("<I", original, 12)[0]
        return (bytes(head[:hsize]) + original[80:hsize]).ljust(hsize, b"\0") + thumb + data
    return _with_resources(head, original, thumb, data)


def _with_resources(head: bytearray, original: bytes, thumb: bytes, data: bytes) -> bytes:
    """7.3 and later: a resource table pointing at the thumbnail and the image."""
    kept = _kept_resources(original)
    count = len(kept) + 1 + (1 if thumb else 0)
    hsize = 80 + 8 * count
    entries = struct.pack("<3sxI", b"\x01\0\0", hsize) if thumb else b""
    entries += struct.pack("<3sxI", b"\x30\0\0", hsize + len(thumb)) + b"".join(kept)
    struct.pack_into("<I", head, 12, hsize)
    struct.pack_into("<I", head, 68, count)
    return bytes(head) + entries + thumb + data
