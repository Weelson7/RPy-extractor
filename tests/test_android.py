"""L3: Android packages (static arm only). An APK is identified by its binary manifest whatever
its name, a bundle by its APKs, an OBB as a zip; every member comes out; the rebuild keeps every
untouched member's compressed bytes and the members' order, aligns stored members as zipalign
does (page-aligned `.so` when the original was), leaves the old v1 signature out and signs
through the pinned signer (faked here: no device, no network) or says it is unsigned; end to
end, a decoded manifest and resource table are edited and go back into the patched copy, the
game left as it was, and the engine inside an APK (or a bundle's APK) is re-detected."""

from __future__ import annotations

import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from tests import android_build as b
from tests.helpers import runtime, tree_hashes
from tests.test_android_formats import EDITED
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts.types import OutcomeKind, ProcessResult
from viwo.core.pipeline.export import _wrapper
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.core.roundtrip import repack
from viwo.plugins.android import AndroidPlugin, ApkZip, BundleZip, identify_android
from viwo.plugins.android import zipfmt as z
from viwo.plugins.android.axml import read_axml, to_text
from viwo.plugins.android.pack import ApkPacker, ObbPacker
from viwo.plugins.android.sign import DEBUG, UNSIGNED

SIGNATURES = ("META-INF/MANIFEST.MF", "META-INF/CERT.SF", "META-INF/CERT.RSA")


def ctx(root: Path, tool=None, run=None) -> SimpleNamespace:
    tools = SimpleNamespace(locate=lambda spec: tool)
    return SimpleNamespace(
        os=SimpleNamespace(tools=tools, process=SimpleNamespace(run=run)),
        scratch=root / "scratch",
        cancel=SimpleNamespace(cancelled=False),
        log=lambda *a, **k: None,
    )


def identify(path: Path):
    head = path.read_bytes()[:64]
    return identify_android(path, head, b"")


def raw_members(path: Path) -> dict[str, tuple[int, bytes]]:
    """member -> (data offset, its compressed bytes as stored)."""
    out = {}
    with open(path, "rb") as fh:
        entries, _ = z.read_entries(fh, path.stat().st_size)
        for entry in entries:
            start, _ = z.data_at(fh, entry)
            fh.seek(start)
            out[entry.text] = (start, fh.read(entry.csize))
    return out


def fake_signer(argv, timeout=None, cancel=None, **_):
    apk, out = Path(argv[argv.index("-a") + 1]), Path(argv[argv.index("-o") + 1])
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{apk.stem}-aligned-debugSigned.apk").write_bytes(apk.read_bytes() + b"SIGNED")
    return ProcessResult(0, "", "")


