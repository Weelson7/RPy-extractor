"""L2: `--plugin <id>=on|off` and `--slot <slot>=<main>[,<spare>]` for one run (doc 9.1, value
source 4). Properties: whatever the ini says, a plugin the flags turn off is not loaded and
one they turn on is, and every such value reads "cli" as its source; a slot the flags name is
bound as asked when the backends exist, and a bad id is said and replaced by the default,
never silently; a malformed flag is refused with the form it should have; after the command
word `--slot` and `--plugin` stay the command's own."""

import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime, write_ini
from viwo import cli
from viwo.cli_boot import boot_for_cli, run_overrides
from viwo.contracts.errors import ViwoError
from viwo.core.wiring.boot import boot

ENGINES = ("renpy", "unity", "godot", "doom", "source", "electron")


class PluginFlagTests(unittest.TestCase):
    def test_the_flags_win_over_the_ini_and_say_so(self) -> None:
        rng = random.Random(48)
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(6):
                ini = {p: rng.random() < 0.5 for p in ENGINES}
                asked = {p: rng.random() < 0.5 for p in rng.sample(ENGINES, rng.randint(1, 4))}
                body = "[plugins]\n" + "".join(
                    f"{p} = {'on' if on else 'off'}\n" for p, on in ini.items()
                )
                path = write_ini(Path(tmp), body)
                rt = boot(path, temp_root=Path(tmp) / "t", overrides=(asked, {}))
                for plugin in ENGINES:
                    self.assertEqual(plugin in rt.plugins, {**ini, **asked}[plugin], plugin)
                    want = "cli" if plugin in asked else "ini"
                    self.assertEqual(rt.config.sources[f"plugins.{plugin}"], want)

    def test_an_unknown_plugin_is_said(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ini(Path(tmp))
            rt = boot(path, temp_root=Path(tmp) / "t", overrides=({"nosuch": True}, {}))
            self.assertTrue(any("nosuch" in p for p in rt.problems), rt.problems)


class SlotFlagTests(unittest.TestCase):
    def test_a_slot_is_bound_as_asked_and_a_bad_id_is_replaced_aloud(self) -> None:
        rng = random.Random(49)
        with tempfile.TemporaryDirectory() as tmp:
            base = runtime(Path(tmp))
            both = [s for s, b in sorted(base.bindings.items()) if b.main and b.spare]
            self.assertTrue(both)  # some slot has a main and a spare to swap
            for slot in rng.sample(both, min(3, len(both))):
                was = base.bindings[slot]
                path = write_ini(Path(tmp))
                swap = {slot: (was.spare, was.main)}
                rt = boot(path, temp_root=Path(tmp) / "t", overrides=({}, swap))
                now = rt.bindings[slot]
                self.assertEqual((now.main, now.spare, now.source), (was.spare, was.main, "cli"))
                self.assertEqual(rt.config.sources[f"slots.{slot}"], "cli")
                alone = boot(
                    path, temp_root=Path(tmp) / "t", overrides=({}, {slot: (was.main, "")})
                )
                self.assertEqual(
                    (alone.bindings[slot].main, alone.bindings[slot].spare), (was.main, "")
                )
                bad = boot(path, temp_root=Path(tmp) / "t", overrides=({}, {slot: ("nosuch", "")}))
                self.assertEqual(bad.bindings[slot].main, was.main)  # the default, and said
                self.assertTrue(any(slot in p and "nosuch" in p for p in bad.problems))
                others = {s: (b.main, b.spare) for s, b in rt.bindings.items() if s != slot}
                self.assertEqual(
                    others, {s: (b.main, b.spare) for s, b in base.bindings.items() if s != slot}
                )
            lost = boot(
                write_ini(Path(tmp)),
                temp_root=Path(tmp) / "t",
                overrides=({}, {"no.slot": ("x", "")}),
            )
            self.assertTrue(any("no.slot" in p for p in lost.problems))


class FlagTextTests(unittest.TestCase):
    def test_the_forms_are_read_and_anything_else_is_refused_with_the_form(self) -> None:
        args = SimpleNamespace(
            plugin_overrides=["RenPy=ON", " unity = off "],
            slot_overrides=["Unarchive.Zip=a,b", "decode.audio=none,c", "x.y=only"],
        )
        plugins, slots = run_overrides(args)
        self.assertEqual(plugins, {"renpy": True, "unity": False})
        want = {"unarchive.zip": ("a", "b"), "decode.audio": ("", "c"), "x.y": ("only", "")}
        self.assertEqual(slots, want)
        self.assertIsNone(run_overrides(SimpleNamespace()))
        for flag, texts in (
            ("plugin_overrides", ("renpy", "renpy=maybe", "=on", "renpy=")),
            ("slot_overrides", ("unarchive.zip", "=a", "s=a,b,c", "s=")),
        ):
            for text in texts:
                with self.assertRaises(ViwoError) as caught:
                    run_overrides(SimpleNamespace(**{flag: [text]}))
                self.assertIn("expected <", str(caught.exception))
                self.assertIn(text, str(caught.exception))

    def test_after_the_command_the_flags_are_the_commands_own(self) -> None:
        parser = cli._parser()
        args = parser.parse_args(
            ["--slot", "a.b=c", "unpack", "f.zip", "--out", "o", "--slot", "unarchive.7z"]
        )
        self.assertEqual((args.slot_overrides, args.slot), (["a.b=c"], "unarchive.7z"))
        line = ["--plugin", "renpy=off", "extract", "g", "--workspace", "w", "--plugin", "unity"]
        args = parser.parse_args(line)
        self.assertEqual((args.plugin_overrides, args.plugin), (["renpy=off"], "unity"))
        with tempfile.TemporaryDirectory() as tmp:
            ini = str(write_ini(Path(tmp), "[plugins]\nrenpy = on\n"))
            early = boot_for_cli(["--ini", ini, "--plugin", "renpy=off", "info"])
            self.assertNotIn("renpy", early.plugins)
            late = boot_for_cli(["--ini", ini, "extract", "g", "--plugin", "renpy=off"])
            self.assertIn("renpy", late.plugins)  # the command's flag is not a wiring flag


if __name__ == "__main__":
    unittest.main()
