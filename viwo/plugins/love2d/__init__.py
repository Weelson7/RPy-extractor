"""LÖVE (Love2D): the game is a zip, either alone (`game.love`, run by `love.exe`) or fused onto
the engine's executable (`copy /b love.exe+game.love game.exe`: the zip appended to the
executable, its offsets relative to its own start). Both unpack through Python's zipfile, which
finds a zip behind other bytes. The way back rebuilds the zip in the patched copy, after the
executable's own bytes when fused (its offsets then count from the file's start, which LÖVE's
PhysFS reads as well as the fused form: it works out what lies before the zip). LÖVE reads loose
files only from the game's save folder, outside the game and shared with it, so it has no mod
form. Read back by unpacking it again."""

import os
import zipfile
from pathlib import Path

from viwo.backends.archives import ZipBackend
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Match, Packer, SlotDefinition
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

MANIFEST = PluginManifest(
    "love2d",
    "LÖVE (Love2D)",
    "0.1.0",
    engine_type="love2d",
    priority=14,
    description="LÖVE games: the .love zip, alone or fused onto the executable",
    capabilities=("detect", "unpack", "pack"),
)
END = b"PK\x05\x06"  # a zip's end-of-central-directory record
RUNTIME = "love.dll"  # beside every Windows build of LÖVE, fused or not


def fused(path: Path, tail: bytes) -> bool:
    """An executable with a zip appended and LÖVE's library beside it."""
    if path.suffix.lower() != ".exe" or not (path.parent / RUNTIME).is_file():
        return False
    at = tail.rfind(END)
    return (
        at >= 0
        and at + 22 <= len(tail)
        and at + 22 + int.from_bytes(tail[at + 20 : at + 22], "little") == len(tail)
    )


def identify_love(path: Path, head: bytes, tail: bytes) -> Match | None:
    if path.name.lower().endswith(".love") and head.startswith(b"PK"):
        return Match("unarchive.love", path)
    return Match("unarchive.love", path) if fused(path, tail) else None


SLOTS = (
    SlotDefinition("unarchive.love", "unarchive", "love2d", "love-zip", identify=identify_love),
    SlotDefinition("pack.love", "pack", "love2d", "love-pack"),
)


class LoveZip(ZipBackend):
    """The game's zip, alone or behind the executable (zipfile finds where it starts)."""

    backend_id, owner, license = "love-zip", "love2d", "PSF-2.0"


def _start(src: zipfile.ZipFile, size: int) -> int:
    """Where the zip starts in its file: its first local header (the executable's end)."""
    return min((info.header_offset for info in src.infolist()), default=size)


class LovePacker(Packer):
    """The zip rebuilt with the edited members, behind the executable's bytes when fused."""

    backend_id, owner, license = "love-pack", "love2d", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: reads the game's zip

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            with zipfile.ZipFile(container) as src, open(temp, "wb") as fh:
                start = _start(src, container.stat().st_size)
                with open(container, "rb") as exe:
                    fh.write(exe.read(start))  # the executable, or nothing for a .love
                with zipfile.ZipFile(fh, "w") as out:  # the zip after those bytes
                    for info in src.infolist():
                        edited = members.get(info.filename)
                        data = edited.read_bytes() if edited is not None else src.read(info)
                        out.writestr(info, data, compress_type=info.compress_type)
                    for name in sorted(set(members) - set(src.namelist())):
                        out.write(members[name], name, compress_type=zipfile.ZIP_DEFLATED)
            os.replace(temp, container)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=f"{container.name}: {exc}"[:300])
        how = "after the executable's own bytes" if start else "as the .love"
        return Outcome(OutcomeKind.OK, len(members), notes=(f"zip rebuilt {how}",))


class Love2dPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if any(probe.head(p, 2) == b"PK" for p in probe.with_suffix(".love")[:20]):
            evidence.append("LÖVE game archive (.love)")
        exes = probe.with_suffix(".exe")[:20]
        if any(fused(p, probe.tail(p, 64)) for p in exes):
            evidence.append("LÖVE game fused onto its executable")
        strong = bool(evidence)
        if probe.has_name(RUNTIME):
            evidence.append("LÖVE runtime (love.dll)")
        if probe.has_name("main.lua") and probe.has_name("conf.lua"):
            evidence.append("LÖVE game sources (main.lua, conf.lua)")
        score = 0.9 if strong else (0.6 if evidence else 0.0)
        return DetectionResult("love2d", score, tuple(evidence), "love2d")

    def slot_definitions(self):
        return SLOTS

    def backends(self):
        return (LoveZip(), LovePacker())

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.love" if unarchive_slot == "unarchive.love" else ""
