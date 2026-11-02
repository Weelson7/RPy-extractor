"""Source engine (Valve) VPK archives: v1 and v2, multi-part (_dir.vpk + _000.vpk...)."""

from __future__ import annotations

import struct
from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Match, SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import safe_member

MAGIC = struct.pack("<I", 0x55AA1234)
MANIFEST = PluginManifest(
    "source", "Source engine (VPK)", "0.1.0", engine_type="source", priority=12
)


def _cstr(blob: bytes, pos: int) -> tuple[str, int]:
    end = blob.index(b"\0", pos)
    return blob[pos:end].decode("utf-8", "replace"), end + 1


def tree(blob: bytes):
    """(path, crc, preload, archive index, offset, length), and the data base offset."""
    version, size = struct.unpack_from("<II", blob, 4)
    header = 12 if version == 1 else 28
    pos, end, entries = header, header + size, []
    while pos < end:
        ext, pos = _cstr(blob, pos)
        if not ext:
            break
        while True:
            folder, pos = _cstr(blob, pos)
            if not folder:
                break
            while True:
                name, pos = _cstr(blob, pos)
                if not name:
                    break
                _, preload, index, offset, length, _ = struct.unpack_from("<IHHIIH", blob, pos)
                pos += 18
                where = "" if folder == " " else f"{folder}/"
                path = f"{where}{name}{'' if ext == ' ' else '.' + ext}"
                entries.append((path, blob[pos : pos + preload], index, offset, length))
                pos += preload
    return entries, end


def identify_vpk(path: Path, head: bytes, tail: bytes) -> Match | None:
    return Match("unarchive.vpk", path) if head.startswith(MAGIC) else None


class VpkBuiltin(Unarchiver):
    backend_id, owner, license = "vpk-builtin", "source", "MIT"

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        stem, written, handles = archive.name[: -len("_dir.vpk")], 0, {}
        try:
            with open(archive, "rb") as fh:
                head = fh.read(28)
                version, size = struct.unpack_from("<II", head, 4)
                fh.seek(0)  # only the header and directory tree are read into memory
                entries, base = tree(fh.read((12 if version == 1 else 28) + size))
                for path, preload, index, offset, length in entries:
                    rel = safe_member(path)
                    if rel is None or ctx.cancel.cancelled:
                        continue
                    source = fh if index == 0x7FFF else _part(handles, archive, stem, index)
                    if source is None:
                        continue
                    source.seek((base if index == 0x7FFF else 0) + offset)
                    target = dest.joinpath(*rel.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(preload + source.read(length))
                    written += 1
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad VPK: {exc}")
        finally:
            for handle in handles.values():
                handle.close()
        return Outcome(OutcomeKind.OK, written)


def _part(handles: dict, archive: Path, stem: str, index: int):
    """Open data part files lazily, keeping only one open at a time."""
    if index not in handles:
        for handle in handles.values():
            handle.close()
        handles.clear()
        part = archive.with_name(f"{stem}_{index:03d}.vpk")
        handles[index] = open(part, "rb") if part.is_file() else None
    return handles[index]


SLOT = SlotDefinition("unarchive.vpk", "unarchive", "source", "vpk-builtin", identify=identify_vpk)


class SourcePlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        dirs = [p for p in probe.with_suffix(".vpk")[:40] if probe.head(p, 4) == MAGIC]
        evidence = ("Valve VPK archives",) if dirs else ()
        if probe.has_name("gameinfo.txt", "hl2.exe", "srcds.exe"):
            evidence += ("Source engine game files",)
        score = 0.9 if dirs else (0.6 if evidence else 0.0)
        return DetectionResult("source", score, evidence, "source")

    def slot_definitions(self):
        return (SLOT,)

    def backends(self):
        return (VpkBuiltin(),)

    def claimed_suffixes(self):
        return (".vpk",)  # numbered parts; _dir.vpk files are identified as containers first
