"""L3: Defold bundles, property tests on archives written here byte by byte the way Defold's
builder writes them (versions 4, 5 and 6 of the index; SHA-1 of the stored bytes, sorted; data
aligned to 4; LZ4 blocks; the protobuf manifest naming each resource): every unencrypted resource
comes out under its URL (resources sharing one content each), encrypted ones are named and never
guessed; an unchanged bundle is rebuilt byte for byte; an edit reads back with every hash, the
manifest and every other resource as they were, the index's MD5 that of its new body; unknown
versions and damage are named failures; end to end, an edited resource is repacked into the
patched copy, the game left as it was."""

from __future__ import annotations

import hashlib
import random
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import lz4.block

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts.types import OutcomeKind
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.core.roundtrip import repack
from viwo.plugins.defold import ArciBuiltin, ArciWriter, DefoldPlugin
from viwo.plugins.defold.archive import read_index
from viwo.plugins.defold.crypt import DEFAULT_KEY, crypt

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


def octx(key: str = "") -> SimpleNamespace:
    return SimpleNamespace(cancel=SimpleNamespace(cancelled=False), options={"decryption_key": key})


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        out.append(n & 0x7F | (0x80 if n > 0x7F else 0))
        n >>= 7
        if not n:
            return bytes(out)


def field(number: int, value) -> bytes:
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    return varint(number << 3 | 2) + varint(len(value)) + value


def manifest(entries: list) -> bytes:
    """ManifestFile{data: ManifestData{header, resources: [ResourceEntry]}, signature}."""
    data = field(1, field(1, 2) + field(4, field(1, b"\x01" * 20)))
    for url, digest, size in entries:
        entry = field(1, field(1, digest)) + field(2, url.encode()) + field(3, hash(url) & 0xFFFF)
        data += field(3, entry + field(4, size) + field(5, 0) + field(6, 1) + field(7, 5))
    return field(1, data) + field(2, b"signature") + field(4, 0)


def bundle(resources: dict, version: int, rng: random.Random) -> tuple[bytes, bytes, bytes]:
    """resources: {url: (data, compress, encrypt)} -> (arci, arcd, dmanifest)."""
    stored = {}
    for url, (data, squeeze, lock) in resources.items():
        packed = lz4.block.compress(data, store_size=False) if squeeze else data
        flags = (2 if squeeze else 0) | (1 if lock else 0)
        body = bytes(b ^ 0x5A for b in packed) if lock else packed
        stored.setdefault(hashlib.sha1(body).digest(), (body, len(data), len(packed), flags))
    arcd, offsets = bytearray(), {}
    for digest in rng.sample(sorted(stored), len(stored)):  # written in any order
        arcd += b"\0" * (-len(arcd) % 4)
        offsets[digest] = len(arcd)
        arcd += stored[digest][0]
    order = sorted(stored)
    hashes = b"".join(d.ljust(64, b"\0") for d in order)
    table = b""
    for d in order:
        _, size, packed, flags = stored[d]
        packed = packed if flags & 2 else 0xFFFFFFFF
        if version >= 6:
            table += struct.pack(">QII", flags << 60 | offsets[d], size, packed)
        else:
            table += struct.pack(">IIII", offsets[d], size, packed, flags)
    body = hashes + table
    head = struct.pack(">IIQIIII", version, 0, 0, len(order), 48 + len(hashes), 48, 20)
    arci = head + hashlib.md5(body).digest() + body
    by_url = [(u, hashlib.sha1(_body(d)).digest(), len(d[0])) for u, d in resources.items()]
    return arci, bytes(arcd), manifest(by_url)


def _body(spec) -> bytes:
    data, squeeze, lock = spec
    packed = lz4.block.compress(data, store_size=False) if squeeze else data
    return bytes(b ^ 0x5A for b in packed) if lock else packed


def resources_of(rng: random.Random) -> dict:
    out = {}
    for i in range(rng.randint(1, 10)):
        data = (
            rng.randbytes(rng.randint(0, 300)) if rng.random() < 0.5 else bytes(rng.randint(0, 900))
        )
        folder = rng.choice(["main", "assets/img", "_generated"])
        url = f"/{folder}/r{i}.{rng.choice(['texturec', 'luac', 'goc'])}"
        out[url] = (data, rng.random() < 0.5, rng.random() < 0.15)
    if rng.random() < 0.4:  # two resources, one content
        first = next(iter(out.values()))
        out["/main/copy_of_first.bin"] = first
    return out


def write(folder: Path, resources: dict, version: int, rng: random.Random) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    arci, arcd, man = bundle(resources, version, rng)
    (folder / "game.arci").write_bytes(arci)
    (folder / "game.arcd").write_bytes(arcd)
    (folder / "game.dmanifest").write_bytes(man)
    return folder / "game.arci"


def read(archive: Path, out: Path):
    result = ArciBuiltin().extract(archive, out, CTX)
    assert result.kind is OutcomeKind.OK, result.error
    return result, {
        f.relative_to(out).as_posix(): f.read_bytes() for f in out.rglob("*") if f.is_file()
    }


