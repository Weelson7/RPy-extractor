"""Java applications: `.jar`, `.war` and `.ear` archives (zip with a `META-INF/` manifest). They
extract and rebuild through the stdlib zip path (every entry kept, edited ones replaced, the
compression method preserved), so resources, `.properties`, `.class` bytecode and manifests all
come out and go back. The engine loads nothing over a jar: it is rewritten in the patched copy
(doc 18.3), read back after writing.

No bytecode decompiler is pinned (`viwo/data/tools.json` has a JDK for Ghidra and ILSpy for .NET,
but no CFR/Procyon/Fernflower), so `.class` files are extracted and repacked as bytes, not
decompiled to source: said here and in CONFORMANCE rather than shipped half-done."""

from viwo.backends.archives import ZipBackend
from viwo.backends.packers import ZipPacker
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import DetectionResult

MANIFEST = PluginManifest(
    "java",
    "Java (jar / war / ear)",
    "0.1.0",
    engine_type="java",
    priority=3,
    description="Java .jar/.war/.ear archives: extract and rebuild (no class decompiler pinned)",
    capabilities=("detect", "unpack", "pack"),
)
SUFFIXES = (".jar", ".war", ".ear")
RUNTIMES = ("java.exe", "javaw.exe", "jvm.dll", "libjvm.so", "server/libjvm.so")


class JarBackend(ZipBackend):
    backend_id, owner, license = "jar-builtin", "java", "PSF-2.0"


class JarPacker(ZipPacker):
    backend_id, owner, license = "jar-packer", "java", "PSF-2.0"


SLOTS = (
    SlotDefinition("unarchive.jar", "unarchive", "java", "jar-builtin", suffixes=SUFFIXES),
    SlotDefinition("pack.jar", "pack", "java", "jar-packer"),
)


class JavaPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        jars = [p for suffix in SUFFIXES for p in probe.with_suffix(suffix)[:20]]
        if any(probe.head(p, 2) == b"PK" for p in jars[:20]):
            evidence.append("Java archives (.jar/.war/.ear)")
        strong = bool(evidence)
        if probe.has_name(*RUNTIMES):
            evidence.append("Java runtime")
        score = 0.85 if strong else (0.5 if evidence else 0.0)
        return DetectionResult("java", score, tuple(evidence), "java")

    def slot_definitions(self):
        return SLOTS

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.jar" if unarchive_slot == "unarchive.jar" else ""

    def backends(self):
        return (JarBackend(), JarPacker())
