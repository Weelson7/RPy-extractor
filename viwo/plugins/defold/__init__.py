"""Defold: the bundled archive (`game.arci` index, `game.arcd` data, `game.dmanifest` names;
archive.py). Every resource out under its URL (LZ4-compressed ones through the `lz4` package),
and the archive rebuilt in the patched copy with the edited resources: the engine loads nothing
over its bundle. Encrypted resources (Defold's XTEA-CTR cipher, crypt.py) are decrypted when a
key verifies against the bundle (the user's `decryption_key`, else the engine's built-in default)
and refused by name with the reason when none does; an edited encrypted resource is re-encrypted
on the way back with that same verified key."""

import os
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest, PluginOption
from viwo.contracts.slots import Packer, SlotDefinition, Unarchiver
from viwo.contracts.types import DependencySpec, DetectionResult, Outcome, OutcomeKind

from .archive import COMPRESSED, ENCRYPTED, manifest_names, read_index, write_archive
from .crypt import DEFAULT_KEY, crypt

MANIFEST = PluginManifest(
    "defold",
    "Defold",
    "0.1.0",
    engine_type="defold",
    priority=13,
    description="Defold games: the bundled archive (game.arci, game.arcd, game.dmanifest)",
    capabilities=("detect", "unpack", "pack"),
    options=(
        PluginOption(
            "decryption_key",
            "Resource key (XTEA)",
            kind="secret",
            help="Defold resource key; blank tries the engine's built-in default",
        ),
    ),
)
LZ4 = DependencySpec(
    "lz4", "lz4 (Defold resources)", kind="python", import_name="lz4", hint="pip install lz4"
)
SLOTS = (
    SlotDefinition("unarchive.arci", "unarchive", "defold", "arci-builtin", suffixes=(".arci",)),
    SlotDefinition("pack.arci", "pack", "defold", "arci-writer"),
)


def _lz4():
    try:
        import lz4.block

        return lz4
    except ImportError:
        return None


def _names(index_path: Path) -> tuple[dict, str]:
    """(content hash -> URLs, a note when the manifest is missing)."""
    path = index_path.with_suffix(".dmanifest")
    if not path.is_file():
        return {}, f"no {path.name}: resources named by their hash"
    return manifest_names(path.read_bytes()), ""


def read_all(index_path: Path):
    """(index, hash -> URLs, note) of a bundle."""
    index = read_index(index_path.read_bytes())
    names, note = _names(index_path)
    return index, names, note


def _keys(ctx) -> list[bytes]:
    """The candidate keys to try, most likely first: the user's `decryption_key` (a secret, never
    logged), then the engine's built-in default (D18: the plugin verifies before it uses one)."""
    user = str((getattr(ctx, "options", None) or {}).get("decryption_key", "") or "")
    return ([user.encode("utf-8")] if user else []) + [DEFAULT_KEY]


def _pick_key(index, data_path: Path, candidates: list[bytes], lz4) -> bytes | None:
    """The first candidate that decrypts a compressed+encrypted resource to a valid LZ4 block of
    its declared size (the only self-verifying check Defold's hashes allow), or None when the
    bundle has no such resource or none of the keys works."""
    checks = [e for e in index.entries if e.flags & ENCRYPTED and e.flags & COMPRESSED]
    if lz4 is None or not checks:
        return None
    with open(data_path, "rb") as fh:
        return next((key for key in candidates if _verifies(fh, checks[0], key, lz4)), None)


def _verifies(fh, entry, key: bytes, lz4) -> bool:
    fh.seek(entry.offset)
    size = max(entry.size, 1)
    try:
        data = lz4.block.decompress(crypt(fh.read(entry.stored), key), uncompressed_size=size)
    except (lz4.block.LZ4BlockError, ValueError):
        return False
    return len(data) == entry.size


def _resource(fh, entry, lz4, key: bytes | None) -> bytes | None:
    fh.seek(entry.offset)
    stored = fh.read(entry.stored)
    if len(stored) != entry.stored:
        raise ValueError("a resource runs past the end of the data file")
    if entry.flags & ENCRYPTED:  # decrypt first: the bundler compresses, then encrypts
        stored = crypt(stored, key)
    if not entry.flags & COMPRESSED:
        return stored
    if lz4 is None:
        return None
    try:  # bounded by the declared size: never more than the entry says
        data = lz4.block.decompress(stored, uncompressed_size=max(entry.size, 1))
    except lz4.block.LZ4BlockError as exc:
        raise ValueError(f"damaged LZ4 resource: {exc}") from None
    if len(data) != entry.size:
        raise ValueError("a resource does not inflate to its size")
    return data


