"""The way back for decode.ctex (doc 18.3): an edited PNG written as the original Godot texture.

The original's header is kept (version, flags, mipmap limit, the image format field) with the
PNG's size, and so is its form: a PNG texture gets PNG mipmaps, a WebP one lossless WebP (a lossy
original too: the same data format, nothing more lost), each behind the original's tag (`PNG `,
`WEBP` or none); an uncompressed one its 8-bit format (L8, LA8, R8, RG8, RGB8, RGBA8) as raw
bytes; a VRAM-compressed one (S3TC, RGTC, BPTC) in its block format through ViWo's block
encoders (vram.py). Mipmaps are rebuilt (box filter) down to 1x1 when it had them. An ETC,
ETC2, ASTC, PVRTC or Basis Universal texture is refused by name (no decoder, no encoder), and
so is a WebP one when this Pillow cannot write WebP; without Pillow nothing is written, and the
reason says how to get it."""

import io
import struct

from .ctex import PILLOW, RAW, parse
from .vram import level as vram_level

WEBP_LIMIT = 16383  # the largest side WebP holds


def _pillow(webp: bool) -> str:
    """Why this Python cannot write the texture, "" when it can."""
    try:
        from PIL import features
    except ImportError:
        return f"Pillow is not installed ({PILLOW.hint})"
    if webp and not features.check("webp"):
        return "this Pillow was built without WebP: it cannot write the texture's WebP mipmaps"
    return ""


def refusal(head: bytes) -> str:
    """Why a texture (its first 64 bytes do) cannot go back, "" when it can."""
    try:
        tex = parse(head, whole=False)
    except (ValueError, struct.error) as exc:
        return str(exc)
    return _pillow(tex.kind == "webp")


def _raw(image, fmt: int) -> bytes:
    """One level in an uncompressed Godot format (R8 and RG8 from the red and green)."""
    mode = RAW[fmt][0]
    if mode in ("L", "LA", "RGB", "RGBA"):
        return image.convert(mode).tobytes()
    rgba = image.convert("RGBA").tobytes()
    if mode == "R":
        return rgba[0::4]
    out = bytearray(len(rgba) // 2)
    out[0::2], out[1::2] = rgba[0::4], rgba[1::4]
    return bytes(out)


def _payload(image, kind: str, mode: str, tag: bytes) -> bytes:
    out = io.BytesIO()
    if kind == "png":
        image.convert(mode).save(out, "PNG")
    else:  # WebP holds RGB or RGBA; lossless, transparent pixels keep their colour
        webp = "RGBA" if "A" in mode else "RGB"
        image.convert(webp).save(out, "WEBP", lossless=True, quality=100, exact=True)
    data = tag + out.getvalue()
    return struct.pack("<I", len(data)) + data


def _mode(original: bytes, tex) -> str:
    """The Pillow mode of the original's first mipmap (its channels are kept)."""
    from PIL import Image

    at, size = tex.payloads[0]
    with Image.open(io.BytesIO(original[at + len(tex.tag) : at + size])) as first:
        return first.mode if first.mode in ("L", "LA", "RGB", "RGBA") else "RGBA"


def write_ctex(png: bytes, original: bytes) -> bytes:
    """The texture for an edited PNG, shaped on `original` (see the module)."""
    tex = parse(original)
    if why := _pillow(tex.kind == "webp"):
        raise ValueError(why)
    from PIL import Image

    with Image.open(io.BytesIO(png)) as opened:
        image = opened.convert("RGBA")
    w, h = image.size
    if max(w, h) > (WEBP_LIMIT if tex.kind == "webp" else 0xFFFF):
        raise ValueError(f"size {w}x{h} does not fit this texture's form")
    count = max(w, h).bit_length() if tex.mips else 1
    sizes = [(max(1, w >> n), max(1, h >> n)) for n in range(count)]
    levels = [image.resize(size, Image.Resampling.BOX) for size in sizes]
    if tex.kind == "raw":
        body = b"".join(_raw(level, tex.fmt) for level in levels)
    elif tex.kind == "vram":
        body = b"".join(vram_level(level, tex.block) for level in levels)
    else:
        mode = _mode(original, tex)
        body = b"".join(_payload(level, tex.kind, mode, tex.tag) for level in levels)
        body = (struct.pack("<I", count) if tex.version == 3 else b"") + body
    head = bytearray(original[: 52 if tex.version == 4 else 20])
    if tex.version == 4:
        struct.pack_into("<II", head, 8, w, h)
        struct.pack_into("<HHI", head, 40, w, h, count - 1)
    else:
        struct.pack_into("<H", head, 4, w)
        struct.pack_into("<H", head, 8, h)
    return bytes(head) + body