class PackageTests(unittest.TestCase):
    def test_identified_by_content_not_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = {
                "game.bin": (b.zip_of(b.apk_members(), b.STORED), "unarchive.apk"),
                "lib.aar": (b.zip_of({"AndroidManifest.xml": b"<manifest/>"}), None),
                "x.xapk": (b.zip_of({"base.apk": b"PK", "manifest.json": b"{}"}), "unarchive.apks"),
                "y.zip": (b.zip_of({"split.apk": b"PK", "toc.pb": b""}), "unarchive.apks"),
                "plain.zip": (b.zip_of({"a.apk": b"PK"}), None),
                "main.1.x.obb": (b.zip_of({"a.bin": b"x"}), "unarchive.obb"),
                "pck.obb": (b"GDPC" + bytes(60), None),
                "broken.apk": (b"PK\x03\x04" + bytes(40), None),
            }
            for name, (blob, slot) in cases.items():
                (root / name).write_bytes(blob)
                found = identify(root / name)
                self.assertEqual(found.slot_id if found else None, slot, name)

    def test_members_come_out_and_an_encrypted_bundle_needs_its_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apk = root / "a.apk"
            apk.write_bytes(b.zip_of(b.apk_members(), b.STORED))
            done = ApkZip().extract(apk, root / "out", ctx(root))
            self.assertEqual(done.kind, OutcomeKind.OK, done.error)
            got = {p.relative_to(root / "out").as_posix(): p.read_bytes()
                   for p in (root / "out").rglob("*") if p.is_file()}  # fmt: skip
            self.assertEqual(got, b.apk_members())
            blob = bytearray(b.zip_of({"base.apk": b"PK", "manifest.json": b"{}"}))
            at = blob.find(b"PK\x01\x02")
            blob[at + 8] |= 1  # the encryption flag of the first member
            (root / "locked.xapk").write_bytes(bytes(blob))
            locked = BundleZip().extract(root / "locked.xapk", root / "o2", ctx(root))
            self.assertEqual(locked.kind, OutcomeKind.NEEDS_KEY)

    def test_rebuild_keeps_bytes_and_order_aligns_and_drops_the_old_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for pages in (False, True):
                apk = root / f"g{pages}.apk"
                apk.write_bytes(b.zip_of(b.apk_members(), b.STORED, pages=pages))
                before = raw_members(apk)
                edits = {"assets/readme.txt": root / "e1", "classes.dex": root / "e2"}
                edits["assets/new.txt"] = root / "e3"
                edits["lib/x86/libnew.so"] = root / "e4"
                for n, path in enumerate(edits.values()):
                    path.write_bytes(bytes([n]) * (100 + n))
                done = ApkPacker({}).pack(apk, edits, ctx(root))
                self.assertEqual(done.kind, OutcomeKind.OK, done.error)
                self.assertIn(UNSIGNED, done.notes)
                self.assertTrue(any("3 old v1 signature" in n for n in done.notes))
                after = raw_members(apk)
                kept = [m for m in before if m not in SIGNATURES]
                self.assertEqual(list(after), kept + ["assets/new.txt", "lib/x86/libnew.so"])
                for member in kept:
                    if member not in edits:
                        self.assertEqual(after[member][1], before[member][1], member)
                with zipfile.ZipFile(apk) as zf:
                    self.assertIsNone(zf.testzip())
                    stored = [i for i in zf.infolist() if i.compress_type == 0]
                    self.assertEqual(zf.read("classes.dex"), edits["classes.dex"].read_bytes())
                    self.assertEqual(zf.getinfo("classes.dex").compress_type, 8)
                    self.assertEqual(zf.getinfo("assets/readme.txt").compress_type, 0)
                for info in stored:
                    align = 4096 if pages and info.filename.endswith(".so") else 4
                    self.assertEqual(after[info.filename][0] % align, 0, info.filename)
                self.assertEqual(ApkPacker().verify(apk, edits, None), [])
                edits["classes.dex"].write_bytes(b"other")
                self.assertEqual(ApkPacker().verify(apk, edits, None), ["classes.dex"])

    def test_signing_with_the_debug_key_a_keystore_or_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apk = root / "g.apk"
            apk.write_bytes(b.zip_of(b.apk_members(), b.STORED))
            tool = SimpleNamespace(argv_prefix=["java", "-jar", "signer.jar"])
            done = ApkPacker({}).pack(apk, {}, ctx(root, tool, fake_signer))
            self.assertIn(DEBUG, done.notes)
            self.assertTrue(apk.read_bytes().endswith(b"SIGNED"))
            seen = []

            def refusing(argv, **_):
                seen.append(argv)
                return ProcessResult(1, "", "keystore password hunter2 was incorrect")

            (root / "my.jks").write_bytes(b"ks")
            settings = {"keystore": str(root / "my.jks"), "key_alias": "me"}
            apk.write_bytes(b.zip_of(b.apk_members(), b.STORED))
            done = ApkPacker(settings).pack(apk, {}, ctx(root, tool, refusing))
            self.assertTrue(any("needs an existing file" in n for n in done.notes))
            settings["keystore_password"] = "hunter2"
            done = ApkPacker(settings).pack(apk, {}, ctx(root, tool, refusing))
            note = next(n for n in done.notes if "signing failed" in n)
            self.assertNotIn("hunter2", note)
            self.assertIn("<secret>", note)
            self.assertIn("--ksAlias", seen[0])
            self.assertFalse(apk.read_bytes().endswith(b"SIGNED"))
            self.assertFalse(list((root / "scratch").iterdir()))  # nothing left behind
            obb = root / "main.obb"
            obb.write_bytes(b.zip_of({"a.bin": b"x" * 50}))
            done = ObbPacker().pack(obb, {"a.bin": root / "my.jks"}, ctx(root))
            self.assertFalse(any("sign" in n.lower() for n in done.notes))
            bad = root / "bad.apk"
            bad.write_bytes(b"PK\x03\x04 not a zip")
            self.assertEqual(ApkPacker().pack(bad, {}, ctx(root)).kind, OutcomeKind.FAILED)
            self.assertFalse((root / "bad.apk.viwo-tmp").exists())

    def test_detection_and_the_wrapper_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = AndroidPlugin()
            self.assertEqual(plugin.detect(FolderProbe(root)).confidence, 0.0)
            (root / "main.1.x.obb").write_bytes(b.zip_of({"a": b"1"}))
            self.assertEqual(plugin.detect(FolderProbe(root)).confidence, 0.6)
            (root / "game.apk").write_bytes(b.zip_of(b.apk_members()))
            self.assertEqual(plugin.detect(FolderProbe(root)).confidence, 0.9)
            loose = root / "loose"
            loose.mkdir()
            (loose / "AndroidManifest.xml").write_bytes(b.manifest())
            self.assertEqual(plugin.detect(FolderProbe(loose)).confidence, 0.6)
        self.assertTrue(_wrapper("game:sub/game.apk"))
        self.assertTrue(_wrapper("game:x.xapk!base.apk"))
        self.assertFalse(_wrapper("game:data.zip!base.apk"))
        self.assertTrue(_wrapper("game:resources/app.asar"))


