"""Doom lump decoders: pictures, flats and DMX sounds to PNG / WAV; formats by magic bytes."""

import io
import math
import struct
import wave
import zlib

MAGIC = (
    (b"\x89PNG", ".png"),
    (b"MUS\x1a", ".mus"),
    (b"MThd", ".mid"),
    (b"OggS", ".ogg"),
    (b"fLaC", ".flac"),
    (b"ID3", ".mp3"),
    (b"IMPM", ".it"),
    (b"Extended Module", ".xm"),
)
TEXT_BYTES = frozenset(range(32, 127)) | {9, 10, 13}


def by_magic(data: bytes) -> str:
    """File suffix for self-describing lumps, "" when unknown."""
    for magic, suffix in MAGIC:
        if data.startswith(magic):
            return suffix
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ".wav"
    return ".s3m" if data[44:48] == b"SCRM" else ""


def is_text(data: bytes) -> bool:
    return bool(data) and all(b in TEXT_BYTES for b in data[:4096])


def png(width: int, height: int, rgba: bytes, offsets: tuple[int, int] | None = None) -> bytes:
    """RGBA PNG; offsets go into a grAb chunk (the ZDoom convention) for the round trip."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride : (y + 1) * stride] for y in range(height))
    parts = [
        b"\x89PNG\r\n\x1a\n",
        chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
    ]
    parts.append(chunk(b"IDAT", zlib.compress(raw, 6)))
    if offsets is not None:
        parts.insert(2, chunk(b"grAb", struct.pack(">ii", *offsets)))
    return b"".join(parts) + chunk(b"IEND", b"")


def _rgba(indices: list[int | None], palette: bytes) -> bytes:
    table = [palette[i * 3 : i * 3 + 3] + b"\xff" for i in range(256)]
    clear = b"\x00\x00\x00\x00"
    return b"".join(clear if i is None else table[i] for i in indices)


def _column(data: bytes, start: int, height: int, pixels: list, x: int, width: int) -> None:
    """One column's posts; more posts than the height could hold is damage (a crafted lump
    could replay one long run of empty posts for every column)."""
    top, pos = -1, start
    for _ in range(2 * height + 64):
        if data[pos] == 0xFF:
            return
        delta, length = data[pos], data[pos + 1]
        top = top + delta if delta <= top else delta  # tall patches (DeePsea)
        body = data[pos + 3 : pos + 3 + length]
        if len(body) != length:
            raise IndexError("post runs past the lump")
        for i, value in enumerate(body):
            if 0 <= top + i < height:
                pixels[(top + i) * width + x] = value
        pos += length + 4
    raise IndexError("a column runs on past its height")


def picture(data: bytes, palette: bytes) -> bytes | None:
    """Doom picture format (patches, sprites, menu graphics) to PNG, None if not one."""
    if len(data) < 12:
        return None
    width, height, left, top = struct.unpack_from("<HHhh", data)
    table = 8 + 4 * width
    if not (0 < width <= 4096 and 0 < height <= 4096) or len(data) < table:
        return None
    offsets = struct.unpack_from(f"<{width}I", data, 8)
    if any(not table <= o < len(data) for o in offsets):
        return None
    pixels: list[int | None] = [None] * (width * height)
    try:
        for x, start in enumerate(offsets):
            _column(data, start, height, pixels, x, width)
    except IndexError:
        return None
    return png(width, height, _rgba(pixels, palette), (left, top))


def flat(data: bytes, palette: bytes) -> bytes | None:
    """Raw palettized flats: power-of-two squares, or 64x128 (Heretic/Hexen scrolling flats)."""
    side = math.isqrt(len(data))
    if len(data) == 8192:
        width, height = 64, 128
    elif side * side == len(data) and side in (16, 32, 64, 128, 256, 512, 1024):
        width = height = side
    else:
        return None
    return png(width, height, _rgba(list(data), palette))


def dmx_sound(data: bytes) -> bytes | None:
    """DMX digital sound (format 3, unsigned 8-bit mono) to WAV; 16 pad bytes each side."""
    if len(data) < 8:
        return None
    kind, rate, count = struct.unpack_from("<HHI", data)
    if kind != 3 or not 4000 <= rate <= 96000 or count > len(data) - 8:
        return None
    samples = data[8 : 8 + count]
    samples = samples[16:-16] if len(samples) > 32 else samples
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(1)
        wav.setframerate(rate)
        wav.writeframes(samples)
    return out.getvalue()
