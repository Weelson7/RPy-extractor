"""L3: slot resolution, the core archive backends, RPG Maker MV media and the settings routes
as properties: a [slots] entry never binds a backend that cannot serve the slot and every bad
entry is named; the archive tools name a missing tool, a password and a failed run; MV media
decrypts byte for byte with the game's key or one recovered from its images, and repacks to
what the game reads; the settings routes name an unreadable ini and a broken plugin."""

from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import needs
from viwo.backends.archives import Py7zrBackend, SevenZipCli, UnrarCli, ZipBackend
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import OutcomeKind
from viwo.core.wiring.binder import _resolve


class BinderPropertyTests(unittest.TestCase):
    def test_an_ini_entry_never_binds_what_cannot_serve(self) -> None:
        rng = random.Random(8)
        backends = {
            "good": SimpleNamespace(families=frozenset({"unarchive"})),
            "spare": SimpleNamespace(families=frozenset({"unarchive"})),
            "packer": SimpleNamespace(families=frozenset({"pack"})),
        }
        for _ in range(300):
            slot = SlotDefinition(
                "unarchive.x",
                "unarchive",
                "core",
                rng.choice(["good", "ghost"]),
                default_spare=rng.choice(["spare", "", "gone"]),
            )
            override = (
                None
                if rng.random() < 0.2
                else tuple(
                    rng.choice(["good", "spare", "packer", "nope", "gone", ""]) for _ in range(2)
                )
            )
            main, spare, problems = _resolve(slot, override, backends)
            for chosen in (main, spare):  # whatever was asked, never a wrong backend
                self.assertIn(chosen, ("", "good", "spare", "ghost"))
            if override is None:
                continue
            for position, wanted in enumerate(override):
                bad = wanted and (
                    wanted not in backends or "unarchive" not in backends[wanted].families
                )
                silent = position == 1 and wanted == slot.default_spare  # its plugin is off
                role = ("main", "spare")[position]
                named = any(f"backend '{wanted}'" in p and f"default {role}" in p for p in problems)
                self.assertEqual(bool(bad and not silent), named, (override, problems))


def _ctx(run, located=True):
    tool = SimpleNamespace(argv_prefix=("tool",))
    host = SimpleNamespace(
        tools=SimpleNamespace(locate=lambda spec: tool if located else None),
        process=SimpleNamespace(run=run),
    )
    return SimpleNamespace(os=host, cancel=None)


class ArchiveBackendTests(unittest.TestCase):
    def test_cli_tools_name_a_password_a_failure_and_a_missing_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for said, kind in (
                ("Wrong password?", OutcomeKind.NEEDS_KEY),
                ("CRC failed", OutcomeKind.FAILED),
                ("", OutcomeKind.FAILED),
            ):

                def run(argv, timeout=None, cancel=None, said=said):
                    return SimpleNamespace(ok=False, stderr=said, stdout="", returncode=2)

                for backend in (SevenZipCli(), UnrarCli()):
                    out = backend.extract(dest / "a.rar", dest, _ctx(run))
                    self.assertEqual(out.kind, kind, (backend.backend_id, said))
                    self.assertTrue(out.error)  # "exit code 2" when the tool said nothing
            ok = SimpleNamespace(ok=True, stderr="", stdout="")
            (dest / "x.txt").write_text("x")
            self.assertEqual(
                UnrarCli().extract(dest / "a.rar", dest, _ctx(lambda *a, **k: ok)).files, 1
            )
            self.assertEqual(
                UnrarCli().extract(dest / "a.rar", dest, _ctx(None, False)).kind,
                OutcomeKind.UNAVAILABLE,
            )
            self.assertTrue(UnrarCli().argv(dest / "a.rar", dest)[-1].endswith("/"))

    @needs("py7zr")
    def test_py7zr_names_an_encrypted_archive_and_unsafe_zip_names_are_counted(self) -> None:
        import zipfile

        import py7zr

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "f.txt").write_text("secret")
            with py7zr.SevenZipFile(root / "locked.7z", "w", password="pw") as z:
                z.write(root / "f.txt", "f.txt")
            out = Py7zrBackend().extract(root / "locked.7z", root / "o", None)
            self.assertEqual(out.kind, OutcomeKind.NEEDS_KEY)
            with mock.patch.dict("sys.modules", {"py7zr": None}):
                self.assertEqual(
                    Py7zrBackend().extract(root / "locked.7z", root / "o", None).kind,
                    OutcomeKind.UNAVAILABLE,
                )
            with zipfile.ZipFile(root / "z.zip", "w") as z:
                z.writestr("../evil.txt", "x")
                z.writestr("C:/abs.txt", "x")
                z.writestr("ok/fine.txt", "x")
            (root / "plain").mkdir()
            (root / "plain" / "a.txt").write_text("a")
            with py7zr.SevenZipFile(root / "open.7z", "w") as z:
                z.writeall(root / "plain", "plain")
            self.assertEqual(Py7zrBackend().extract(root / "open.7z", root / "o7", None).files, 1)
            (root / "bad.7z").write_bytes(b"7z\xbc\xaf\x27\x1c" + bytes(40))
            bad = Py7zrBackend().extract(root / "bad.7z", root / "b7", None)
            self.assertEqual(bad.kind, OutcomeKind.FAILED)
            import tarfile

            from tests.helpers import make_tar
            from viwo.backends import archives

            make_tar(root / "t.tar", {"a/b.txt": b"b"})
            with mock.patch.dict(archives.tarfile.__dict__):
                del archives.tarfile.data_filter  # a Python without the data filter
                tar = archives.TarBackend().extract(root / "t.tar", root / "to", None)
            self.assertEqual(tar.files, 1)
            self.assertTrue(hasattr(tarfile, "data_filter"))
            (root / "broken.zip").write_bytes(b"PK not really")
            self.assertEqual(
                ZipBackend().extract(root / "broken.zip", root / "bz", None).kind,
                OutcomeKind.FAILED,
            )
            done = ZipBackend().extract(root / "z.zip", root / "zo", None)
            self.assertEqual(done.files, 2)  # "C:/abs.txt" kept inside as C_/abs.txt, recorded
            self.assertEqual((root / "zo" / "C_" / "abs.txt").read_text(), "x")
            self.assertIn("1 member name(s) Windows cannot write altered", done.notes[0])
            self.assertIn("1 entr(ies) whose name leads out", done.notes[1])  # said, never silent
            self.assertFalse((root / "evil.txt").exists())


