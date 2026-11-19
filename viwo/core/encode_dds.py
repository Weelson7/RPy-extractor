"""The way back for decode.image (doc 18.3): an edited PNG written as the original DDS, its header
kept (a DX10 one too) with the PNG's size, mipmaps rebuilt (box filter) when it had them.

- Uncompressed: 8-bit channels at 24 or 32 bits per pixel in any byte order its masks give
  (BGRA8, RGBA8, BGRX8, BGR8...), 8-bit luminance, DX10 R8G8B8A8 or B8G8R8A8.
- Block-compressed: BC1 (DXT1), BC2 (DXT3), BC3 (DXT5), BC4 (ATI1, BC4U) and BC5 (ATI2,
  BC5U), as FourCC or DX10 (UNORM, sRGB, typeless), and BC6H (unsigned UF16, signed SF16) and
  BC7 (UNORM, sRGB, typeless) as DX10, through ViWo's own encoders (encode_bc.py,
  encode_bptc.py). ATI2 keeps the channel order its decoder showed: ffmpeg shows its first
  block as green, Pillow (the spare) as red.
- Refused with the reason, so the plan names the texture: premultiplied DXT2 and DXT4, signed
  BC4/BC5 (no encoder for them), typeless BC6H (signed or not is the shader's choice: no
  decoder reads it either), any other pixel format, and a cube map, volume or array texture
  (more than one image)."""

import io
import struct

from viwo.backends.blocks import encode_bc

FOURCC, RGB, LUMINANCE = 0x4, 0x40, 0x20000
CUBE_OR_VOLUME = 0x200 | 0x200000
DX10_RAW = {28: "RGBA", 29: "RGBA", 87: "BGRA", 91: "BGRA"}  # DXGI format -> byte order
MIPMAPCOUNT, PITCH, LINEARSIZE = 0x20000, 0x8, 0x80000
BLOCK_FOURCC = {b"DXT1": "BC1", b"DXT3": "BC2", b"DXT5": "BC3", b"ATI1": "BC4", b"BC4U": "BC4"}
BLOCK_FOURCC |= {b"ATI2": "BC5", b"BC5U": "BC5"}
BLOCK_DXGI = {70: "BC1", 71: "BC1", 72: "BC1", 73: "BC2", 74: "BC2", 75: "BC2"}
BLOCK_DXGI |= {76: "BC3", 77: "BC3", 78: "BC3", 79: "BC4", 80: "BC4", 82: "BC5", 83: "BC5"}
BLOCK_DXGI |= {95: "BC6H", 96: "BC6HS", 97: "BC7", 98: "BC7", 99: "BC7"}
NOT_ENCODED = {b"DXT2": "premultiplied BC2", b"DXT4": "premultiplied BC3"}
NOT_ENCODED |= {b"BC4S": "signed BC4", b"BC5S": "signed BC5"}
DXGI_NOT = {81: "signed BC4", 84: "signed BC5", 94: "typeless BC6H: signed or not unknown"}
NO_ENCODER = "block-compressed in a form ViWo has no encoder for (it writes BC1 to BC7)"


def _dx10(dds: bytes) -> tuple[int, dict[str, int], int, str]:
    if len(dds) < 148:
        raise ValueError("a DX10 header cut short")
    dxgi, dim, misc, size = struct.unpack_from("<IIII", dds, 128)
    if dxgi in DXGI_NOT:
        raise ValueError(f"DXGI format {dxgi} ({DXGI_NOT[dxgi]}) is {NO_ENCODER}")
    if dxgi not in DX10_RAW and dxgi not in BLOCK_DXGI:
        raise ValueError(f"DXGI format {dxgi} is not a pixel format ViWo writes back")
    if dim != 3 or size != 1 or misc & 0x4:  # 0x4: a cube map
        raise ValueError("an array or a non-2D texture: only single images go back")
    if dxgi in BLOCK_DXGI:
        return 0, {}, 148, BLOCK_DXGI[dxgi]
    return 4, {c: DX10_RAW[dxgi].index(c) for c in "RGBA"}, 148, ""


