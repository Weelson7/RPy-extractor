"""XNB primary objects ViWo converts, both ways. Texture2D: surface format, width, height, mip
count, then each level's size and data; Color (RGBA8), Bgr565, Bgra5551, Bgra4444, Alpha8 and
DXT1/3/5 (through `backends/blocks`) to PNG (the largest level) and back (every level rebuilt,
box filter, when it had mipmaps); another surface format is refused by name. Colours are what the
file holds: XNA's content pipeline premultiplies alpha by default, and the PNG shows that.
SoundEffect: the WAVEFORMATEX, the samples, the loop start and length and the duration, to a WAV
with that format chunk and back (the loop kept when it still fits, else the whole sound)."""

import io
import struct

from viwo.backends.blocks.decode_bc import decompress
from viwo.backends.blocks.encode_bc import compress
from viwo.backends.blocks.encode_bc import size as block_size

NAMES = ("Color", "Bgr565", "Bgra5551", "Bgra4444", "Dxt1", "Dxt3", "Dxt5", "NormalizedByte2")
NAMES += ("NormalizedByte4", "Rgba1010102", "Rg32", "Rgba64", "Alpha8", "Single", "Vector2")
NAMES += ("Vector4", "HalfSingle", "HalfVector2", "HalfVector4", "HdrBlendable")
BLOCKS = {4: "BC1", 5: "BC2", 6: "BC3"}
PACKED = {  # (shift, bits) of red, green, blue, alpha in one little-endian 16-bit value
    1: ((11, 5), (5, 6), (0, 5), None),
    2: ((10, 5), (5, 5), (0, 5), (15, 1)),
    3: ((8, 4), (4, 4), (0, 4), (12, 4)),
}
READ = (0, 1, 2, 3, 4, 5, 6, 12)


def _level_bytes(fmt: int, w: int, h: int) -> int:
    if fmt in BLOCKS:
        return block_size(BLOCKS[fmt], w, h)
    return w * h * (4 if fmt == 0 else 1 if fmt == 12 else 2)


def texture(body: bytes, at: int) -> tuple[int, int, int, list, int]:
    """(format, width, height, [level data], end) of a Texture2D's content."""
    fmt, w, h, count = struct.unpack_from("<iIII", body, at)
    if fmt not in READ:
        name = NAMES[fmt] if 0 <= fmt < len(NAMES) else str(fmt)
        raise ValueError(f"surface format {name}: not converted")
    if not 0 < w <= 16384 or not 0 < h <= 16384 or count > 15:
        raise ValueError(f"a {w}x{h} texture with {count} levels is damage")
    at, levels = at + 16, []
    for _ in range(count):
        (n,) = struct.unpack_from("<I", body, at)
        levels.append(body[at + 4 : at + 4 + n])
        at += 4 + n
    if at > len(body) or not levels or len(levels[0]) < _level_bytes(fmt, w, h):
        raise ValueError("texture data cut short")
    return fmt, w, h, levels, at


