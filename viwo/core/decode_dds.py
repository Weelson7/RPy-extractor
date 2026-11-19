"""decode.image's DDS side (doc 18.3): the way back its two backends share, and its spare.

- `DdsWayBack`: what encode_dds.py cannot write is refused by name from the header; an edited
  PNG is written back as the original's format; BC6H's loss is said with the file.
- `PillowImage` (the spare, in process): a DDS ffmpeg does not read, BC6H and BC7 above all
  (the pinned ffmpeg has no BPTC decoder, so the main says so without starting it), and every
  DDS when ffmpeg is missing. BC6H's HDR colour comes out clamped to 0..1 in 8 bits, said per
  file."""

import struct
from pathlib import Path

from viwo.backends.blocks.encode_bptc import CLAMPED, HDR
from viwo.contracts.slots import Decoder
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

PILLOW = DependencySpec(
    "pillow", "Pillow", kind="python", import_name="PIL", hint="pip install pillow"
)
BPTC = {94: "BC6H", 95: "BC6H", 96: "BC6H", 97: "BC7", 98: "BC7", 99: "BC7"}


def bptc(head: bytes) -> str:
    """The block format of a DDS header naming BC6H or BC7 (DX10), else ""."""
    if head[:4] != b"DDS " or head[84:88] != b"DX10" or len(head) < 132:
        return ""
    return BPTC.get(struct.unpack_from("<I", head, 128)[0], "")


class DdsWayBack(Decoder):
    """The way back of a DDS decoded to PNG (encode_dds.py, encode_bc.py, encode_bptc.py)."""

    encodes = True
    ati2_green = True  # how this decoder shows ATI2: its first block as green (ffmpeg)

    def refuses(self, original: Path) -> str:
        from .encode_dds import layout

        with open(original, "rb") as fh:
            head = fh.read(148)
        try:
            layout(head)
        except ValueError as exc:
            return f"{original.name}: {exc}"
        return ""

    def encode(self, edited: Path, original: Path, out: Path, ctx) -> Outcome:
        from .encode_dds import PREMULT, write_dds

        try:
            source = original.read_bytes()
            out.write_bytes(write_dds(edited.read_bytes(), source, self.ati2_green))
        except (ValueError, OSError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{original.name}: {exc}")
        if bptc(source) == "BC6H":
            notes = (HDR,)
        else:
            notes = (PREMULT,) if source[84:88] in (b"DXT2", b"DXT4") else ()
        return Outcome(OutcomeKind.OK, 1, notes=notes)


class PillowImage(DdsWayBack):
    backend_id, license, ati2_green = "pillow-image", "HPND", False
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process
    requires = (PILLOW,)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        from PIL import Image

        try:
            with Image.open(path) as image:
                image.load()
                keep = image.mode in ("L", "LA", "RGB", "RGBA")
                (image if keep else image.convert("RGBA")).save(dest / f"{path.name}.png")
            with open(path, "rb") as fh:
                hdr = bptc(fh.read(132)) == "BC6H"
        except Exception as exc:  # noqa: BLE001  (any unreadable image: this file's failure)
            return Outcome(OutcomeKind.FAILED, error=f"{path.name}: {exc}"[:300])
        return Outcome(OutcomeKind.OK, 1, notes=(CLAMPED,) if hdr else ())
