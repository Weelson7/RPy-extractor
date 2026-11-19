"""XNA, FNA and MonoGame: the game's compiled content is loose `.xnb` files (xnb.py), copied as
they are; `decode.xnb` turns a Texture2D into PNG and a SoundEffect into WAV (content.py) and
writes an edited one back into the XNB, compressed as it was. Other content types, LZX
compression and XNA 3.x files are refused by name."""

import struct
from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import DependencySpec, DetectionResult, Outcome, OutcomeKind

from .content import sound_back, sound_wav, texture, texture_back, texture_png
from .xnb import READERS, read_xnb, refusal, write_xnb

MANIFEST = PluginManifest(
    "xna",
    "XNA / FNA / MonoGame",
    "0.1.0",
    engine_type="xna",
    priority=13,
    description="XNA, FNA and MonoGame games: .xnb textures to PNG and sounds to WAV, and back",
    capabilities=("detect", "decode"),
)
PILLOW = DependencySpec(
    "pillow", "Pillow", kind="python", import_name="PIL", hint="pip install Pillow"
)
LZ4 = DependencySpec(
    "lz4", "lz4 (LZ4 XNB)", kind="python", import_name="lz4", hint="pip install lz4"
)
SLOT = SlotDefinition("decode.xnb", "decode", "xna", "xnb-builtin", suffixes=(".xnb",))
FRAMEWORKS = ("microsoft.xna.framework.dll", "fna.dll", "monogame.framework.dll")


def _lz4():
    try:
        import lz4.block

        return lz4
    except ImportError:
        return None


def _open(path: Path):
    xnb = read_xnb(path.read_bytes(), _lz4())
    if xnb.reader not in READERS:
        raise ValueError(
            f"holds {xnb.reader or 'no object'}: only Texture2D and SoundEffect convert"
        )
    return xnb


class XnbDecoder(Decoder):
    backend_id, owner, license = "xnb-builtin", "xna", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process
    encodes = True  # an edited PNG or WAV back into its XNB (doc 18.3)

    def dependencies(self):
        return (PILLOW, LZ4)

    def available(self, os) -> tuple[bool, str]:
        return True, ""  # Pillow is needed for textures, lz4 for LZ4 files: said per file

    def refuses(self, original: Path) -> str:
        with open(original, "rb") as fh:
            why = refusal(fh.read(10), _lz4())
        if not why:
            try:
                xnb = _open(original)
                if xnb.reader == READERS[0]:
                    texture(xnb.body, xnb.start)
            except (OSError, ValueError, IndexError) as exc:
                why = str(exc)
        return f"{original.name}: {why}" if why else ""

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        try:
            xnb = _open(path)
            if xnb.reader == READERS[0]:
                (dest / f"{path.stem}.png").write_bytes(texture_png(xnb.body, xnb.start))
            else:
                (dest / f"{path.stem}.wav").write_bytes(sound_wav(xnb.body, xnb.start))
        except ImportError:
            return Outcome(OutcomeKind.UNAVAILABLE, error=f"{path.name}: {PILLOW.hint}")
        except (OSError, ValueError, IndexError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{path.name}: {exc}")
        return Outcome(OutcomeKind.OK, 1)

    def encode(self, edited: Path, original: Path, out: Path, ctx) -> Outcome:
        try:
            xnb = _open(original)
            back = texture_back if xnb.reader == READERS[0] else sound_back
            content, end = back(edited.read_bytes(), xnb.body, xnb.start)
            out.write_bytes(write_xnb(xnb, content, end, _lz4()))
        except ImportError:
            return Outcome(OutcomeKind.UNAVAILABLE, error=f"{edited.name}: {PILLOW.hint}")
        except (OSError, ValueError, IndexError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{edited.name}: {exc}")
        return Outcome(OutcomeKind.OK, 1)


class XnaPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if any(probe.head(p, 3) == b"XNB" for p in probe.with_suffix(".xnb")[:20]):
            evidence.append("XNB content files")
        strong = bool(evidence)
        if probe.has_name(*FRAMEWORKS):
            evidence.append("XNA, FNA or MonoGame framework")
        score = 0.9 if strong else (0.6 if evidence else 0.0)
        return DetectionResult("xna", score, tuple(evidence), "xna")

    def slot_definitions(self):
        return (SLOT,)

    def backends(self):
        return (XnbDecoder(),)
