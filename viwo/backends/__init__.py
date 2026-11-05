"""Core-owned slots and backends (doc 8.4)."""

from viwo.contracts.slots import Backend, SlotDefinition

from .archives import Py7zrBackend, SevenZipCli, TarBackend, UnrarCli, ZipBackend
from .packers import ZipPacker

TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tbz2", ".tar.xz", ".txz")

CORE_SLOTS = (
    SlotDefinition("media.encode", "media.encode", "core", "ffmpeg"),
    SlotDefinition("carve.signatures", "carve", "core", "signature-carver"),
    SlotDefinition("pack.zip", "pack", "core", "zip-packer"),
    SlotDefinition(
        "unarchive.zip",
        "unarchive",
        "core",
        "py-zipfile",
        "sevenzip-cli",
        suffixes=(".zip", ".nw"),  # NW.js package.nw is a zip
        magic=(b"PK\x03\x04",),
    ),
    SlotDefinition(
        "unarchive.tar", "unarchive", "core", "py-tarfile", "sevenzip-cli", suffixes=TAR_SUFFIXES
    ),
    SlotDefinition(
        "unarchive.7z",
        "unarchive",
        "core",
        "sevenzip-cli",
        "py7zr",
        suffixes=(".7z",),
        magic=(b"7z\xbc\xaf\x27\x1c",),
    ),
    SlotDefinition(
        "unarchive.rar",
        "unarchive",
        "core",
        "unrar-cli",
        "sevenzip-cli",
        suffixes=(".rar",),
        magic=(b"Rar!\x1a\x07",),
    ),
)


def core_backends() -> list[Backend]:
    """The backends of this package (the core's own, carver and ffmpeg, are added by
    core.wiring: backends sit below core and never import it)."""
    return [b() for b in (ZipBackend, TarBackend, SevenZipCli, UnrarCli, Py7zrBackend, ZipPacker)]
