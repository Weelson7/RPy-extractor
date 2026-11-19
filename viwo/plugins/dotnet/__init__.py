""".NET assemblies (PE files with a CLI header): managed resources are listed and extracted
first-party (pe.py + meta.py walk the ECMA-335 metadata to the ManifestResource table), and an
edited resource is written back in the patched copy in place when its size is unchanged
(pack.py). The decompiled C# is the static view through the pinned ILSpy handoff (doc 6, rung
A2): this plugin proposes each managed assembly as a `dotnet_assembly` analysis target; it does
not re-author a decompiler. Linked (non-embedded) resources and IL2CPP games are named, not
rebuilt here."""

from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.analysis import AnalysisTarget
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Match, SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

from . import pe, resources

MANIFEST = PluginManifest(
    "dotnet",
    ".NET (managed resources)",
    "0.1.0",
    engine_type="dotnet",
    priority=3,
    description=".NET assemblies: managed resources extracted and written back, C# via ILSpy",
    capabilities=("detect", "unpack", "pack"),
)
RUNTIMES = ("clr.dll", "coreclr.dll", "mscoree.dll", "hostfxr.dll", "mscorlib.dll")


def identify_managed(path: Path, head: bytes, tail: bytes) -> Match | None:
    if path.suffix.lower() not in (".dll", ".exe"):
        return None
    try:
        with open(path, "rb") as fh:
            if pe.has_cli(fh.read(4096)):
                return Match("unarchive.dotnet", path)
    except OSError:
        return None
    return None


class DotnetResources(Unarchiver):
    backend_id, owner, license = "dotnet-resources", "dotnet", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        try:
            raw = archive.read_bytes()
            listed = resources.listed(raw)
        except (OSError, ValueError, IndexError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad .NET assembly: {exc}")
        names, written, linked = ws.Names(dest), 0, 0
        for name, offset, length, embedded in listed:
            if ctx.cancel.cancelled:
                break
            if not embedded:
                linked += 1
                continue
            res_off = resources.blob_offset(raw)
            target = names.target(f"resources/{name}")
            if target is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw[res_off + offset + 4 : res_off + offset + 4 + length])
                written += 1
        note = (
            (f"{linked} linked resource(s) live in another file (named, not extracted)",)
            if linked
            else ()
        )
        return Outcome(OutcomeKind.OK, written, notes=note + names.save())


SLOT = SlotDefinition(
    "unarchive.dotnet", "unarchive", "dotnet", "dotnet-resources", identify=identify_managed
)


class DotnetPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        managed = [p for p in (probe.with_suffix(".dll") + probe.with_suffix(".exe"))[:30]]
        if any(pe.has_cli(probe.head(p, 4096)) for p in managed):
            evidence.append("managed .NET assemblies")
        strong = bool(evidence)
        if probe.has_name(*RUNTIMES):
            evidence.append(".NET runtime")
        score = 0.8 if strong else (0.45 if evidence else 0.0)
        return DetectionResult("dotnet", score, tuple(evidence), "dotnet")

    def slot_definitions(self):
        from .pack import SLOT as PACK_SLOT

        return (SLOT, PACK_SLOT)

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.resources" if unarchive_slot == "unarchive.dotnet" else ""

    def backends(self):
        from .pack import ResourcesWriter

        return (DotnetResources(), ResourcesWriter())

    def analysis_targets(self, probe: GameProbe):
        out = []
        for path in (probe.with_suffix(".dll") + probe.with_suffix(".exe"))[:50]:
            if pe.has_cli(probe.head(path, 4096)):
                out.append(
                    AnalysisTarget(
                        key=path.stem.lower(),
                        kind="dotnet_assembly",
                        paths=(path,),
                        owner="dotnet",
                        label=path.name,
                    )
                )
        return out
