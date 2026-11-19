"""The way back for decode.image (doc 18.3): an edited PNG written as the original DDS, when the
original is uncompressed: 8-bit channels at 24 or 32 bits per pixel in any byte order its masks
give (BGRA8, RGBA8, BGRX8, BGR8...), 8-bit luminance, or a DX10 header naming R8G8B8A8 or
B8G8R8A8. Its header is kept with the PNG's size; mipmaps are rebuilt (box filter) when it had
them. A block-compressed original (BC1-BC7: DXT1-5, ATI1/2, BC4-7) needs an encoder ViWo does
not ship, and a cube map, volume or array texture holds more than one image: both are refused
with that reason, so the plan names the texture."""

import io
import struct

FOURCC, RGB, LUMINANCE = 0x4, 0x40, 0x20000
CUBE_OR_VOLUME = 0x200 | 0x200000
DX10_RAW = {28: "RGBA", 29: "RGBA", 87: "BGRA", 91: "BGRA"}  # DXGI format -> byte order
MIPMAPCOUNT, PITCH, LINEARSIZE = 0x20000, 0x8, 0x80000
COMPRESSED = "block-compressed (BC1-BC7): writing it back needs an encoder ViWo does not ship"


def layout(dds: bytes) -> tuple[int, dict[str, int], int]:
    """(bytes per pixel, channel -> byte index, header size) of an uncompressed DDS; ValueError
    with the reason for anything else."""
    if dds[:4] != b"DDS " or len(dds) < 128:
        raise ValueError("not a DDS texture")
    pf_flags, fourcc, bits, *masks = struct.unpack_from("<I4sIIIII", dds, 80)
    caps2 = struct.unpack_from("<I", dds, 112)[0]
    if caps2 & CUBE_OR_VOLUME:
        raise ValueError("a cube map or volume texture: only single images go back")
    if pf_flags & FOURCC:
        if fourcc != b"DX10" or len(dds) < 148:
            raise ValueError(f"{fourcc.decode('latin-1')} is {COMPRESSED}")
        dxgi, dim, misc, size = struct.unpack_from("<IIII", dds, 128)
        if dxgi not in DX10_RAW:
            raise ValueError(f"DXGI format {dxgi} is {COMPRESSED} or not 8-bit RGBA")
        if dim != 3 or size != 1 or misc & 0x4:  # 0x4: a cube map
            raise ValueError("an array or a non-2D texture: only single images go back")
        return 4, {c: DX10_RAW[dxgi].index(c) for c in "RGBA"}, 148
    names = "L" if pf_flags & LUMINANCE else "RGBA"
    if not pf_flags & (RGB | LUMINANCE) or bits not in ((8,) if names == "L" else (24, 32)):
        raise ValueError(f"a {bits}-bit pixel format ViWo does not write back")
    where = {}
    for name, mask in zip(names, masks):
        if mask and (mask not in [0xFF << (8 * k) for k in range(bits // 8)]):
            raise ValueError(f"channel mask {mask:#x} is not one whole byte")
        if mask:
            where[name] = (mask.bit_length() - 1) // 8
    return bits // 8, where, 128


def _level(image, step: int, where: dict[str, int]) -> bytes:
    if "L" in where:
        return image.convert("L").tobytes()
    rgba = image.convert("RGBA").tobytes()
    out = bytearray(b"\xff" * (len(rgba) // 4 * step))  # an unused byte (X8) stays 0xFF
    for channel, byte in where.items():
        out[byte::step] = rgba["RGBA".index(channel) :: 4]
    return bytes(out)


def write_dds(png: bytes, original: bytes) -> bytes:
    """The DDS for an edited PNG, shaped on the uncompressed `original` (see the module)."""
    from PIL import Image

    step, where, hsize = layout(original)
    with Image.open(io.BytesIO(png)) as opened:
        image = opened.convert("RGBA")
    w, h = image.size
    flags, mips = (
        struct.unpack_from("<I", original, 8)[0],
        struct.unpack_from("<I", original, 28)[0],
    )
    count = 1 if not (flags & MIPMAPCOUNT and mips > 1) else min(mips, max(w, h).bit_length())
    head = bytearray(original[:hsize])
    flags = (flags | PITCH) & ~LINEARSIZE
    struct.pack_into("<IIII", head, 8, flags, h, w, w * step)
    struct.pack_into("<I", head, 28, count)
    levels = [
        _level(image.resize((max(1, w >> n), max(1, h >> n)), Image.Resampling.BOX), step, where)
        for n in range(count)
    ]
    return bytes(head) + b"".join(levels)