def layout(dds: bytes) -> tuple[int, dict[str, int], int, str]:
    """(bytes per pixel, channel -> byte index, header size, block format or "") of a DDS that
    can go back; ValueError with the reason for anything else."""
    if dds[:4] != b"DDS " or len(dds) < 128:
        raise ValueError("not a DDS texture")
    pf_flags, fourcc, bits, *masks = struct.unpack_from("<I4sIIIII", dds, 80)
    caps2 = struct.unpack_from("<I", dds, 112)[0]
    if caps2 & CUBE_OR_VOLUME:
        raise ValueError("a cube map or volume texture: only single images go back")
    if pf_flags & FOURCC:
        if fourcc == b"DX10":
            return _dx10(dds)
        if fourcc in BLOCK_FOURCC:
            return 0, {}, 128, BLOCK_FOURCC[fourcc]
        name = fourcc.decode("latin-1")
        if fourcc in NOT_ENCODED:
            raise ValueError(f"{name} ({NOT_ENCODED[fourcc]}) is {NO_ENCODER}")
        raise ValueError(f"FourCC {name!r} is not a pixel format ViWo writes back")
    names = "L" if pf_flags & LUMINANCE else "RGBA"
    if not pf_flags & (RGB | LUMINANCE) or bits not in ((8,) if names == "L" else (24, 32)):
        raise ValueError(f"a {bits}-bit pixel format ViWo does not write back")
    where = {}
    for name, mask in zip(names, masks):
        if mask and (mask not in [0xFF << (8 * k) for k in range(bits // 8)]):
            raise ValueError(f"channel mask {mask:#x} is not one whole byte")
        if mask:
            where[name] = (mask.bit_length() - 1) // 8
    return bits // 8, where, 128, ""


def _level(image, step: int, where: dict[str, int]) -> bytes:
    if "L" in where:
        return image.convert("L").tobytes()
    rgba = image.convert("RGBA").tobytes()
    out = bytearray(b"\xff" * (len(rgba) // 4 * step))  # an unused byte (X8) stays 0xFF
    for channel, byte in where.items():
        out[byte::step] = rgba["RGBA".index(channel) :: 4]
    return bytes(out)


def _blocks(image, block: str, swap: bool) -> bytes:
    rgba = image.tobytes()
    if swap:  # ATI2 as ffmpeg shows it: red and green change places
        turned = bytearray(rgba)
        turned[0::4], turned[1::4] = rgba[1::4], rgba[0::4]
        rgba = bytes(turned)
    return encode_bc.compress(rgba, image.width, image.height, block)


def write_dds(png: bytes, original: bytes, ati2_green: bool = True) -> bytes:
    """The DDS for an edited PNG, shaped on `original` (see the module). `ati2_green`: the
    PNG came from a decoder that shows ATI2's first block as green (ffmpeg)."""
    from PIL import Image

    step, where, hsize, block = layout(original)
    with Image.open(io.BytesIO(png)) as opened:
        image = opened.convert("RGBA")
    w, h = image.size
    flags, mips = (
        struct.unpack_from("<I", original, 8)[0],
        struct.unpack_from("<I", original, 28)[0],
    )
    count = 1 if not (flags & MIPMAPCOUNT and mips > 1) else min(mips, max(w, h).bit_length())
    head = bytearray(original[:hsize])
    if block:
        flags, pitch = (flags | LINEARSIZE) & ~PITCH, encode_bc.size(block, w, h)
    else:
        flags, pitch = (flags | PITCH) & ~LINEARSIZE, w * step
    struct.pack_into("<IIII", head, 8, flags, h, w, pitch)
    struct.pack_into("<I", head, 28, count)
    swap = ati2_green and original[84:88] == b"ATI2"
    levels = []
    for n in range(count):
        level = image.resize((max(1, w >> n), max(1, h >> n)), Image.Resampling.BOX)
        levels.append(_blocks(level, block, swap) if block else _level(level, step, where))
    return bytes(head) + b"".join(levels)
