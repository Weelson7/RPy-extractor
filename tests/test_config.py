"""L1: distro config files: naming, determinism, strict checks, base layering, drift."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from viwo.contracts import ViwoError
from viwo.core.wiring.distros import MARKER, NAME, OSES, PROFILES, check, generate, render
from viwo.core.wiring.ini import load_ini

ROOT = Path(__file__).resolve().parent.parent


class GeneratorTests(unittest.TestCase):
    def test_twelve_files_named_and_written_strictly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            report = generate(out)
            self.assertEqual(len(report), len(OSES) * len(PROFILES))
            self.assertFalse(any(report.values()), report)
            first = {p.name: p.read_bytes() for p in out.iterdir()}
            generate(out)
            self.assertEqual(
                first, {p.name: p.read_bytes() for p in out.iterdir()}
            )  # deterministic
            for name, data in first.items():
                self.assertRegex(name, NAME)
                text = data.decode("utf-8")
                self.assertTrue(text.startswith(MARKER))
                self.assertNotIn("\r", text)
                self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"))
            unity = load_ini(out / "windows-unity.ini")
            self.assertEqual((unity.os_id, unity.profile), ("windows", "unity"))
            self.assertTrue(unity.plugins["unity"] and unity.plugins["generic"])
            self.assertFalse(unity.plugins["renpy"])

    def test_hand_written_files_are_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mine = Path(tmp) / "linux-renpy.ini"
            mine.write_text("[plugins]\nrenpy = on\n")
            report = generate(Path(tmp))
            self.assertTrue(report["linux-renpy.ini"])
            self.assertEqual(mine.read_text(), "[plugins]\nrenpy = on\n")

    def test_shipped_distros_match_the_generator(self) -> None:
        for os_id in OSES:
            for profile in PROFILES:
                shipped = (ROOT / "distros" / f"{os_id}-{profile}.ini").read_bytes()
                self.assertEqual(
                    shipped.decode("utf-8"),
                    render(os_id, profile),
                    f"{os_id}-{profile}: run `viwo config generate`",
                )


class CheckTests(unittest.TestCase):
    def problems(self, name: str, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_text(text)
            return check(path)

    def test_strict_rules(self) -> None:
        self.assertEqual(self.problems("linux-unity.ini", "[plugins]\nunity = on\n"), [])
        cases = {
            "Linux_Unity.ini": "[plugins]\nunity = on\n",
            "linux-unity.ini": "[plugins]\nnope = on\n",
            "windows-mixed.ini": "[slots]\nunarchive.nope = py-zipfile\n",
            "windows-godot.ini": "[slots]\nunarchive.zip = ffmpeg\n",
            "linux-mixed.ini": "[weird]\nx = 1\n",
            "linux-renpy.ini": "[options.godot]\nencryption_key = abc\n",
            "linux-custom.ini": "[startup]\nos = mac\n",
            "windows-unreal.ini": "[startup]\nflavour = spicy\n",
        }
        for name, text in cases.items():
            with self.subTest(name=name, text=text):
                self.assertTrue(self.problems(name, text))

    def test_engine_distros_boot_without_spare_problems(self) -> None:
        """Doc 8.2 / 8.4: a distro never names a spare whose plugin it switches off."""
        from viwo.core.wiring.boot import boot

        with tempfile.TemporaryDirectory() as tmp:
            generate(Path(tmp) / "distros")
            for name in ("windows-unreal.ini", "windows-godot.ini"):  # this host's OS layer
                rt = boot(Path(tmp) / "distros" / name, temp_root=Path(tmp) / "t")
                self.assertFalse([p for p in rt.problems if "unknown backend" in p], rt.problems)
            text = (Path(tmp) / "distros" / "windows-unreal.ini").read_text()
            self.assertIn("unarchive.upak = repak-cli\n", text)
            self.assertIn("unarchive.upak = repak-cli, quickbms-cli", render("windows", "mixed"))

    def test_suffix_clash_is_reported_and_profile_flag_selects_plugins(self) -> None:
        from viwo.contracts.slots import SlotDefinition
        from viwo.core.wiring.boot import boot
        from viwo.core.wiring.conformance import suffix_clashes

        a = SlotDefinition("unarchive.a", "unarchive", "p1", "x", suffixes=(".pak",))
        b = SlotDefinition("unarchive.b", "unarchive", "p2", "y", suffixes=(".pak", ".zip"))
        [problem] = suffix_clashes({"unarchive.a": a, "unarchive.b": b})
        self.assertIn("unarchive.a wins", problem)
        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "startup.ini"
            ini.write_text("[plugins]\nrenpy = on\nunity = on\n")
            rt = boot(ini, temp_root=Path(tmp) / "t", profile="godot")
            self.assertEqual(rt.config.sources["startup.profile"], "cli")
            self.assertTrue("godot" in rt.plugins and "unity" not in rt.plugins)
            with self.assertRaises(ViwoError):
                boot(ini, temp_root=Path(tmp) / "t", profile="spicy")

    def test_base_layering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate(root / "distros")
            top = root / "startup.ini"
            top.write_text("[startup]\nbase = distros/linux-godot.ini\n[plugins]\nrenpy = on\n")
            config = load_ini(top)
            self.assertTrue(config.plugins["godot"] and config.plugins["renpy"])  # base + override
            self.assertFalse(config.plugins["unity"])
            self.assertEqual(check(top), [])
            top.write_text("[startup]\nbase = missing.ini\n")
            with self.assertRaises(ViwoError):
                load_ini(top)
            (root / "a.ini").write_text("[startup]\nbase = b.ini\n")
            (root / "b.ini").write_text("[startup]\nbase = a.ini\n")
            with self.assertRaises(ViwoError):
                load_ini(root / "a.ini")


if __name__ == "__main__":
    unittest.main()