class DefoldTests(unittest.TestCase):
    def test_every_version_comes_out_and_an_unchanged_bundle_is_rebuilt_as_it_was(self) -> None:
        rng = random.Random(61)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(30):
                version = (4, 5, 6)[case % 3]
                resources = resources_of(rng)
                archive = write(root / f"c{case}", resources, version, rng)
                before = {p.name: p.read_bytes() for p in archive.parent.iterdir()}
                result, got = read(archive, root / f"o{case}")
                plain = {u.lstrip("/"): d for u, (d, _, lock) in resources.items() if not lock}
                self.assertEqual(got, plain)
                locked = [u for u, (_, _, lock) in resources.items() if lock]
                self.assertEqual(any("encrypted" in n for n in result.notes), bool(locked))
                self.assertEqual(ArciWriter().pack(archive, {}, CTX).kind, OutcomeKind.OK)
                after = {p.name: p.read_bytes() for p in archive.parent.iterdir()}
                self.assertEqual(after, before, case)

    def test_an_edit_reads_back_with_every_hash_and_the_manifest_kept(self) -> None:
        rng = random.Random(62)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(30):
                version = (4, 5, 6)[case % 3]
                resources = resources_of(rng)
                archive = write(root / f"c{case}", resources, version, rng)
                plain = sorted(u for u, (_, _, lock) in resources.items() if not lock)
                if not plain:
                    continue
                manifest_before = (archive.parent / "game.dmanifest").read_bytes()
                index_before = read_index(archive.read_bytes())
                edits = {}
                for url in rng.sample(plain, rng.randint(1, len(plain))):
                    edits[url.lstrip("/")] = archive.parent / f"e{len(edits)}"
                    edits[url.lstrip("/")].write_bytes(rng.randbytes(rng.randint(0, 500)))
                done = ArciWriter().pack(archive, edits, CTX)
                self.assertEqual(done.kind, OutcomeKind.OK, done.error)
                _, got = read(archive, root / f"o{case}")
                for url, (data, _, lock) in resources.items():
                    if lock:
                        continue
                    # resources sharing a content share it still: the last edit in name order
                    group = sorted(e for e in edits if resources["/" + e] == resources[url])
                    want = edits[group[-1]].read_bytes() if group else data
                    self.assertEqual(got[url.lstrip("/")], want)
                if len(edits) > 1 and any(
                    resources["/" + a] == resources["/" + b] for a in edits for b in edits if a < b
                ):
                    self.assertIn("several resources", " ".join(done.notes))
                index = read_index(archive.read_bytes())
                self.assertEqual(
                    [e.digest for e in index.entries], [e.digest for e in index_before.entries]
                )
                self.assertEqual(index.blob[32:48], hashlib.md5(index.blob[48:]).digest())
                self.assertEqual((archive.parent / "game.dmanifest").read_bytes(), manifest_before)

    def test_unknown_versions_missing_manifests_and_damage_are_named(self) -> None:
        rng = random.Random(63)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = write(root / "v3", {"/a.txt": (b"a", False, False)}, 4, rng)
            blob = bytearray(archive.read_bytes())
            blob[3] = 3
            archive.write_bytes(bytes(blob))
            done = ArciBuiltin().extract(archive, root / "o3", CTX)
            self.assertIn("version 3", done.error)
            archive = write(root / "nm", {"/a.txt": (b"abc", False, False)}, 6, rng)
            (archive.parent / "game.dmanifest").unlink()
            result, got = read(archive, root / "onm")
            self.assertEqual(list(got.values()), [b"abc"])
            self.assertIn("named by their hash", result.notes[0])
            bad = ArciWriter().pack(archive, {"zz/not-there": archive}, CTX)
            self.assertEqual(bad.kind, OutcomeKind.FAILED)
            self.assertFalse(list(archive.parent.glob("*.viwo-tmp")))  # nothing left behind
            for case in range(200):
                folder = write(
                    root / f"d{case}", resources_of(rng), rng.choice((4, 5, 6)), rng
                ).parent
                target = folder / rng.choice(("game.arci", "game.arcd", "game.dmanifest"))
                blob = bytearray(target.read_bytes())
                if blob and rng.random() < 0.5:
                    blob = blob[: rng.randrange(len(blob))]
                elif blob:
                    blob[rng.randrange(len(blob))] ^= 1 << rng.randrange(8)
                target.write_bytes(bytes(blob))
                ArciBuiltin().extract(folder / "game.arci", folder / "o", CTX)  # never a crash

    def test_detection_and_an_edit_end_to_end(self) -> None:
        rng = random.Random(64)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "Jumper"
            resources = {
                "/main/title.txt": (b"Jumper", True, False),
                "/main/main.luac": (b"lua", False, True),
            }
            write(game, resources, 6, rng)
            (game / "game.projectc").write_text("[project]\n")
            self.assertEqual(DefoldPlugin().detect(FolderProbe(game)).confidence, 0.9)
            before = tree_hashes(game)
            rt, request = runtime(root), ExtractionRequest(str(game), str(root / "ws"))
            result = extract(rt, request, "j", lambda e: None, CancelToken())
            self.assertEqual(result.runs[0].plugin_id, "defold", result.warnings)
            edited = next((root / "ws").rglob("title.txt"))
            edited.write_bytes(b"Jumper, edited")
            report = repack(rt, root / "ws", root / "copy")
            self.assertTrue(report["verified"], report)
            _, got = read(root / "copy" / "game.arci", root / "back")
            self.assertEqual(got, {"main/title.txt": b"Jumper, edited"})
            self.assertEqual(tree_hashes(game), before)


