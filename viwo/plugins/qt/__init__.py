"""Qt applications (Qt 5 and Qt 6): the Qt resource system. Standalone `.rcc` files are read and
rebuilt first-party (rcc.py: the `qresource` tree, zlib blobs; zstd blobs reported). `.qm`
compiled translations are read into JSON for viewing (qm.py, one way). Resources compiled into an
executable or DLL have no standalone header: `viwo qt-resources BINARY` carves their textual QML,
JS, QSS and SVG by content (binres.py), named by kind, since a stripped binary keeps no tree.

Free Download Manager is such an app: its QML UI is compiled into fdm.exe and comes out this way;
its connection limit, however, is enforced in native code (the setting key
`MaxConnectionsPerServerLimit`), not in a resource, so that change is a binary patch (doc 18.8),
not a resource edit."""

import json
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import CliCommand, EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Decoder, SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

from . import binres, qm, rcc

MANIFEST = PluginManifest(
    "qt",
    "Qt (rcc, QML, .qm)",
    "0.1.0",
    engine_type="qt",
    priority=3,
    description="Qt apps: .rcc and .qm read, embedded QML carved, .rcc rebuilt",
    capabilities=("detect", "unpack", "decode", "pack"),
)
QT_DLLS = ("qt6core.dll", "qt5core.dll", "libqt6core.so.6", "libqt5core.so.5", "qtcore4.dll")


class RccBuiltin(Unarchiver):
    backend_id, owner, license = "rcc-builtin", "qt", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        try:
            entries = rcc.extract(archive.read_bytes())
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad rcc: {exc}")
        names, written, skipped = ws.Names(dest), 0, 0
        for path, content, note in entries:
            if ctx.cancel.cancelled:
                break
            target = names.target(path) if not note else None
            if target is None:
                skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            written += 1
        notes = (f"{skipped} resource(s) could not be read (zstd or damaged)",) if skipped else ()
        return Outcome(OutcomeKind.OK, written, notes=notes + names.save())


class QmDecoder(Decoder):
    backend_id, owner, license = "qm-builtin", "qt", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process
    one_way = "a .qm's lookup hashes are not re-authored; edit the .ts source and recompile"

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        try:
            (dest / f"{path.stem}.qm.json").write_bytes(qm.to_json(path.read_bytes()))
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{path.name}: {exc}")
        return Outcome(OutcomeKind.OK, 1)


RCC_SLOT = SlotDefinition(
    "unarchive.rcc", "unarchive", "qt", "rcc-builtin", suffixes=(".rcc",), magic=(rcc.MAGIC,)
)
QM_SLOT = SlotDefinition("decode.qm", "decode", "qt", "qm-builtin", suffixes=(".qm",))


def _carve_cmd(rt, args) -> dict:
    data = Path(args.binary).read_bytes()
    found = binres.carve(data)
    out = Path(args.out) if args.out else None
    if out is not None:
        for name, content in found:
            target = ws.member_path(out, name)
            if target is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
    return {"binary": Path(args.binary).name, "carved": len(found), "names": [n for n, _ in found]}


def _build(parser) -> None:
    parser.add_argument("binary", type=Path, help="an executable or DLL with embedded Qt resources")
    parser.add_argument("--out", help="a folder to write the carved resources into")


class QtPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if any(probe.head(p, 4) == rcc.MAGIC for p in probe.with_suffix(".rcc")[:20]):
            evidence.append("Qt resource collections (.rcc)")
        if any(probe.head(p, 16) == qm.MAGIC for p in probe.with_suffix(".qm")[:20]):
            evidence.append("Qt compiled translations (.qm)")
        strong = bool(evidence)
        if probe.has_name(*QT_DLLS):
            evidence.append("Qt runtime")
        score = 0.85 if strong else (0.55 if evidence else 0.0)
        return DetectionResult("qt", score, tuple(evidence), "qt")

    def slot_definitions(self):
        from .pack import SLOT as PACK_SLOT

        return (RCC_SLOT, QM_SLOT, PACK_SLOT)

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.rcc" if unarchive_slot == "unarchive.rcc" else ""

    def backends(self):
        from .pack import RccWriter

        return (RccBuiltin(), QmDecoder(), RccWriter())

    def cli_commands(self):
        return (
            CliCommand(
                "qt-resources",
                "carve embedded QML/JS/QSS/SVG resources from a Qt binary",
                _build,
                _carve_cmd,
                formatter=lambda d: json.dumps(d, indent=2),
            ),
        )