class EndToEndTests(unittest.TestCase):
    def test_an_apk_is_decoded_edited_and_rebuilt_into_the_patched_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "Game"
            game.mkdir()
            members = {**b.apk_members(), "assets/project.binary": b"GDPC-ish"}
            (game / "game.apk").write_bytes(b.zip_of(members, b.STORED))
            before = tree_hashes(game)
            rt, request = runtime(root), ExtractionRequest(str(game), str(root / "ws"))
            result = extract(rt, request, "j", lambda e: None, CancelToken())
            self.assertEqual(result.runs[0].plugin_id, "android", result.warnings)
            self.assertTrue(any("Re-detected godot inside game:game.apk" in line
                                for line in result.logs), result.logs)  # fmt: skip
            ws = root / "ws"
            text = next(ws.rglob("AndroidManifest.text.xml"))
            self.assertEqual(text.read_text("utf-8"), b.MANIFEST_TEXT)
            text.write_text(EDITED, encoding="utf-8")
            table = next(ws.rglob("resources.arsc.json"))
            table.write_text(table.read_text("utf-8").replace('"World"', '"Edited"'), "utf-8")
            report = repack(rt, ws, root / "copy")
            self.assertTrue(report["verified"], report)
            notes = [n for r in report["results"] for n in r.get("notes", [])]
            self.assertIn(UNSIGNED, notes)
            with zipfile.ZipFile(root / "copy" / "game.apk") as zf:
                self.assertEqual(to_text(read_axml(zf.read("AndroidManifest.xml")))[0], EDITED)
                self.assertIn("Edited".encode("utf-16-le"), zf.read("resources.arsc"))
                self.assertNotIn("META-INF/CERT.RSA", zf.namelist())
            self.assertEqual(tree_hashes(game), before)

    def test_a_bundle_opens_down_to_its_apk_and_obb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "Game"
            game.mkdir()
            obb = b.zip_of({"data/level1.bin": b"level one" * 10})
            inner = {**b.apk_members(), "assets/bin/Data/globalgamemanagers": b"\0" * 40}
            bundle = {"manifest.json": b"{}", "base.apk": b.zip_of(inner, b.STORED)}
            bundle["Android/obb/com.viwo.test/main.1.com.viwo.test.obb"] = obb
            (game / "game.xapk").write_bytes(b.zip_of(bundle, tuple(bundle)))
            rt, request = runtime(root), ExtractionRequest(str(game), str(root / "ws"))
            result = extract(rt, request, "j", lambda e: None, CancelToken())
            self.assertTrue(next((root / "ws").rglob("level1.bin"), None))
            self.assertTrue(next((root / "ws").rglob("classes.dex"), None))
            logs = "\n".join(result.logs)
            for backend in ("apks-zip", "apk-zip", "obb-zip"):
                self.assertIn(f"via {backend}", logs)
            self.assertIn("Re-detected unity inside game:game.xapk!base.apk", logs)
            shutil.rmtree(root / "ws", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
