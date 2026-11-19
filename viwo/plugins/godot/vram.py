"""Godot's VRAM-compressed textures (doc 16.0c, doc 18.3): S3TC, RGTC and BPTC image data in a
`.ctex`/`.stex`, decoded to an image and written back block for block.

- Godot image formats 17-24 (Godot 3 and 4 number them alike): DXT1, DXT3, DXT5, RGTC_R,
  RGTC_RG, BPTC_RGBA through ViWo's first-party block decoders (viwo/backends/blocks),
  BPTC_RGBF (signed BC6H) and BPTC_RGBFU (unsigned) through Pillow behind a DDS header (HDR
  colour shown clamped to 0..1 in 8 bits, said); Godot 4's DXT5_RA_AS_RG (34, normal maps)
  shown as Godot shows it, red and green from the block's red and alpha.
- Written back through ViWo's block encoders, every mip level, in the same format.
- ETC, ETC2, ASTC and PVRTC are refused by name: no decoder for them in ViWo."""

import io
import struct

# Godot format -> (block format, the name Godot gives it)
VRAM = {17: ("BC1", "DXT1"), 18: ("BC2", "DXT3"), 19: ("BC3", "DXT5"), 20: ("BC4", "RGTC_R")}
VRAM |= {21: ("BC5", "RGTC_RG"), 22: ("BC7", "BPTC_RGBA"), 23: ("BC6HS", "BPTC_RGBF")}
VRAM |= {24: ("BC6H", "BPTC_RGBFU")}
V4_ONLY = {34: ("BC3RA", "DXT5_RA_AS_RG")}
NOT_READ = {
    4: [(25, 25, "ETC"), (26, 33, "ETC2"), (35, 38, "ASTC")],
    3: [(25, 28, "PVRTC"), (29, 29, "ETC"), (30, 36, "ETC2")],
}
DXGI = {"BC6HS": 96, "BC6H": 95}


def block_format(version: int, fmt: int) -> str:
    """The block format of a VRAM-compressed Godot format ViWo reads, else ""."""
    return (VRAM | (V4_ONLY if version == 4 else {})).get(fmt, ("", ""))[0]


def refusal(version: int, fmt: int) -> str:
    """Why a Godot image format is not read."""
    for low, high, name in NOT_READ[version]:
        if low <= fmt <= high:
            return f"Godot image format {fmt} ({name}): no {name} decoder in ViWo"
    return f"Godot image format {fmt} (not 8-bit, not a block format ViWo reads): not decoded"


def _dds(data: bytes, kind: str, size: tuple[int, int]) -> bytes:
    """A DX10 DDS of one BC6H image, for Pillow."""
    (w, h), length = size, ((size[0] + 3) // 4) * ((size[1] + 3) // 4) * 16
    head = struct.pack("<7I44x", 124, 0x81007, h, w, length, 0, 1)
    head += struct.pack("<II4s5I", 32, 4, b"DX10", 0, 0, 0, 0, 0)
    head += struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    return b"DDS " + head + struct.pack("<5I", DXGI[kind], 3, 0, 1, 0) + data[:length]


def image(data: bytes, kind: str, size: tuple[int, int]):
    """A Pillow image of the top level of VRAM-compressed data (ValueError: cut short)."""
    from PIL import Image

    from viwo.backends.blocks.decode_bc import decompress

    if kind in DXGI:
        if len(data) < ((size[0] + 3) // 4) * ((size[1] + 3) // 4) * 16:
            raise ValueError(f"{kind} data cut short")
        with Image.open(io.BytesIO(_dds(data, kind, size))) as opened:
            return opened.convert("RGB")
    rgba = decompress(data, *size, "BC3" if kind == "BC3RA" else kind)
    if kind == "BC3RA":  # Godot's convert_ra_rgba8_to_rg: green from alpha, blue 0, opaque
        out, n = bytearray(rgba), len(rgba) // 4
        out[1::4], out[2::4], out[3::4] = rgba[3::4], bytes(n), b"\xff" * n
        rgba = bytes(out)
    shown = Image.frombytes("RGBA", size, rgba)
    return shown.convert({"BC4": "L", "BC5": "RGB", "BC3RA": "RGB"}.get(kind, "RGBA"))


def level(picture, kind: str) -> bytes:
    """One level written as `kind` blocks (DXT5_RA_AS_RG: red and green into red and alpha)."""
    from viwo.backends.blocks.encode_bc import compress

    rgba = picture.convert("RGBA").tobytes()
    if kind == "BC3RA":  # Godot's convert_rg_to_ra_rgba8
        out = bytearray(len(rgba))
        out[0::4], out[3::4] = rgba[0::4], rgba[1::4]
        rgba, kind = bytes(out), "BC3"
    return compress(rgba, picture.width, picture.height, kind)
