"""L3: properties at the edges of the pipeline and its tools. Duplicate cleaning never trashes
the last copy of any content; plugin sanitizer rules are taken only under their plugin's id;
QuickBMS names a missing scripts folder, tool or script and a run that wrote nothing; survey
reports are found by id only inside their folder and a damaged one is skipped; a backend that
raises is a named failure in the failover; the carve stage says its failures and fallbacks."""

from __future__ import annotations

import hashlib
import os
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.contracts import ViwoError
from viwo.contracts.slots import SlotBinding
from viwo.contracts.types import Outcome, OutcomeKind


def _contents(ws: Path) -> set[str]:
    return {
        hashlib.sha256(p.read_bytes()).hexdigest()
        for p in ws.rglob("*")
        if p.is_file() and not p.relative_to(ws).parts[0].startswith(".")
    }


class DuplicateTests(unittest.TestCase):
    def test_no_content_ever_loses_its_last_copy(self) -> None:
        from viwo.core import sanitizer

        rng = random.Random(15)
        for _ in range(12):
            with tempfile.TemporaryDirectory() as tmp:
                ws = Path(tmp) / "ws"
                (ws / ".viwo-workspace").parent.mkdir(parents=True)
                (ws / ".viwo-workspace").write_text("")
                blobs = [rng.randbytes(rng.randint(20, 60)) for _ in range(rng.randint(1, 4))]
                for i in range(rng.randint(2, 14)):
                    path = ws / rng.choice(["a", "b", "c"]) / f"f{i}{rng.choice(['', '__2'])}.bin"
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(rng.choice(blobs))
                before = _contents(ws)
                plan = sanitizer.plan(ws)
                sanitizer.apply(ws, plan["planId"])
                self.assertEqual(_contents(ws), before)  # every content kept at least once


class RuleCollectionTests(unittest.TestCase):
    def test_plugin_rules_only_under_their_own_id(self) -> None:
        from viwo.core.sanitizer_rules import SanitizerRule, collect_rules, rule_ids, sniff

        class Mine(SanitizerRule):
            rule_id, owner = "unity.atlas", "unity"

        class Foreign(SanitizerRule):
            rule_id, owner = "core.sneaky", "unity"

        plugin = SimpleNamespace(sanitizer_rules=lambda: [Mine(), Foreign(), "not a rule"])
        ids = [r.rule_id for r in collect_rules(SimpleNamespace(plugins={"unity": plugin}))]
        self.assertIn("unity.atlas", ids)
        self.assertNotIn("core.sneaky", ids)  # a plugin cannot speak for core
        self.assertEqual(Mine().inspect(Path("x"), None), [])
        self.assertTrue(Mine().applies_to(Path("x")))
        self.assertEqual(Mine().dependencies(), ())
        self.assertIn("core.health", rule_ids([SimpleNamespace(rule_id="core.extension")]))
        with tempfile.TemporaryDirectory() as tmp:
            small = Path(tmp) / "s.png"
            small.write_bytes(b"\x89PNG")
            self.assertIsNone(sniff(small))  # too small to carry a format


class QuickBmsTests(unittest.TestCase):
    def test_every_missing_piece_and_an_empty_run_are_named(self) -> None:
        from viwo.plugins.quickbms import QuickBmsCli, ScriptTable

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            table = ScriptTable()
            with self.assertRaisesRegex(ValueError, "scripts folder not found"):
                table.load(str(root / "nowhere"))
            (root / "scripts").mkdir()
            (root / "scripts" / "dat.bms").write_text("get SIZE asize")
            table.load(str(root / "scripts"))
            tool = SimpleNamespace(argv_prefix=("quickbms",))
            for located, ok, wrote in (
                (False, True, 0),
                (True, False, 0),
                (True, True, 0),
                (True, True, 2),
            ):
                dest = root / f"d{located}{ok}{wrote}"
                dest.mkdir()
                for i in range(wrote):
                    (dest / f"o{i}").write_bytes(b"x")
                ctx = SimpleNamespace(
                    cancel=None,
                    os=SimpleNamespace(
                        tools=SimpleNamespace(locate=lambda s, on=located: tool if on else None),
                        process=SimpleNamespace(
                            run=lambda argv, timeout, cancel, ok=ok: SimpleNamespace(
                                ok=ok, stderr="script error", stdout=""
                            )
                        ),
                    ),
                )
                out = QuickBmsCli(table).extract(root / "game.dat", dest, ctx)
                want = (
                    OutcomeKind.UNAVAILABLE
                    if not located
                    else (OutcomeKind.OK if ok and wrote else OutcomeKind.FAILED)
                )
                self.assertEqual(out.kind, want, (located, ok, wrote))
            self.assertEqual(
                QuickBmsCli(table).extract(root / "game.pak", dest, ctx).kind,
                OutcomeKind.UNAVAILABLE,
            )


