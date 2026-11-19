"""Kaitai declarative plugins (doc 13.2): a second plugin form. Instead of a hand-written reader,
ViWo reads a Kaitai Struct `.ksy` definition (bundled under `defs/`) with its own first-party
interpreter (`ksy.py`, stdlib only, never the GPL kaitai compiler) and surfaces each as a
`decode.kaitai_<id>` slot that parses a matching file into a structured JSON tree. It is a
read-only structured view: there is no general way back from a parse tree, so every such decoder
is one way.

The plugin is not an engine: it detects nothing (confidence 0) and its decoders run only when it
is selected for a run (`--plugin kaitai`), so no normal extraction is surprised by them. The
bundled proof is `defs/wav.ksy` (WAV/RIFF), which exercises seq, user types, sized fields, a
repeat to the end of the stream, little-endian integers and an enum."""

import json
import struct
from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

from .ksy import load_ksy, parse

MANIFEST = PluginManifest(
    "kaitai",
    "Kaitai declarative",
    "0.1.0",
    engine_type="kaitai",
    priority=1,
    description="Declarative .ksy format definitions parsed to a JSON tree (a second plugin form)",
    capabilities=("detect", "decode"),
)
DEFS = Path(__file__).resolve().parent / "defs"
ONE_WAY = "a Kaitai parse tree is a read-only structured view: there is no way back to the bytes"


def _load() -> list[tuple[str, dict]]:
    """(id, definition) for every bundled `.ksy`, by file name."""
    out = []
    for path in sorted(DEFS.glob("*.ksy")):
        out.append((path.stem, load_ksy(path.read_text(encoding="utf-8"))))
    return out


class KsyDecoder(Decoder):
    owner, license, one_way = "kaitai", "MIT", ONE_WAY
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def __init__(self, name: str, ksy: dict) -> None:
        self.backend_id, self.ksy = f"kaitai-{name}", ksy

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        try:
            tree = parse(self.ksy, path.read_bytes())
            (dest / f"{path.stem}.json").write_text(json.dumps(tree, indent=2), encoding="utf-8")
        except (OSError, ValueError, KeyError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{path.name}: {exc}")
        return Outcome(OutcomeKind.OK, 1)


class KaitaiPlugin(EnginePlugin):
    manifest = MANIFEST

    def _defs(self):
        return _load()

    def detect(self, probe: GameProbe) -> DetectionResult:
        return DetectionResult("kaitai", 0.0, (), "kaitai")  # a form, not an engine

    def slot_definitions(self):
        defs = []
        for name, ksy in self._defs():
            suffix = "." + str((ksy.get("meta") or {}).get("file-extension", name)).lstrip(".")
            defs.append(
                SlotDefinition(
                    f"decode.kaitai_{name}",
                    "decode",
                    "kaitai",
                    f"kaitai-{name}",
                    suffixes=(suffix.lower(),),
                )
            )
        return tuple(defs)

    def backends(self):
        return tuple(KsyDecoder(name, ksy) for name, ksy in self._defs())
