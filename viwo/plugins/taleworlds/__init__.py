"""TaleWorlds engine (Mount & Blade II: Bannerlord): `.tpac` asset packages.

Header (36 bytes): magic TPAC, version (1 or 2), package GUID, item count, data offset,
reserved. Items follow in a row: type GUID, asset GUID, [version], name (i32 length, UTF-8),
metadata (u64 size), checksum, then the data segments (absolute offset, actual size, stored
size, two GUIDs, 12 unknown bytes, a storage format byte: 0 raw, 1 LZ4 block) and dependencies
(48 bytes each). Members come out as `<name>.<segment index>.bin`; LZ4 needs the `lz4` package.
"""

from __future__ import annotations

import struct
from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DependencySpec, DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files, safe_member

MAGIC = b"TPAC"
HEADER = 36
LIMIT = 1 << 30
MANIFEST = PluginManifest(
    "taleworlds", "TaleWorlds (Bannerlord)", "0.1.0", engine_type="taleworlds", priority=10
)
MARKERS = ("bannerlord.exe", "taleworlds.mountandblade.launcher.exe", "bannerlord.native.exe")
LZ4 = DependencySpec("lz4", "lz4 (Bannerlord TPAC)", kind="python", import_name="lz4")


def _string(fh) -> str:
    (length,) = struct.unpack("<i", fh.read(4))
    if not 0 <= length < 1 << 16:
        raise ValueError("name length out of range")
    return fh.read(length).decode("utf-8", "replace")


def entries(fh):
    """(name, [(offset, actual size, stored size, format)]) per item."""
    head = fh.read(HEADER)
    if head[:4] != MAGIC:
        raise ValueError("not a TPAC package")
    version, count = struct.unpack_from("<I", head, 4)[0], struct.unpack_from("<I", head, 24)[0]
    if version not in (1, 2) or count > 1 << 20:
        raise ValueError("version or item count out of range")
    for _ in range(count):
        fh.read(32)  # type GUID, asset GUID
        if version > 1:
            fh.read(4)
        name = _string(fh)
        (meta,) = struct.unpack("<Q", fh.read(8))
        if meta > LIMIT:
            raise ValueError("metadata size out of range")
        fh.seek(meta + 8, 1)  # metadata, checksum
        (segments,) = struct.unpack("<i", fh.read(4))
        if not 0 <= segments < 1 << 12:
            raise ValueError("segment count out of range")
        found = []
        for _ in range(segments):
            offset, actual, stored = struct.unpack("<QQQ", fh.read(24))
            fh.seek(44, 1)  # owner GUID, type GUID, 12 unknown bytes
            found.append((offset, actual, stored, fh.read(1)[0]))
        (deps,) = struct.unpack("<i", fh.read(4))
        fh.seek(48 * max(deps, 0), 1)
        yield name, found


def _inflate(data: bytes, actual: int, fmt: int) -> bytes | None:
    if fmt == 0 or (fmt == 1 and len(data) == actual):
        return data
    if fmt != 1:
        return None
    try:
        import lz4.block
    except ImportError:
        return None
    try:
        return lz4.block.decompress(data, uncompressed_size=actual)
    except Exception:  # noqa: BLE001  (lz4 raises its own error types)
        return None


class TpacBuiltin(Unarchiver):
    backend_id, owner, license = "tpac-builtin", "taleworlds", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def dependencies(self):
        return (LZ4,)

    def available(self, os):
        return True, ""  # lz4 only unlocks compressed segments; raw ones come out without it

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        skipped = 0
        try:
            with open(archive, "rb") as fh:
                for name, segments in list(entries(fh)):
                    rel = safe_member(name)
                    if rel is None or ctx.cancel.cancelled:
                        continue
                    for n, (offset, actual, stored, fmt) in enumerate(segments):
                        if actual > LIMIT or stored > LIMIT:
                            raise ValueError("segment size out of range")
                        fh.seek(offset)
                        data = _inflate(fh.read(stored), actual, fmt)
                        if data is None:
                            skipped += 1
                            continue
                        target = dest.joinpath(*rel.parts[:-1], f"{rel.name}.{n}.bin")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad TPAC: {exc}")
        notes = (f"{skipped} LZ4 segment(s) need the 'lz4' Python package",) if skipped else ()
        return Outcome(OutcomeKind.OK, count_files(dest), notes=notes)


PLUGIN = "TaleworldsPlugin"  # discovered by viwo.core.wiring.registry


class TaleworldsPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if any(probe.head(p, 4) == MAGIC for p in probe.with_suffix(".tpac")[:10]):
            evidence.append("TPAC asset packages")
        if probe.has_name(*MARKERS):
            evidence.append("Bannerlord executable")
        score = 0.9 if len(evidence) == 2 else 0.7 if evidence else 0.0
        return DetectionResult("taleworlds", score, tuple(evidence), "taleworlds")

    def slot_definitions(self):
        return (
            SlotDefinition(
                "unarchive.tpac",
                "unarchive",
                "taleworlds",
                "tpac-builtin",
                suffixes=(".tpac",),
                magic=(MAGIC,),
            ),
        )

    def backends(self):
        return (TpacBuiltin(),)
