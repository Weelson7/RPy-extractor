"""decode.vtf (doc 16.0c): Source engine textures (VTF 7.0-7.5) to PNG, in process. The largest
mipmap of the first frame (face, slice) is read: block-compressed formats (DXT1, DXT3, DXT5)
through a DDS header for Pillow, the 8-bit-per-channel formats as raw pixels. Mipmaps are stored
smallest first, each with all frames, faces and slices; from 7.3 a resource table points at the
image data, before that it follows the header and the low-resolution thumbnail."""

import io
import struct
from pathlib import Path

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

SLOT = SlotDefinition("decode.vtf", "decode", "source", "vtf-builtin", suffixes=(".vtf",))
PILLOW = DependencySpec(
    "pillow", "Pillow", kind="python", import_name="PIL", hint="pip install Pillow"
)
BLOCKS = {13: (b"DXT1", 8), 14: (b"DXT3", 16), 15: (b"DXT5", 16), 20: (b"DXT1", 8)}
RAW = {  # format -> (bytes per pixel, Pillow mode, raw mode)
    0: (4, "RGBA", "RGBA"), 1: (4, "RGBA", "ABGR"), 2: (3, "RGB", "RGB"), 3: (3, "RGB", "BGR"),
    5: (1, "L", "L"), 6: (2, "LA", "LA"), 8: (1, "L", "L"), 9: (3, "RGB", "RGB"),
    10: (3, "RGB", "BGR"), 11: (4, "RGBA", "ARGB"), 12: (4, "RGBA", "BGRA"),
    16: (4, "RGB", "BGRX"),
}  # fmt: skip
LIMIT = 1 << 14  # a texture side larger than this is damage, not art
ENVMAP = 0x4000


def _size(fmt: int, width: int, height: int) -> int:
    if fmt in BLOCKS:
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * BLOCKS[fmt][1]
    if fmt in RAW:
        return width * height * RAW[fmt][0]
    raise ValueError(f"VTF image format {fmt} is not decoded yet")


def header(blob: bytes) -> dict:
    if blob[:4] != b"VTF\0":
        raise ValueError("not a VTF texture")
    major, minor, size, width, height, flags, frames = struct.unpack_from("<IIIHHIH", blob, 4)
    fmt, mips, low_fmt, low_w, low_h = struct.unpack_from("<iBiBB", blob, 52)
    depth = struct.unpack_from("<H", blob, 63)[0] if minor >= 2 else 1
    if major != 7 or not (0 < width <= LIMIT and 0 < height <= LIMIT) or not 0 < mips <= 16:
        raise ValueError("VTF header out of range")
    image = size + (_size(low_fmt, low_w, low_h) if low_fmt >= 0 and low_w else 0)
    if minor >= 3:
        (count,) = struct.unpack_from("<I", blob, 68)
        for i in range(min(count, 32)):
            tag, offset = struct.unpack_from("<3sxI", blob, 80 + 8 * i)
            image = offset if tag == b"\x30\0\0" else image
    (first_frame,) = struct.unpack_from("<H", blob, 26)  # VTFLib: before 7.5 an env map also
    faces = (7 if minor < 5 and first_frame != 0xFFFF else 6) if flags & ENVMAP else 1  # sphere
    return {"width": width, "height": height, "format": fmt, "mips": mips, "image": image,
            "layers": max(1, frames) * faces * max(1, depth)}  # fmt: skip


def largest(blob: bytes, info: dict) -> bytes:
    """The full-size image of the first frame: past every smaller mipmap's layers."""
    at = info["image"]
    for level in range(info["mips"] - 1, 0, -1):
        w, h = max(1, info["width"] >> level), max(1, info["height"] >> level)
        at += _size(info["format"], w, h) * info["layers"]
    size = _size(info["format"], info["width"], info["height"])
    if at + size > len(blob):
        raise ValueError("VTF image data cut short")
    return blob[at : at + size]


def to_png(blob: bytes) -> bytes:
    from PIL import Image

    info = header(blob)
    data, fmt = largest(blob, info), info["format"]
    w, h = info["width"], info["height"]
    if fmt in BLOCKS:
        dds = struct.pack("<4sIIIIIII44x", b"DDS ", 124, 0x81007, h, w, len(data), 0, 1)
        dds += struct.pack("<II4s20x", 32, 0x4, BLOCKS[fmt][0]) + struct.pack("<I16x", 0x1000)
        image = Image.open(io.BytesIO(dds + data))
    else:
        _, mode, raw = RAW[fmt]
        image = Image.frombytes(mode, (w, h), data, "raw", raw)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


class VtfDecoder(Decoder):
    backend_id, owner, license = "vtf-builtin", "source", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def dependencies(self):
        return (PILLOW,)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        try:
            (dest / f"{path.stem}.png").write_bytes(to_png(path.read_bytes()))
        except (ValueError, struct.error, OSError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{path.name}: {exc}")
        return Outcome(OutcomeKind.OK, 1)