class SurveyStoreTests(unittest.TestCase):
    def test_reports_by_id_inside_their_folder_only(self) -> None:
        from viwo.core import surveys

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for bad in ("../../etc/passwd", "x"):
                with self.assertRaises(ViwoError):
                    surveys.load(root, bad)
            with self.assertRaises(ViwoError) as err:
                surveys.load(root, "20260101-000000-games")
            self.assertEqual(err.exception.code, "not_found")
            (root / "20260101-000000-games.json").write_text("{damaged")
            self.assertEqual(surveys.list_reports(root), [])  # skipped, never a crash


class FailoverTests(unittest.TestCase):
    def test_a_raising_backend_is_a_named_failure_and_the_spare_runs(self) -> None:
        from viwo.core.pipeline.failover import run_with_failover

        def call(backend):
            if backend.name == "main":
                raise KeyError("index 7")
            return Outcome(OutcomeKind.OK, 1)

        backends = {"main": SimpleNamespace(name="main"), "spare": SimpleNamespace(name="spare")}
        out, used = run_with_failover(SlotBinding("s", "main", "spare"), backends, call)
        self.assertEqual((out.kind, used), (OutcomeKind.OK, "spare"))
        self.assertIn("KeyError", out.fallback)  # the main's bug travels with the result


class CarveStageTests(unittest.TestCase):
    def test_carve_failures_fallbacks_and_big_files_are_said(self) -> None:
        from viwo.contracts.pipeline import CarveMode
        from viwo.core.pipeline import carving

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blobs = []
            for i in range(3):
                blob = root / f"blob{i}.bin"
                blob.write_bytes(bytes(5000))
                blobs.append((blob, f"blob{i}.bin"))
            logs, cancel = [], SimpleNamespace(cancelled=False)
            answers = iter(
                [
                    (
                        Outcome(
                            OutcomeKind.FAILED,
                            error="carver broke",
                            fallback="main failed; used spare",
                        ),
                        "spare",
                    ),
                    (Outcome(OutcomeKind.OK, 2), "signature-carver"),
                ]
            )

            def answer(*a, **k):
                out = next(answers)
                cancel.cancelled = out[0].ok  # the user cancels after the second file
                return out

            run = SimpleNamespace(
                cancel=cancel,
                log=lambda msg, stage, level="info": logs.append((level, msg)),
                rt=SimpleNamespace(
                    bindings={"carve.signatures": SlotBinding("c", "signature-carver")},
                    backends={},
                    slots={},
                ),
                request=SimpleNamespace(carve=CarveMode.ALL),
                ctx=lambda owner: SimpleNamespace(),
                work=root / "work",
            )
            with (
                mock.patch.object(carving, "run_with_failover", side_effect=answer),
                mock.patch.object(carving, "BIG", 10),
                mock.patch.dict(os.environ, {"VIWO_WORKERS": "1"}),  # one at a time: in order
            ):
                report = carving.carve_all(run, frozenset(), blobs)
            self.assertEqual(report.scanned, 2)  # the cancel stopped before the third
            self.assertTrue(any("carver broke" in f for f in report.failures))
            self.assertTrue(any(level == "warn" and "used spare" in m for level, m in logs))
            self.assertTrue(any(m.startswith("Scanning blob0.bin") for _, m in logs))
            self.assertEqual(report.files, 2)


if __name__ == "__main__":
    unittest.main()
