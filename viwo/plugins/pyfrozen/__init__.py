"""Frozen Python applications: PyInstaller (a CArchive appended to a bootloader exe, with an inner
PYZ of modules), py2exe and cx_Freeze (a `library.zip` of modules beside the exe). PyInstaller
onefile exes are read first-party (carchive.py: data files, bundled binaries, top-level modules
and every PYZ module come out as `.pyc`) and rebuilt with edits (pack.py). py2exe/cx_Freeze keep
their modules in `library.zip`, a plain zip the core's zip slot extracts and rebuilds, so this
plugin detects them and leaves that path to the core (said). `decode.pyc` disassembles a `.pyc`
when its magic matches the running interpreter, else writes the bytecode out with a note naming
the version needed (no Python decompiler is pinned)."""

import dis
import importlib.util
import io
import marshal
import struct
import zlib
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Decoder, Match, SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

from . import carchive as c
from .pack import out_name

MANIFEST = PluginManifest(
    "pyfrozen",
    "Frozen Python (PyInstaller, py2exe, cx_Freeze)",
    "0.1.0",
    engine_type="pyfrozen",
    priority=4,
    description="Frozen Python: PyInstaller CArchive/PYZ extracted and rebuilt, .pyc disassembled",
    capabilities=("detect", "unpack", "decode", "pack"),
)
FROZEN_MARKERS = ("library.zip", "python3.dll", "python27.dll", "base_library.zip", "pyvenv.cfg")
PY2EXE = ("python27.dll", "python3.dll", "library.zip")


def identify_pyi(path: Path, head: bytes, tail: bytes) -> Match | None:
    """A PyInstaller onefile exe: the MEI cookie near the end (scanned, not only the tail bytes)."""
    if path.suffix.lower() not in (".exe", "") and not path.suffix.lower().startswith(".so"):
        return None
    with open(path, "rb") as fh:
        fh.seek(max(0, fh.seek(0, 2) - (4 << 20)))
        if c.PKG_MAGIC in fh.read():
            return Match("unarchive.pyi", path)
    return None


class PyiBuiltin(Unarchiver):
    backend_id, owner, license = "pyi-builtin", "pyfrozen", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        try:
            raw = archive.read_bytes()
            start, toc_abs, toc_len, _ = c.find_archive(raw)
            entries = c.toc(raw, toc_abs, toc_len)
            magic = c.pyz_magic(raw, start, entries) or importlib.util.MAGIC_NUMBER
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad PyInstaller exe: {exc}")
        names, written, bad = ws.Names(dest), 0, 0
        for entry in entries:
            if ctx.cancel.cancelled:
                break
            done, failed = _write_entry(raw, start, entry, magic, names)
            written, bad = written + done, bad + failed
        note = (f"{bad} member(s) could not be read (damaged or compressed)",) if bad else ()
        return Outcome(OutcomeKind.OK, written, notes=note + names.save())


def _write_one(names, rel: str, data: bytes) -> int:
    target = names.target(rel)
    if target is None:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return 1


def _write_entry(raw, start, entry, magic, names) -> tuple[int, int]:
    """(members written, members that could not be read) for one CArchive entry."""
    name, dpos, dlen, _, cflag, typ = entry
    try:
        data = c.member_bytes(raw, start, dpos, dlen, cflag)
        if typ in b"zZ":
            mods = c.pyz_modules(data)
            return sum(
                _write_one(names, f"PYZ-contents/{m.replace('.', '/')}.pyc", c.as_pyc(magic, code))
                for m, _, code in mods
            ), 0
        body = c.as_pyc(magic, data) if typ in c.MODULE_TYPES else data
        return _write_one(names, out_name(name, typ), body), 0
    except (ValueError, zlib.error, EOFError, struct.error):  # never silent: counted below
        return 0, 1


class PycDecoder(Decoder):
    backend_id, owner, license = "pyc-builtin", "pyfrozen", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process
    one_way = "no Python decompiler is pinned; the disassembly is a read-only view"

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        raw = path.read_bytes()
        if raw[:4] != importlib.util.MAGIC_NUMBER:
            note = f"{path.name}: bytecode for another Python; disassembly needs that interpreter"
            return Outcome(OutcomeKind.OK, 0, notes=(note,))
        try:
            code = marshal.loads(raw[16:])
            buf = io.StringIO()
            dis.dis(code, file=buf)
            (dest / f"{path.stem}.dis.txt").write_text(buf.getvalue(), encoding="utf-8")
        except (ValueError, EOFError, TypeError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{path.name}: {exc}")
        return Outcome(OutcomeKind.OK, 1)


PYI_SLOT = SlotDefinition(
    "unarchive.pyi", "unarchive", "pyfrozen", "pyi-builtin", identify=identify_pyi
)
PYC_SLOT = SlotDefinition("decode.pyc", "decode", "pyfrozen", "pyc-builtin", suffixes=(".pyc",))


class PyFrozenPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        exes = probe.with_suffix(".exe")[:10]
        if any(c.PKG_MAGIC in probe.tail(p, 1 << 20) for p in exes):
            evidence.append("PyInstaller onefile executable")
        if probe.has_name("library.zip") or probe.has_name("base_library.zip"):
            evidence.append("py2exe / cx_Freeze library.zip")
        strong = bool(evidence)
        if probe.has_name(*FROZEN_MARKERS):
            evidence.append("frozen Python runtime")
        score = 0.85 if strong else (0.4 if evidence else 0.0)
        return DetectionResult("pyfrozen", score, tuple(evidence), "pyfrozen")

    def slot_definitions(self):
        from .pack import SLOT as PACK_SLOT

        return (PYI_SLOT, PYC_SLOT, PACK_SLOT)

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.pyi" if unarchive_slot == "unarchive.pyi" else ""

    def backends(self):
        from .pack import PyiWriter

        return (PyiBuiltin(), PycDecoder(), PyiWriter())