class RpgMvTests(unittest.TestCase):
    def test_media_decrypts_with_the_games_key_or_one_recovered_from_its_images(self) -> None:
        from tests.test_rpgmaker import encrypt_mv
        from viwo.plugins.rpgmaker.mv import RpgMvExporter, RpgMvPacker, decrypt, system_key

        rng = random.Random(12)
        png = bytes.fromhex("89504e470d0a1a0a0000000d49484452")
        with tempfile.TemporaryDirectory() as tmp:
            for case in range(8):
                game = Path(tmp) / f"g{case}"
                (game / "www" / "data").mkdir(parents=True)
                with_system = rng.random() < 0.5
                if with_system:
                    key = "d41d8cd98f00b204e9800998ecf8427e"
                    (game / "www" / "data" / "System.json").write_text(
                        json.dumps({"encryptionKey": key})
                    )
                files = {}
                for i in range(rng.randint(1, 5)):
                    ext, body = rng.choice(
                        [
                            (".rpgmvp", png + rng.randbytes(40)),
                            (".rpgmvo", b"OggS" + rng.randbytes(40)),
                        ]
                    )
                    path = game / "www" / "img" / f"f{i}{ext}"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(encrypt_mv(body))
                    files[path] = body
                (game / "www" / "img" / "plain.png_").write_bytes(b"no header")  # kept as it is
                staging = Path(tmp) / f"s{case}"
                staging.mkdir()
                ctx = SimpleNamespace(
                    game_root=game, staging=staging, cancel=SimpleNamespace(cancelled=False)
                )
                out = RpgMvExporter().export(ctx)
                has_image = any(p.suffix == ".rpgmvp" for p in files)
                if not with_system and not has_image:
                    self.assertEqual(
                        out.kind, OutcomeKind.NEEDS_KEY
                    )  # nothing to recover a key from
                    continue
                self.assertEqual(out.files, len(files) + 1)  # + the unheadered file, raw
                self.assertTrue(any("without the RPGMV header" in n for n in out.notes))
                raw = staging / "www" / "img" / "plain.png_"
                self.assertEqual(raw.read_bytes(), b"no header")
                for path, body in files.items():
                    rel = path.relative_to(game).with_suffix(
                        ".png" if path.suffix == ".rpgmvp" else ".ogg"
                    )
                    self.assertEqual((staging / rel).read_bytes(), body)
                one = next(iter(files))
                edit = Path(tmp) / f"edit{case}"
                edit.write_bytes(png + b"edited")
                RpgMvPacker().pack(one, {"file": edit}, ctx)
                self.assertEqual(RpgMvPacker().verify(one, {"file": edit}, ctx), [])
                key = system_key(game) or bytes(a ^ b for a, b in zip(one.read_bytes()[16:32], png))
                self.assertEqual(decrypt(one.read_bytes(), key), png + b"edited")
            self.assertIsNone(decrypt(b"no header", b"\0" * 16))

    def test_no_key_means_needs_key_never_a_crash(self) -> None:
        from viwo.plugins.rpgmaker.mv import RpgMvPacker, png_key, system_key

        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken"
            (broken / "data").mkdir(parents=True)
            (broken / "data" / "System.json").write_text("{not json")
            self.assertIsNone(system_key(broken))  # unreadable: no key, never a crash
            self.assertIsNone(png_key([broken / "data" / "System.json"]))  # not an MV image
            nokey = SimpleNamespace(
                game_root=broken, staging=broken, cancel=SimpleNamespace(cancelled=True)
            )
            target = broken / "data" / "System.json"
            self.assertEqual(RpgMvPacker().pack(target, {}, nokey).kind, OutcomeKind.NEEDS_KEY)


class SettingsRouteTests(unittest.TestCase):
    def test_an_unreadable_ini_and_a_broken_plugin_are_named(self) -> None:
        from tests.helpers import runtime
        from viwo.api.app import App
        from viwo.api.handlers_settings import _plugin_info, get_settings, save_settings
        from viwo.contracts.errors import ViwoError

        with tempfile.TemporaryDirectory() as tmp:
            app = App(runtime(Path(tmp)))
            boom = ViwoError("invalid_request", "bad ini line 3")
            with mock.patch("viwo.api.handlers_settings.read_settings", side_effect=boom):
                self.assertEqual(get_settings(app, {})["error"], "bad ini line 3")
            with mock.patch("viwo.api.handlers_settings.write_settings", side_effect=boom):
                self.assertEqual(save_settings(app, {"features": "x"})["code"], "invalid_request")
            with mock.patch(
                "viwo.api.handlers_settings.load_plugin", side_effect=ImportError("no module")
            ):
                with mock.patch.object(app.rt, "plugins", {}):
                    info = _plugin_info(app)
            self.assertTrue(
                all("no module" in v["problem"] for v in info.values())
            )  # listed, not hidden


if __name__ == "__main__":
    unittest.main()
