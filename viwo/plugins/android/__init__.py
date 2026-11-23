"""Android packages, static arm only (owner, 2026-11-23: APK support, no mobile runtime). An APK
is a zip whose root holds a binary `AndroidManifest.xml`: identified by that content, whatever
its name. The bundle forms (`.xapk`, `.apks`, `.apkm`: zips of APKs and expansion files) unpack
to their APKs and OBBs, which the unpack loop then opens in turn; an OBB expansion file is a zip
(a Godot `.pck` or anything else is left to the readers that know it). Binary XML and
`resources.arsc` decode to text XML and JSON and go back (decoders.py); the packages are rebuilt
member-faithful and zipaligned, an APK then re-signed (pack.py, sign.py). The engines inside
(Unity, Unreal, Godot) are found by the wrapper re-detection (doc 3.1). `classes.dex` is
extracted, not decompiled: no dex decompiler is pinned. Nothing here touches a device."""

import zipfile
from pathlib import Path

from viwo.backends.archives import ZipBackend
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest, PluginOption
from viwo.contracts.slots import Match, SlotDefinition
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

from .axml import is_axml
from .decoders import SLOTS as DECODE_SLOTS
from .decoders import ArscDecoder, AxmlDecoder
from .pack import SLOTS as PACK_SLOTS
from .pack import ApkPacker, BundlePacker, ObbPacker

MANIFEST = PluginManifest(
    "android",
    "Android packages (APK, OBB, XAPK/APKS/APKM)",
    "0.1.0",
    engine_type="android",
    priority=12,
    options=(
        PluginOption("keystore", "Keystore that signs a rebuilt APK (empty: debug key)", "path"),
        PluginOption("key_alias", "Alias of the signing key in that keystore", "string"),
        PluginOption("keystore_password", "Password of the keystore", "secret"),
        PluginOption("key_password", "Password of the key (empty: the keystore's)", "secret"),
    ),
    description="Android APK/OBB/bundles: unpack, binary XML and resources.arsc decoded and "
    "back, rebuilt zipaligned and re-signed (static only, no device)",
    capabilities=("detect", "unpack", "decode", "pack"),
    dependencies=("uber-apk-signer",),
)
LOCAL = b"PK\x03\x04"
MANIFEST_NAME = "AndroidManifest.xml"
BUNDLES = (".xapk", ".apks", ".apkm")
BUNDLE_MARKS = ("manifest.json", "info.json", "toc.pb")
PACKAGES = (".apk", *BUNDLES, ".obb")


def _kind(path: Path) -> str:
    """ "apk", "apks" (a bundle) or "" from the zip's own members."""
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if MANIFEST_NAME in names:
            with zf.open(MANIFEST_NAME) as fh:
                return "apk" if is_axml(fh.read(8)) else ""
    apks = any(n.lower().endswith(".apk") for n in names)
    marked = path.suffix.lower() in BUNDLES or any(n in BUNDLE_MARKS for n in names)
    return "apks" if apks and marked else ""


def identify_android(path: Path, head: bytes, tail: bytes) -> Match | None:
    if not head.startswith(LOCAL):
        return None
    try:
        kind = _kind(path)
    except (OSError, ValueError, EOFError, RuntimeError, NotImplementedError, zipfile.BadZipFile):
        return None
    if kind:
        return Match(f"unarchive.{kind}", path)
    return Match("unarchive.obb", path) if path.suffix.lower() == ".obb" else None


class ApkZip(ZipBackend):
    backend_id, owner, license = "apk-zip", "android", "PSF-2.0"


class BundleZip(ZipBackend):
    """A bundle's APKs and OBBs; an encrypted one (some `.apkm`) needs its key, never broken."""

    backend_id, owner, license = "apks-zip", "android", "PSF-2.0"

    def extract(self, archive, dest, ctx) -> Outcome:
        try:
            with zipfile.ZipFile(archive) as zf:
                locked = any(info.flag_bits & 0x1 for info in zf.infolist())
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc)[:300])
        if locked:
            return Outcome(OutcomeKind.NEEDS_KEY, error="the bundle's members are encrypted")
        return super().extract(archive, dest, ctx)


class ObbZip(ZipBackend):
    backend_id, owner, license = "obb-zip", "android", "PSF-2.0"


def _unarchive(kind: str, backend: str) -> SlotDefinition:
    return SlotDefinition(f"unarchive.{kind}", "unarchive", "android", backend,
                          identify=identify_android if kind == "apk" else None)  # fmt: skip


SLOTS = (_unarchive("apk", "apk-zip"), _unarchive("apks", "apks-zip"), _unarchive("obb", "obb-zip"))
PACKS = {"unarchive.apk": "pack.apk", "unarchive.apks": "pack.apks", "unarchive.obb": "pack.obb"}


class AndroidPlugin(EnginePlugin):
    manifest = MANIFEST

    def __init__(self) -> None:
        self.signing: dict = {}  # [options.android], shared with the APK packer

    def configure(self, options) -> None:
        self.signing.clear()
        self.signing.update({k: v for k, v in dict(options).items() if v not in (None, "")})

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        found = [p for p in probe.with_suffix(*PACKAGES)[:40] if probe.head(p, 4) == LOCAL]
        if any(p.suffix.lower() != ".obb" for p in found):
            evidence.append("Android packages (APK or bundle)")
        if any(p.suffix.lower() == ".obb" for p in found):
            evidence.append("Android expansion files (.obb)")
        manifests = probe.find(MANIFEST_NAME, limit=5)
        unpacked = any(is_axml(probe.head(p, 8)) for p in manifests)
        if unpacked:
            evidence.append("an unpacked APK (binary AndroidManifest.xml)")
        strong = any(p.suffix.lower() != ".obb" for p in found)
        score = 0.9 if strong else (0.6 if evidence else 0.0)
        return DetectionResult("android", score, tuple(evidence), "android")

    def slot_definitions(self):
        return (*SLOTS, *PACK_SLOTS, *DECODE_SLOTS)

    def backends(self):
        packers = (ApkPacker(self.signing), BundlePacker(), ObbPacker())
        return (ApkZip(), BundleZip(), ObbZip(), *packers, AxmlDecoder(), ArscDecoder())

    def pack_slot(self, unarchive_slot: str) -> str:
        return PACKS.get(unarchive_slot, "")