def enc_bundle(folder: Path, plain: bytes, enc: bytes, key: bytes) -> Path:
    """A version-6 bundle: one plain resource and one that is LZ4-compressed then XTEA-encrypted
    with `key`, exactly as Defold's bundler stores an encrypted resource."""
    folder.mkdir(parents=True, exist_ok=True)
    packed = lz4.block.compress(enc, store_size=False)
    recs = {  # digest -> (stored bytes, size, packed field, flags)
        hashlib.sha1(plain).digest(): (plain, len(plain), 0xFFFFFFFF, 0),
        hashlib.sha1(crypt(packed, key)).digest(): (crypt(packed, key), len(enc), len(packed), 3),
    }
    order, arcd, offsets = sorted(recs), bytearray(), {}
    for d in order:
        arcd += b"\0" * (-len(arcd) % 4)
        offsets[d] = len(arcd)
        arcd += recs[d][0]
    hashes = b"".join(d.ljust(64, b"\0") for d in order)
    table = b"".join(
        struct.pack(">QII", recs[d][3] << 60 | offsets[d], recs[d][1], recs[d][2]) for d in order
    )
    body = hashes + table
    head = struct.pack(">IIQIIII", 6, 0, 0, len(order), 48 + len(hashes), 48, 20)
    (folder / "game.arci").write_bytes(head + hashlib.md5(body).digest() + body)
    (folder / "game.arcd").write_bytes(bytes(arcd))
    man = manifest(
        [
            ("/plain.txt", hashlib.sha1(plain).digest(), len(plain)),
            ("/enc.luac", hashlib.sha1(crypt(packed, key)).digest(), len(enc)),
        ]
    )
    (folder / "game.dmanifest").write_bytes(man)
    return folder / "game.arci"


class DefoldEncryptionTests(unittest.TestCase):
    def test_crypt_matches_the_defold_engine_vector(self) -> None:
        expected = bytes.fromhex("81b4a1042dace5cb7789ec1161c3dcfab9a325")
        self.assertEqual(crypt(b"ABCDEFGH12345678XYZ", b"12345678abcdefgh"), expected)
        self.assertEqual(crypt(expected, b"12345678abcdefgh"), b"ABCDEFGH12345678XYZ")

    def test_the_builtin_default_key_decrypts_an_encrypted_resource(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = enc_bundle(
                root / "g", b"plain body", b"-- lua source\nreturn 1\n", DEFAULT_KEY
            )
            result, got = read(archive, root / "o")
            self.assertEqual(got["enc.luac"], b"-- lua source\nreturn 1\n")
            self.assertEqual(got["plain.txt"], b"plain body")
            self.assertFalse(any("not decrypted" in n for n in result.notes), result.notes)

    def test_a_user_key_is_verified_and_a_wrong_key_is_refused_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = enc_bundle(root / "g", b"plain", b"secret lua body", b"mysecretkey12345")
            ArciBuiltin().extract(archive, root / "ok", octx("mysecretkey12345"))
            got = {p.name: p.read_bytes() for p in (root / "ok").rglob("*") if p.is_file()}
            self.assertEqual(got.get("enc.luac"), b"secret lua body")
            bad = ArciBuiltin().extract(
                archive, root / "bad", octx("")
            )  # only the default is tried
            names = {p.name for p in (root / "bad").rglob("*") if p.is_file()}
            self.assertNotIn("enc.luac", names)
            self.assertTrue(any("not decrypted" in n for n in bad.notes), bad.notes)

    def test_an_edited_encrypted_resource_is_re_encrypted_on_the_way_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = enc_bundle(root / "g", b"plain", b"old lua", b"mysecretkey12345")
            edit = root / "new.luac"
            new = b"local function noop() end\n" * 50  # compressible: stays LZ4 + encrypted
            edit.write_bytes(new)
            done = ArciWriter().pack(archive, {"enc.luac": edit}, octx("mysecretkey12345"))
            self.assertEqual(done.kind, OutcomeKind.OK, done.error)
            _, got = read_with(archive, root / "back", octx("mysecretkey12345"))
            self.assertEqual(got["enc.luac"], new)


def read_with(archive: Path, out: Path, ctx):
    result = ArciBuiltin().extract(archive, out, ctx)
    assert result.kind is OutcomeKind.OK, result.error
    return result, {
        f.relative_to(out).as_posix(): f.read_bytes() for f in out.rglob("*") if f.is_file()
    }


if __name__ == "__main__":
    unittest.main()
