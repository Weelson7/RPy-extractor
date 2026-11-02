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