def _unpack16(data: bytes, fmt: int, n: int) -> bytes:
    values = struct.unpack(f"<{n}H", data[: 2 * n])
    out = bytearray(b"\xff" * (4 * n))
    for c, spec in enumerate(PACKED[fmt]):
        if spec is not None:
            shift, bits = spec
            top = (1 << bits) - 1
            table = bytes((v * 255 + top // 2) // top for v in range(top + 1))
            out[c::4] = bytes(table[v >> shift & top] for v in values)
    return bytes(out)


def _pack16(rgba: bytes, fmt: int) -> bytes:
    n = len(rgba) // 4
    values = [0] * n
    for c, spec in enumerate(PACKED[fmt]):
        if spec is not None:
            shift, bits = spec
            top = (1 << bits) - 1
            table = [((e * top + 127) // 255) << shift for e in range(256)]
            values = [v | table[e] for v, e in zip(values, rgba[c::4])]
    return struct.pack(f"<{n}H", *values)


def to_rgba(fmt: int, data: bytes, w: int, h: int) -> bytes:
    if fmt == 0:
        return data[: 4 * w * h]
    if fmt in BLOCKS:
        return decompress(data, w, h, BLOCKS[fmt])
    if fmt == 12:  # Alpha8: white, its alpha
        out = bytearray(b"\xff" * (4 * w * h))
        out[3::4] = data[: w * h]
        return bytes(out)
    return _unpack16(data, fmt, w * h)


def from_rgba(fmt: int, rgba: bytes, w: int, h: int) -> bytes:
    if fmt == 0:
        return rgba
    if fmt in BLOCKS:
        return compress(rgba, w, h, BLOCKS[fmt])
    return rgba[3::4] if fmt == 12 else _pack16(rgba, fmt)


def texture_png(body: bytes, at: int) -> bytes:
    from PIL import Image

    fmt, w, h, levels, _ = texture(body, at)
    out = io.BytesIO()
    Image.frombytes("RGBA", (w, h), to_rgba(fmt, levels[0], w, h)).save(out, "PNG")
    return out.getvalue()


def texture_back(png: bytes, body: bytes, at: int) -> tuple[bytes, int]:
    """(the Texture2D content holding the PNG, the end of the original content)."""
    from PIL import Image

    fmt, _, _, levels, end = texture(body, at)
    with Image.open(io.BytesIO(png)) as opened:
        image = opened.convert("RGBA")
    w, h = image.size
    count = max(w, h).bit_length() if len(levels) > 1 else 1
    sizes = [(max(1, w >> n), max(1, h >> n)) for n in range(count)]
    out = bytearray(struct.pack("<iIII", fmt, w, h, count))
    for size in sizes:
        level = image if size == image.size else image.resize(size, Image.Resampling.BOX)
        data = from_rgba(fmt, level.tobytes(), *size)
        out += struct.pack("<I", len(data)) + data
    return bytes(out), end


def sound(body: bytes, at: int) -> tuple[bytes, bytes, tuple, int]:
    """(WAVEFORMATEX, samples, (loop start, loop length, duration ms), end) of a SoundEffect."""
    (n,) = struct.unpack_from("<I", body, at)
    fmt = body[at + 4 : at + 4 + n]
    at += 4 + n
    (size,) = struct.unpack_from("<I", body, at)
    data = body[at + 4 : at + 4 + size]
    at += 4 + size
    if len(fmt) != n or len(data) != size or n < 16:
        raise ValueError("sound data cut short")
    return fmt, data, struct.unpack_from("<iii", body, at), at + 12


def _even(tag: bytes, data: bytes) -> bytes:
    return tag + struct.pack("<I", len(data)) + data + b"\0" * (len(data) % 2)


def sound_wav(body: bytes, at: int) -> bytes:
    fmt, data, _, _ = sound(body, at)
    chunks = _even(b"fmt ", fmt) + _even(b"data", data)
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


def read_wav(wav: bytes) -> tuple[bytes, bytes]:
    """(format chunk, samples) of a WAV file."""
    if wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    at, found = 12, {}
    while at + 8 <= len(wav):
        tag, (n,) = wav[at : at + 4], struct.unpack_from("<I", wav, at + 4)
        found.setdefault(tag, wav[at + 8 : at + 8 + n])
        at += 8 + n + n % 2
    if b"fmt " not in found or b"data" not in found or len(found[b"fmt "]) < 16:
        raise ValueError("a WAV file without its format or its samples")
    return found[b"fmt "], found[b"data"]


def sound_back(wav: bytes, body: bytes, at: int) -> tuple[bytes, int]:
    """(the SoundEffect content holding the WAV, the end of the original content)."""
    fmt, data = read_wav(wav)
    old_fmt, old_data, (start, length, duration), end = sound(body, at)
    if (fmt, data) != (old_fmt, old_data):
        rate, align = struct.unpack_from("<I", fmt, 4)[0], struct.unpack_from("<H", fmt, 12)[0]
        samples = len(data) // max(1, align)
        if start < 0 or length < 0 or start + length > samples:
            start, length = 0, samples
        duration = samples * 1000 // max(1, rate)
    head = struct.pack("<I", len(fmt)) + fmt + struct.pack("<I", len(data)) + data
    return head + struct.pack("<iii", start, length, duration), end
