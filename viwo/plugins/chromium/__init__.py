"""Chromium / CEF / Electron resource packs (`.pak`): the DataPack format, versions 4 and 5
(Chrome, Edge, Brave, Steam, VS Code and the rest build on the same reader). Every resource is
keyed by a numeric id; version 5 adds aliases (two ids that share one resource). The reader
lists each resource as `<id>.dat` (pak.py rebuilds the pack from the edited ids, byte-faithful:
an unchanged pack comes back identical). Encrypted or signed packs are not a thing here; a pack
whose header is neither version 4 nor 5 is refused by name."""

import struct
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Match, SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

MANIFEST = PluginManifest(
    "chromium",
    "Chromium resource pack (.pak)",
    "0.1.0",
    engine_type="chromium",
    priority=4,
    description="Chrome/CEF/Electron .pak resource packs (versions 4 and 5), extract and rebuild",
    capabilities=("detect", "unpack", "pack"),
)
ENCODINGS = {0: "binary", 1: "utf-8", 2: "utf-16"}
MARKERS = ("chrome.exe", "msedge.exe", "brave.exe", "cef.dll", "libcef.dll", "chrome.dll")


def read_pak(raw: bytes) -> tuple[int, int, list[tuple[int, int, int]], list[tuple[int, int]]]:
    """(version, encoding, [(id, start, end)], [(alias id, resource index)]). Offsets absolute."""
    (version,) = struct.unpack_from("<I", raw, 0)
    if version == 4:
        count, encoding = struct.unpack_from("<I", raw, 4)[0], raw[8]
        index, alias_at, aliases = 9, 0, []
    elif version == 5:
        encoding = raw[4]
        count, alias_count = struct.unpack_from("<HH", raw, 8)
        index = 12
        alias_at = index + (count + 1) * 6
        aliases = [struct.unpack_from("<HH", raw, alias_at + i * 4) for i in range(alias_count)]
    else:
        raise ValueError(f"DataPack version {version}: only 4 and 5 are known")
    entries = [struct.unpack_from("<HI", raw, index + i * 6) for i in range(count + 1)]
    resources = [
        (entries[i][0], entries[i][1], entries[i + 1][1]) for i in range(count)
    ]  # id, start, end; the trailing sentinel entry gives the last resource's end
    return version, encoding, resources, aliases


def _ordered(raw: bytes):
    version, encoding, resources, aliases = read_pak(raw)
    for rid, start, end in resources:
        if not 0 <= start <= end <= len(raw):
            raise ValueError("a resource runs past the end of the pack")
    return version, encoding, resources, aliases


class PakBuiltin(Unarchiver):
    backend_id, owner, license = "pak-builtin", "chromium", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        try:
            raw = archive.read_bytes()
            _, encoding, resources, aliases = _ordered(raw)
        except (ValueError, struct.error, IndexError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad .pak: {exc}")
        names = ws.Names(dest)
        written = 0
        for rid, start, end in resources:
            if ctx.cancel.cancelled:
                break
            target = names.target(f"{rid}.dat")
            if target is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw[start:end])
            written += 1
        note = f"encoding {ENCODINGS.get(encoding, encoding)}"
        shared = (f"{len(aliases)} alias id(s) share another resource's data",) if aliases else ()
        return Outcome(OutcomeKind.OK, written, notes=(note,) + shared + names.save())


def identify_pak(path: Path, head: bytes, tail: bytes) -> Match | None:
    """A `.pak` whose header is a DataPack (version 4 or 5). `.pak` is used by other engines
    too (Unreal, Quake), so claim it by the header, not the extension alone."""
    if path.suffix.lower() == ".pak" and _is_pak(head):
        return Match("unarchive.pak", path)
    return None


SLOT = SlotDefinition(
    "unarchive.pak", "unarchive", "chromium", "pak-builtin", identify=identify_pak
)


class ChromiumPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if any(_is_pak(probe.head(p, 12)) for p in probe.with_suffix(".pak")[:20]):
            evidence.append("Chromium .pak resource packs")
        strong = bool(evidence)
        if probe.has_name(*MARKERS):
            evidence.append("Chromium / CEF runtime")
        score = 0.85 if strong else (0.5 if evidence else 0.0)
        return DetectionResult("chromium", score, tuple(evidence), "chromium")

    def slot_definitions(self):
        from .pack import SLOT as PACK_SLOT

        return (SLOT, PACK_SLOT)

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.pak" if unarchive_slot == "unarchive.pak" else ""

    def backends(self):
        from .pack import PakWriter

        return (PakBuiltin(), PakWriter())


def _is_pak(head: bytes) -> bool:
    if len(head) < 8:
        return False
    (version,) = struct.unpack_from("<I", head, 0)
    return version in (4, 5)
