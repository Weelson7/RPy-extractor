"""TaleWorlds engine: `.tpac` asset packages (Mount & Blade II: Bannerlord is its game plugin).

Header (36 bytes): magic TPAC, version (1 or 2), package GUID, item count, data offset,
reserved. Items follow in a row: type GUID, asset GUID, [version], name (i32 length, UTF-8),
metadata (u64 size), checksum, then the data segments (absolute offset, actual size, stored
size, two GUIDs, 12 unknown bytes, a storage format byte: 0 raw, 1 LZ4 block) and dependencies
(48 bytes each). Textures come out as `<name>.dds` (textures.py); every other item as
`<name>.<segment index>.bin`. LZ4 needs the `lz4` package.
"""

from __future__ import annotations

import struct
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DependencySpec, DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files

from .textures import CUBE_TAG, TEXTURE, dds, shape

MAGIC = b"TPAC"
HEADER = 36
LIMIT = 1 << 30
MANIFEST = PluginManifest(
    "taleworlds", "TaleWorlds", "0.1.0", engine_type="taleworlds", priority=10
)
LZ4 = DependencySpec("lz4", "lz4 (TaleWorlds TPAC)", kind="python", import_name="lz4")


def _string(fh) -> str:
    (length,) = struct.unpack("<i", fh.read(4))
    if not 0 <= length < 1 << 16:
        raise ValueError("name length out of range")
    return fh.read(length).decode("utf-8", "replace")


def entries(fh):
    """(name, [(offset, actual size, stored size, format)], type GUID, metadata) per item; the
    metadata is read for textures only (the rest is skipped)."""
    head = fh.read(HEADER)
    if head[:4] != MAGIC:
        raise ValueError("not a TPAC package")
    version, count = struct.unpack_from("<I", head, 4)[0], struct.unpack_from("<I", head, 24)[0]
    if version not in (1, 2) or count > 1 << 20:
        raise ValueError("version or item count out of range")
    for _ in range(count):
        kind = fh.read(32)[:16]  # type GUID, asset GUID
        if version > 1:
            fh.read(4)
        name = _string(fh)
        (meta,) = struct.unpack("<Q", fh.read(8))
        if meta > LIMIT:
            raise ValueError("metadata size out of range")
        blob = b""
        if kind == TEXTURE and meta < 1 << 16:
            blob = fh.read(meta)
        else:
            fh.seek(meta, 1)
        fh.seek(8, 1)  # checksum
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
        yield name, found, kind, blob


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

    requires = (LZ4,)

    def available(self, os):
        return True, ""  # lz4 only unlocks compressed segments; raw ones come out without it

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        counts, names = {"lz4": 0, "raw texture": 0, "cut": 0}, ws.Names(dest)
        try:
            with open(archive, "rb") as fh:
                for name, segments, kind, meta in list(entries(fh)):
                    if ctx.cancel.cancelled:
                        break
                    target = names.target(name)
                    if target is not None:
                        _item(fh, target, segments, (kind, meta), counts)
        except (OSError, ValueError, IndexError, struct.error) as exc:  # IndexError: cut short
            return Outcome(OutcomeKind.FAILED, error=f"bad TPAC: {exc}")
        notes = [f"{counts['lz4']} LZ4 segment(s) need the 'lz4' Python package"]
        notes.append(f"{counts['raw texture']} texture(s) of an unknown shape kept as raw .bin")
        notes.append(f"{counts['cut']} segment(s) past the end of the package (cut short)")
        files = count_files(dest)
        notes = tuple(n for n in notes if n[0] != "0") + names.save()
        return Outcome(OutcomeKind.OK, files, notes=notes)


def _segment(fh, segment, counts: dict) -> bytes | None:
    offset, actual, stored, fmt = segment
    if actual > LIMIT or stored > LIMIT:
        raise ValueError("segment size out of range")
    fh.seek(offset)
    raw = fh.read(stored)
    if len(raw) < stored:  # the package was cut short: said, never written as a stub
        counts["cut"] += 1
        return None
    data = _inflate(raw, actual, fmt)
    counts["lz4"] += data is None
    return data


def _item(fh, target: Path, segments: list, typed: tuple[bytes, bytes], counts: dict) -> None:
    """A texture as one DDS (its largest chain); anything else, or a texture whose shape is
    not recognised (counted), as one .bin per segment."""
    target.parent.mkdir(parents=True, exist_ok=True)
    kind, meta = typed
    if kind == TEXTURE and segments:
        faces = 6 if CUBE_TAG in meta else 1
        data = _segment(fh, max(segments, key=lambda s: s[1]), counts)
        found = shape(meta, len(data), faces) if data is not None else None
        if found:
            target.with_name(f"{target.name}.dds").write_bytes(dds(data, *found, faces))
            return
        counts["raw texture"] += 1
    for n, segment in enumerate(segments):
        data = _segment(fh, segment, counts)
        if data is not None:
            target.with_name(f"{target.name}.{n}.bin").write_bytes(data)


PLUGIN = "TaleworldsPlugin"  # discovered by viwo.core.wiring.registry


class TaleworldsPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        """The engine's own signature (TPAC packages), never a game's executable name."""
        found = any(probe.head(p, 4) == MAGIC for p in probe.with_suffix(".tpac")[:10])
        evidence = ("TPAC asset packages",) if found else ()
        return DetectionResult("taleworlds", 0.85 if found else 0.0, evidence, "taleworlds")

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
