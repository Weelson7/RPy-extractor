"""Source engine (Valve) VPK archives: v1 and v2, multi-part (_dir.vpk + _000.vpk...)."""

import struct
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Match, SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

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
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        stem, written, handles = archive.name[: -len("_dir.vpk")], 0, {}
        skipped, names = {"its part file is missing": 0, "cut short": 0}, ws.Names(dest)
        try:
            with open(archive, "rb") as fh:
                head = fh.read(28)
                version, size = struct.unpack_from("<II", head, 4)
                fh.seek(0)  # only the header and directory tree are read into memory
                entries, base = tree(fh.read((12 if version == 1 else 28) + size))
                for path, preload, index, offset, length in entries:
                    if ctx.cancel.cancelled:
                        break
                    source = fh if index == 0x7FFF else _part(handles, archive, stem, index)
                    if source is None:
                        skipped["its part file is missing"] += 1
                        continue
                    source.seek((base if index == 0x7FFF else 0) + offset)
                    data = source.read(length)
                    target = names.target(path)
                    if target is None:
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(preload + data)
                    skipped["cut short"] += len(data) != length
                    written += 1
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad VPK: {exc}")
        finally:
            _close(handles)
        notes = tuple(
            f"{n} entr(ies) skipped or incomplete: {why}" for why, n in skipped.items() if n
        )
        return Outcome(OutcomeKind.OK, written, notes=names.save() + notes)


def _part(handles: dict, archive: Path, stem: str, index: int):
    """Open data part files lazily, keeping only one open at a time."""
    if index not in handles:
        _close(handles)
        part = archive.with_name(f"{stem}_{index:03d}.vpk")
        handles[index] = open(part, "rb") if part.is_file() else None
    return handles[index]


def _close(handles: dict) -> None:
    """Close the open part (a missing part file is kept as None, its entries skipped)."""
    for handle in handles.values():
        if handle is not None:
            handle.close()
    handles.clear()


SLOT = SlotDefinition("unarchive.vpk", "unarchive", "source", "vpk-builtin", identify=identify_vpk)


class SourcePlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        dirs = [p for p in probe.with_suffix(".vpk")[:40] if probe.head(p, 4) == MAGIC]
        evidence = ("Valve VPK archives",) if dirs else ()
        if probe.has_name("gameinfo.txt", "hl2.exe", "srcds.exe"):
            evidence += ("Source engine game files",)
        score = 0.9 if dirs else (0.6 if evidence else 0.0)
        return DetectionResult("source", score, evidence, "source")

    def slot_definitions(self):
        from .pack import SLOT as PACK_SLOT
        from .vtf import SLOT as VTF_SLOT

        return (SLOT, PACK_SLOT, VTF_SLOT)

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.vpk" if unarchive_slot == "unarchive.vpk" else ""

    def backends(self):
        from .pack import VpkWriter
        from .vtf import VtfDecoder

        return (VpkBuiltin(), VpkWriter(), VtfDecoder())

    def claimed_suffixes(self):
        return (".vpk",)  # numbered parts; _dir.vpk files are identified as containers first
