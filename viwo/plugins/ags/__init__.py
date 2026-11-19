"""Adventure Game Studio: CLIB packfiles (clib.py), alone (`.ags`, `.vox`, `ac2game.dat`) or
appended to the game's executable, every asset out (from the other parts of a multi-file
library too, `game.001`...), and rebuilt in the patched copy (pack.py)."""

from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Match, SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

from .clib import HEAD, TAIL, Lib, read_lib
from .pack import SLOT as PACK_SLOT
from .pack import ClibWriter, copy

MANIFEST = PluginManifest(
    "ags",
    "Adventure Game Studio",
    "0.1.0",
    engine_type="ags",
    priority=13,
    description="AGS games: CLIB packfiles, alone or behind the game's executable",
    capabilities=("detect", "unpack", "pack"),
)
MARKERS = ("acsetup.cfg", "winsetup.exe", "ac2game.dat", "agsfnt0.wfn", "agsfnt0.ttf")


def identify_clib(path: Path, head: bytes, tail: bytes) -> Match | None:
    """A library at the start of a file, or behind an executable (its tail signature)."""
    if head.startswith(HEAD) or (tail.endswith(TAIL) and _readable(path)):
        return Match("unarchive.clib", path)
    return None


def _readable(path: Path) -> bool:
    try:
        read_lib(path)
    except (OSError, ValueError):
        return False
    return True


SLOT = SlotDefinition(
    "unarchive.clib", "unarchive", "ags", "clib-builtin", magic=(HEAD,), identify=identify_clib
)


def _part(archive: Path, lib: Lib, uid: int) -> Path | None:
    """The file holding part `uid` (beside the first), when its name is a plain file name."""
    if uid == 0:
        return archive
    name = lib.parts[uid] if uid < len(lib.parts) else ""
    path = ws.member_path(archive.parent, name)
    return path if path is not None and "/" not in name.replace("\\", "/") else None


def _write(source: Path, offset: int, size: int, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(source, "rb") as src, open(target, "wb") as out:
        copy(src, out, offset, size)  # a megabyte at a time; one cut short is damage


class ClibBuiltin(Unarchiver):
    backend_id, owner, license = "clib-builtin", "ags", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        try:
            lib = read_lib(archive)
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad CLIB: {exc}")
        if lib.index:
            note = f"part {lib.index} of a multi-file library: its assets come out with the first"
            return Outcome(OutcomeKind.OK, 0, notes=(note,))
        names, written, missing = ws.Names(dest), 0, set()
        try:
            for asset in lib.assets:
                if ctx.cancel.cancelled:
                    break
                source = _part(archive, lib, asset.uid)
                if source is None or not source.is_file():
                    missing.add(asset.uid)
                    continue
                target = names.target(asset.name)
                if target is not None:
                    base = lib.base if asset.uid == 0 else 0
                    _write(source, base + asset.offset, asset.size, target)
                    written += 1
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad CLIB: {exc}")
        gone = [lib.parts[u] if u < len(lib.parts) else f"#{u}" for u in sorted(missing)]
        notes = (f"assets of missing parts skipped: {', '.join(gone)}",) if gone else ()
        return Outcome(OutcomeKind.OK, written, notes=notes + names.save())


class AgsPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        packs = probe.with_suffix(".ags", ".vox")[:20]
        if any(probe.head(p, 5) == HEAD for p in packs):
            evidence.append("AGS packfiles (CLIB)")
        if any(probe.tail(p, 12) == TAIL for p in probe.with_suffix(".exe")[:20]):
            evidence.append("AGS packfile behind the game's executable")
        strong = bool(evidence)
        if probe.has_name(*MARKERS):
            evidence.append("AGS setup and runtime files")
        score = 0.9 if strong else (0.6 if evidence else 0.0)
        return DetectionResult("ags", score, tuple(evidence), "ags")

    def slot_definitions(self):
        return (SLOT, PACK_SLOT)

    def backends(self):
        return (ClibBuiltin(), ClibWriter())

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.clib" if unarchive_slot == "unarchive.clib" else ""
