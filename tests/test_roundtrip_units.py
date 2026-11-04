"""L3: the round trip's plan and build edges (doc 18): every edit lands in a plan item or a
named warning; the game a workspace came from is the newest extraction run, never a capture
record or a damaged one; a container behind a link, a failed packer and a crashing verify are
reported per container while the rest of the build goes on; a terms-sensitive plugin gets its
reminder."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import make_zip, runtime
from viwo.contracts import ViwoError
from viwo.contracts import workspace as ws
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.core import roundtrip
from viwo.core.roundtrip_edits import Edit


class PlanTests(unittest.TestCase):
    def test_every_edit_is_planned_or_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root)
            game = root / "game"
            make_zip(game / "data.zip", {"a.txt": b"a", "b.txt": b"b"})
            (game / "plain.bin").write_bytes(b"not a container")
            src = root / "edit.txt"
            src.write_text("edited")
            edits = [
                Edit(src, "loose", "", "readme.txt"),
                Edit(src, "added", "", "mods/new.txt"),
                Edit(src, "member", "data.zip", "a.txt"),
                Edit(src, "member", "plain.bin", "x"),  # not a container ViWo can pack
                Edit(src, "exported", "", "img.png", "nobody"),  # its plugin is not loaded
            ]
            originals = {"data.zip": {"a.txt": "1", "b.txt": "2"}}
            items, warnings = roundtrip.plan(rt, game, edits, originals)
            slots = {i.container: i.slot for i in items}
            self.assertEqual(slots, {"": "override", "data.zip": "pack.zip"})
            self.assertEqual(items[0].members.keys(), {"readme.txt", "mods/new.txt"})
            self.assertEqual(items[1].untouched, {"b.txt": "2"})  # what verify checks unchanged
            self.assertTrue(any(w.startswith("plain.bin: no packer") for w in warnings))
            self.assertEqual(len(warnings), 2)  # plain.bin, and the exported file
            with mock.patch.dict(rt.bindings, {"pack.zip": mock.Mock(bound=False)}):
                _, unbound = roundtrip.plan(rt, game, edits[2:3])
            self.assertIn("pack.zip has no available backend", unbound[0])

    def test_the_source_game_is_the_newest_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            runs = work / ws.RUNS_DIR
            runs.mkdir(parents=True)
            with self.assertRaises(ViwoError) as err:
                roundtrip.source_game(work)
            self.assertEqual(err.exception.code, "not_found")
            records = {
                "a.json": {"finished": "2026-01-01", "request": {"game_path": "C:/old"}},
                "b.json": {"finished": "2026-03-01", "request": {"game_path": "C:/new"}},
                "c.json": {"finished": "2026-09-01", "capture": True},  # no request
            }
            for name, data in records.items():
                (runs / name).write_text(json.dumps(data))
            (runs / "d.json").write_text("{damaged")
            self.assertEqual(roundtrip.source_game(work), Path("C:/new"))

    def test_terms_sensitive_plugins_get_their_reminder(self) -> None:
        rt = SimpleNamespace(
            slots={"export.overwatch": SimpleNamespace(owner="overwatch")},
            plugins={"overwatch": SimpleNamespace(manifest=SimpleNamespace(tos_sensitive=True))},
        )
        item = roundtrip.PlanItem("x", "export.overwatch")
        self.assertIn("respect the game's terms", roundtrip._reminders(rt, [item])[0])
        self.assertEqual(roundtrip._reminders(rt, []), [])


class ApplyTests(unittest.TestCase):
    def test_each_container_failure_is_reported_on_its_own(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root)
            target = root / "copy"
            make_zip(target / "data.zip", {"a.txt": b"a"})
            src = root / "edit.txt"
            src.write_text("edited")
            ctx = SimpleNamespace(scratch=root / "s" / "x", log=lambda *a, **k: None)
            (root / "s").mkdir()
            item = roundtrip.PlanItem("data.zip", "pack.zip", {"a.txt": src})
            packer = rt.backends[rt.bindings["pack.zip"].main]
            broken = Outcome(OutcomeKind.FAILED, error="disk full")
            with mock.patch.object(packer, "pack", return_value=broken):
                out = roundtrip._apply(rt, item, target, ctx)
            self.assertEqual((out["failed"], out["error"]), (["a.txt"], "disk full"))
            with mock.patch.object(packer, "verify", side_effect=RuntimeError("verify blew up")):
                out = roundtrip._apply(rt, item, target, ctx)
            self.assertIn("verify failed", out["error"])
            outside = roundtrip.PlanItem("../escape.zip", "pack.zip", {"a.txt": src})
            out = roundtrip._apply(rt, outside, target, ctx)
            self.assertIn("outside the copy", out["error"])
            loose = roundtrip.PlanItem("", "override", {"ok.txt": src, "../evil.txt": src})
            out = roundtrip._apply(rt, loose, target, ctx)
            self.assertEqual(out["failed"], ["../evil.txt"])
            self.assertFalse((root / "evil.txt").exists())
            packed = root / "not-a-container.bin"
            packed.write_bytes(b"junk")
            bad = roundtrip._verify(
                rt, packed, roundtrip.PlanItem("c", "s", {"m": src}, {"u": "1"}), ctx
            )
            self.assertEqual(
                sorted(bad), ["m", "u"]
            )  # nothing re-extracts: everything is unverified

    def test_a_build_needs_a_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = [roundtrip.PlanItem("", "override", {"a": root})]
            with mock.patch.object(roundtrip, "source_game", return_value=root):
                with mock.patch.object(roundtrip, "edit_set", return_value=([], [])):
                    with mock.patch.object(roundtrip, "plan", return_value=(item, [])):
                        with self.assertRaises(ViwoError) as err:
                            roundtrip.repack(runtime(root), root, None)
            self.assertEqual(err.exception.code, "invalid_request")


if __name__ == "__main__":
    unittest.main()
