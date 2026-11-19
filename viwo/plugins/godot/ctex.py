"""decode.ctex (doc 16.0c): Godot's imported textures to PNG, in process: `.ctex` (Godot 4,
`GST2`) and `.stex` (Godot 3, `GDST`). Read: the lossless and lossy forms (every mipmap its own
PNG or WebP, behind Godot's 4-byte `PNG `/`WEBP` tag when it has one) and the uncompressed form
in the 8-bit formats (L8, LA8, R8, RG8, RGB8, RGBA8). The largest mipmap is written. A
VRAM-compressed (S3TC, BPTC, ETC, ASTC...) or Basis Universal texture is not decoded yet: said
per file. The way back is ctex_write.py."""

import io
import struct
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

SLOT = SlotDefinition("decode.ctex", "decode", "godot", "ctex-builtin", suffixes=(".ctex", ".stex"))
PILLOW = DependencySpec(
    "pillow", "Pillow", kind="python", import_name="PIL", hint="pip install Pillow"
)
RAW = {0: ("L", 1), 1: ("LA", 2), 2: ("R", 1), 3: ("RG", 2), 4: ("RGB", 3), 5: ("RGBA", 4)}
IMAGE, PNG, WEBP, BASIS = 0, 1, 2, 3  # Godot 4 data formats
LOSSLESS, LOSSY, MIPMAPS = 1 << 20, 1 << 21, 1 << 23  # Godot 3 format bits
TAGS = (b"PNG ", b"WEBP")
LIMIT = 1 << 14  # a texture side larger than this is damage, not art


@dataclass
class Texture:
    version: int  # 3 (.stex) or 4 (.ctex)
    width: int
    height: int
    kind: str  # "png", "webp" or "raw"
    fmt: int = 5  # Godot image format of a raw texture
    mips: bool = False
    head: int = 0  # bytes of header before the image data
    payloads: list = field(default_factory=list)  # (offset, size) of each PNG/WebP mipmap
    tag: bytes = b""  # Godot's tag before each payload


def _payloads(blob: bytes, at: int, count: int, whole: bool) -> list[tuple[int, int]]:
    """(offset, size) of each mipmap; from a header alone, the first one's offset only."""
    if not whole:
        return [(at + 4, 0)]
    out = []
    for _ in range(count):
        (size,) = struct.unpack_from("<I", blob, at)
        if at + 4 + size > len(blob):
            raise ValueError("a mipmap cut short")
        out.append((at + 4, size))
        at += 4 + size
    return out


def _sniff(blob: bytes, at: int) -> tuple[str, bytes]:
    """(payload kind, Godot's tag) of a PNG/WebP mipmap starting at `at`."""
    tag = blob[at : at + 4] if blob[at : at + 4] in TAGS else b""
    body = blob[at + len(tag) : at + len(tag) + 4]
    if body == b"\x89PNG":
        return "png", tag
    if body == b"RIFF":
        return "webp", tag
    raise ValueError("an image payload that is neither PNG nor WebP")


def _v4(blob: bytes, whole: bool) -> Texture:
    data, w, h, mipmaps, fmt = struct.unpack_from("<IHHII", blob, 36)
    tex = Texture(4, w, h, "raw", fmt, mipmaps > 0, 52)
    if data in (PNG, WEBP):
        if mipmaps > 16:
            raise ValueError("mipmap count out of range")
        tex.payloads = _payloads(blob, 52, mipmaps + 1, whole)
    elif data == BASIS:
        raise ValueError("Basis Universal: needs a Basis transcoder ViWo does not ship")
    elif data != IMAGE:
        raise ValueError(f"unknown Godot data format {data}")
    return tex


def _v3(blob: bytes, whole: bool) -> Texture:
    w, h, df = struct.unpack_from("<H2xH2x4xI", blob, 4)
    tex = Texture(3, w, h, "raw", df & 0xFFFFF, bool(df & MIPMAPS), 20)
    if df & (LOSSLESS | LOSSY):
        (count,) = struct.unpack_from("<I", blob, 20)
        if not 0 < count <= 16:
            raise ValueError("mipmap count out of range")
        tex.payloads, tex.head, tex.mips = _payloads(blob, 24, count, whole), 24, count > 1
    return tex


def parse(blob: bytes, whole: bool = True) -> Texture:
    """The texture's shape; ValueError with the reason for what is not read. whole=False:
    `blob` is the first 64 bytes, enough for the shape (payload sizes are not checked)."""
    magic = blob[:4]
    if magic not in (b"GST2", b"GDST") or len(blob) < (52 if magic == b"GST2" else 24):
        raise ValueError("not a Godot texture (.ctex GST2 or .stex GDST)")
    blob = blob if whole else blob[:64].ljust(64, b"\0")
    tex = _v4(blob, whole) if magic == b"GST2" else _v3(blob, whole)
    if not (0 < tex.width <= LIMIT and 0 < tex.height <= LIMIT):
        raise ValueError("texture size out of range")
    if tex.payloads:
        tex.kind, tex.tag = _sniff(blob, tex.payloads[0][0])
    elif tex.fmt not in RAW:
        why = f"Godot image format {tex.fmt} (VRAM-compressed or not 8-bit)"
        raise ValueError(f"{why}: not decoded yet")
    return tex


def raw_image(data: bytes, fmt: int, size: tuple[int, int]):
    """A Pillow image of one uncompressed level (R8 as grey, RG8 with an empty blue)."""
    from PIL import Image

    mode, step = RAW[fmt]
    if len(data) < size[0] * size[1] * step:
        raise ValueError("image data cut short")
    if mode == "R":
        return Image.frombytes("L", size, data)
    if mode == "RG":
        rgb = bytearray(size[0] * size[1] * 3)
        rgb[0::3], rgb[1::3] = data[0 : len(rgb) // 3 * 2 : 2], data[1 : len(rgb) // 3 * 2 : 2]
        return Image.frombytes("RGB", size, bytes(rgb))
    return Image.frombytes(mode, size, data)


def to_png(blob: bytes) -> bytes:
    from PIL import Image

    tex = parse(blob)
    if tex.payloads:
        at, size = tex.payloads[0]
        image = Image.open(io.BytesIO(blob[at + len(tex.tag) : at + size]))
    else:
        image = raw_image(blob[tex.head :], tex.fmt, (tex.width, tex.height))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


class CtexDecoder(Decoder):
    backend_id, owner, license = "ctex-builtin", "godot", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process
    encodes = True  # an edited PNG back to the texture (ctex_write.py, doc 18.3)

    def dependencies(self):
        return (PILLOW,)

    def refuses(self, original: Path) -> str:
        from .ctex_write import refusal

        with open(original, "rb") as fh:
            why = refusal(fh.read(64))
        return f"{original.name}: {why}" if why else ""

    def encode(self, edited: Path, original: Path, out: Path, ctx) -> Outcome:
        from .ctex_write import write_ctex

        try:
            out.write_bytes(write_ctex(edited.read_bytes(), original.read_bytes()))
        except (ValueError, struct.error, OSError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{edited.name}: {exc}")
        return Outcome(OutcomeKind.OK, 1)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        try:
            (dest / f"{path.stem}.png").write_bytes(to_png(path.read_bytes()))
        except (ValueError, struct.error, OSError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{path.name}: {exc}")
        return Outcome(OutcomeKind.OK, 1)