class ArciBuiltin(Unarchiver):
    backend_id, owner, license = "arci-builtin", "defold", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def dependencies(self):
        return (LZ4,)

    def available(self, os) -> tuple[bool, str]:
        return True, ""  # lz4 only unlocks the compressed resources

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        lz4, names, counts = _lz4(), ws.Names(dest), {"written": 0, "locked": [], "packed": 0}
        try:
            index, urls, note = read_all(archive)
            data_path = archive.with_suffix(".arcd")
            key = _pick_key(index, data_path, _keys(ctx), lz4)
            with open(data_path, "rb") as fh:
                for entry in index.entries:
                    if ctx.cancel.cancelled:
                        break
                    self._one(fh, entry, urls, (names, counts, lz4, key))
        except (OSError, ValueError, RuntimeError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad Defold archive: {exc}"[:300])
        notes = (note,) if note else ()
        if counts["locked"]:
            first = ", ".join(counts["locked"][:3])
            why = "no verified key" if lz4 else "the 'lz4' package is needed to verify a key"
            n = len(counts["locked"])
            notes += (f"{n} encrypted resource(s) not decrypted ({why}): {first}",)
        if counts["packed"]:
            notes += (f"{counts['packed']} LZ4 resource(s) need the 'lz4' Python package",)
        return Outcome(OutcomeKind.OK, counts["written"], notes=notes + names.save())

    @staticmethod
    def _one(fh, entry, urls: dict, run: tuple) -> None:
        names, counts, lz4, key = run
        targets = [u.lstrip("/") for u in urls.get(entry.digest, [])] or [entry.digest.hex()]
        if entry.flags & ENCRYPTED and key is None:
            counts["locked"].append(targets[0])
            return
        data = _resource(fh, entry, lz4, key)
        if data is None:
            counts["packed"] += 1
            return
        for name in targets:  # resources with the same content share one entry
            target = names.target(name)
            if target is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                counts["written"] += 1


class ArciWriter(Packer):
    """The bundle rebuilt: game.arcd with the edited resources, game.arci's entries rewritten,
    every hash and the manifest kept (the engine reads sizes from the index)."""

    backend_id, owner, license = "arci-writer", "defold", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: reads the game's archive

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        data = container.with_suffix(".arcd")
        temps = [p.with_name(p.name + ".viwo-tmp") for p in (container, data)]
        try:
            index, urls, _ = read_all(container)
            lz4 = _lz4()
            key = _pick_key(index, data, _keys(ctx), lz4)
            edits, shared = _edits(urls, members)
            editable = {e.digest for e in index.entries if not e.flags & ENCRYPTED or key}
            if set(edits) - editable:
                raise ValueError("an edit names an encrypted resource and no key was verified")
            with open(data, "rb") as src, open(temps[1], "wb") as out:
                blob = write_archive(index, src, edits, out, lz4, key)
            temps[0].write_bytes(blob)
            os.replace(temps[1], data)
            os.replace(temps[0], container)
        except (OSError, ValueError) as exc:
            for temp in temps:
                temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=f"{container.name}: {exc}"[:300])
        notes = (f"one content, several resources, all take the edit: {shared}",) if shared else ()
        if _lz4() is None:
            notes += ("without the 'lz4' package edited resources are stored uncompressed",)
        return Outcome(OutcomeKind.OK, len(members), notes=notes)


def _edits(urls: dict, members: dict[str, Path]) -> tuple[dict, str]:
    """(content hash -> edited bytes, the members whose content other resources share)."""
    by_url = {u.lstrip("/"): d for d, us in urls.items() for u in us}
    edits, shared = {}, []
    for member, path in sorted(members.items()):
        digest = by_url.get(member)
        if digest is None:
            try:
                digest = bytes.fromhex(member)
            except ValueError:
                raise ValueError(f"{member}: not a resource of this archive") from None
        edits[digest] = path.read_bytes()
        if len(urls.get(digest, ())) > 1:
            shared.append(member)
    return edits, ", ".join(shared[:3])


class DefoldPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if probe.has_name("game.arci") and probe.has_name("game.arcd"):
            evidence.append("Defold bundle (game.arci, game.arcd)")
        if probe.has_name("game.dmanifest", "game.projectc"):
            evidence.append("Defold manifest and project settings")
        score = 0.9 if len(evidence) == 2 else (0.6 if evidence else 0.0)
        return DetectionResult("defold", score, tuple(evidence), "defold")

    def slot_definitions(self):
        return SLOTS

    def backends(self):
        return (ArciBuiltin(), ArciWriter())

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.arci" if unarchive_slot == "unarchive.arci" else ""

    def claimed_suffixes(self):
        return (".arcd", ".dmanifest")  # read with their .arci, never carved on their own
