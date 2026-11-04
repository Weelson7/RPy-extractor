"""L1/L4: ini, binder, failover, selection (every combination), identify, workspace."""

from __future__ import annotations

import itertools
import random
import tempfile
import unittest
from pathlib import Path

from tests.helpers import FakeUnarchiver, make_zip, write_ini
from viwo.contracts import (
    DetectionResult,
    ExtractionMode,
    ExtractionRequest,
    Match,
    MixedPolicy,
    OnExisting,
    Outcome,
    OutcomeKind,
    SlotDefinition,
    ViwoError,
)
from viwo.contracts import workspace as ws
from viwo.core.pipeline.failover import run_with_failover
from viwo.core.pipeline.identify import carve, identify
from viwo.core.pipeline.select import select_plugins
from viwo.core.wiring.binder import bind_slot
from viwo.core.wiring.ini import load_ini
from viwo.core.workspace import resolve_target, workspace_lock
from viwo.os import select_os

SLOT = SlotDefinition("unarchive.x", "unarchive", "core", "main-b", "spare-b", suffixes=(".x",))


class IniTests(unittest.TestCase):
    def test_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            body = (
                "[startup]\nos = linux\nauto_install = on\n[plugins]\nunity = off\n"
                "[slots]\nunarchive.7z = py7zr, none\n[tools]\nsevenzip = bin/7z\n"
                "[options.godot]\nencryption_key = abc\nlevel = 2\n[weird]\nx = 1\n"
            )
            cfg = load_ini(write_ini(Path(tmp), body))
        self.assertEqual(
            (cfg.os_id, cfg.auto_install, cfg.plugins), ("linux", True, {"unity": False})
        )
        self.assertEqual(cfg.slots["unarchive.7z"], ("py7zr", ""))
        self.assertTrue(Path(cfg.tools["sevenzip"]).as_posix().endswith("bin/7z"))
        self.assertEqual(cfg.options, {"godot": {"level": "2"}})  # secret refused
        self.assertEqual(len(cfg.problems), 2)


class BinderAndFailoverTests(unittest.TestCase):
    def test_four_availability_cases(self) -> None:
        layer = select_os()
        for main_up, spare_up in itertools.product((True, False), repeat=2):
            backends = {
                "main-b": FakeUnarchiver("main-b", up=main_up),
                "spare-b": FakeUnarchiver("spare-b", up=spare_up),
            }
            b = bind_slot(SLOT, backends, None, layer)
            with self.subTest(main=main_up, spare=spare_up):
                expected = "main-b" if main_up else ("spare-b" if spare_up else "")
                self.assertEqual(b.main, expected)
                self.assertEqual(b.promoted, not main_up and spare_up)
                self.assertEqual(b.spare, "spare-b" if main_up and spare_up else "")

    def test_failover_outcomes(self) -> None:
        layer = select_os()
        cases = {
            OutcomeKind.FAILED: ("spare-b", 1),
            OutcomeKind.UNAVAILABLE: ("spare-b", 1),
            OutcomeKind.NEEDS_KEY: ("main-b", 0),
        }
        for kind, (used_expected, spare_calls) in cases.items():
            backends = {
                "main-b": FakeUnarchiver("main-b", kind),
                "spare-b": FakeUnarchiver("spare-b"),
            }
            binding = bind_slot(SLOT, backends, None, layer)
            with tempfile.TemporaryDirectory() as tmp:
                outcome, used = run_with_failover(
                    binding, backends, lambda b: b.extract(None, Path(tmp), None)
                )
            with self.subTest(kind=kind):
                self.assertEqual((used, backends["spare-b"].calls), (used_expected, spare_calls))
                self.assertEqual(outcome.ok, kind is not OutcomeKind.NEEDS_KEY)
                said = outcome.fallback  # a spare in use always says why
                self.assertEqual(
                    (said.startswith(f"main-b {kind.value}"), said.endswith("used spare-b")),
                    (spare_calls == 1, spare_calls == 1),
                )


class SayingTests(unittest.TestCase):
    """Never silent, as properties over random cases: what changed or failed is always named."""

    def test_change_warning_names_exactly_the_removed_files(self) -> None:
        from viwo.core.pipeline.guard import change_warning

        rng = random.Random(7)
        for _ in range(200):
            before = {f"f{i}.bin": (i, i) for i in range(rng.randint(0, 6))}
            after = {k: v for k, v in before.items() if rng.random() > 0.3}
            after.update({k: (99, 99) for k in after if rng.random() < 0.3})
            text = change_warning(before, after, "extraction")
            gone = sorted(set(before) - set(after))
            changed = gone + [k for k in after if after[k] != before[k]]
            self.assertEqual(bool(text), bool(changed))
            removed = text.split("antivirus: ")[1].rstrip(")").split(", ") if gone else []
            self.assertEqual(removed, gone[:5])
            self.assertTrue(all(k in text for k in sorted(changed)[:10]))

    def test_export_says_everything_worth_saying(self) -> None:
        from viwo.core.pipeline.export import _said

        rng = random.Random(3)
        for _ in range(100):
            files, notes = rng.choice((0, 4)), tuple(f"note{i}" for i in range(rng.randint(0, 3)))
            fallback = rng.choice(("", "main failed: CAUSE; used spare"))
            lines = _said(Outcome(OutcomeKind.OK, files, notes=notes, fallback=fallback), "s", "b")
            self.assertEqual(len(lines), bool(fallback) + (files == 0) + bool(notes))
            self.assertEqual(any("CAUSE" in line for line in lines), bool(fallback))
            self.assertEqual(
                any(str(len(notes)) in line and "note0" in line for line in lines), bool(notes)
            )


class SelectionTests(unittest.TestCase):
    IDS = ("generic", "renpy", "unity", "godot", "custom")

    def detections(self, ids, conf):
        return [DetectionResult(i, conf.get(i, 0.0), (), i) for i in ids]

    def test_every_combination(self) -> None:
        conf = {"generic": 0.4, "renpy": 0.9, "unity": 0.6, "godot": 0.0, "custom": 0.5}
        for size in range(1, len(self.IDS) + 1):
            for subset in itertools.combinations(self.IDS, size):
                dets = self.detections(subset, conf)
                for policy in MixedPolicy:
                    req = ExtractionRequest(
                        "g", mode=ExtractionMode.MIXED, plugins=subset, mixed_policy=policy
                    )
                    chosen = select_plugins(req, dets, {})
                    with self.subTest(subset=subset, policy=policy):
                        self.assertTrue(chosen)
                        self.assertEqual(len(chosen), len(set(chosen)))
                        self.assertLessEqual(set(chosen), set(subset))
                        if policy is not MixedPolicy.DETECTED:
                            self.assertEqual(set(chosen), set(subset))
                        self.assertEqual(chosen, select_plugins(req, dets[::-1], {}))

    def test_auto_and_fallback(self) -> None:
        dets = self.detections(self.IDS, {"generic": 0.4, "unity": 0.92, "renpy": 0.78})
        self.assertEqual(select_plugins(ExtractionRequest("g"), dets, {}), ("unity",))
        none = self.detections(self.IDS, {"generic": 0.4})
        self.assertEqual(select_plugins(ExtractionRequest("g"), none, {}), ("generic",))

    def test_random_confidences_keep_the_invariants(self) -> None:
        """Doc 3.6 property test: auto picks the strongest non-generic plugin, DETECTED is the
        set above the threshold, every answer is non-empty and order-independent."""
        rng = random.Random(1234)
        for _ in range(300):
            conf = {i: round(rng.random(), 3) for i in self.IDS}
            dets = self.detections(self.IDS, conf)
            auto = select_plugins(ExtractionRequest("g"), dets, {})
            ranked = sorted((i for i in self.IDS if i != "generic"), key=lambda i: (-conf[i], i))
            expected = (ranked[0],) if conf[ranked[0]] > 0 else ("generic",)
            self.assertEqual(auto, expected)
            req = ExtractionRequest(
                "g", mode=ExtractionMode.MIXED, plugins=self.IDS, mixed_policy=MixedPolicy.DETECTED
            )
            chosen = select_plugins(req, dets, {})
            strong = {i for i in self.IDS if conf[i] >= req.mixed_threshold}
            self.assertEqual(set(chosen), strong or {"generic"})
            shuffled = list(dets)
            rng.shuffle(shuffled)
            self.assertEqual(chosen, select_plugins(req, shuffled, {}))


class JobMemoryTests(unittest.TestCase):
    def test_a_long_server_keeps_recent_and_running_jobs_only(self) -> None:
        import threading

        from viwo.core.jobs import KEEP, JobRunner

        runner, release = JobRunner(), threading.Event()
        long = runner.submit("capture", lambda j, s, c: release.wait(30))
        ids = [
            runner.submit("survey", lambda j, s, c: {}, background=False).job_id
            for _ in range(KEEP + 60)
        ]
        kept = {j.job_id for j in runner.list()}
        self.assertLessEqual(len(kept), KEEP + 1)
        self.assertIn(long.job_id, kept)  # still running: never dropped
        self.assertTrue(set(ids[-KEEP + 1 :]) <= kept)  # the newest finished ones stay
        release.set()


class ProbeCacheTests(unittest.TestCase):
    def test_a_rewritten_file_is_read_again(self) -> None:
        import os

        from viwo.core.pipeline.probe import _read

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.pak"
            for i, body in enumerate((b"AAAA-old", b"BBBB-new", b"CC")):
                path.write_bytes(body)
                os.utime(path, ns=(10**18 + i * 10**9,) * 2)  # a later write, a later mtime
                self.assertEqual(
                    (_read(path, 4, False), _read(path, 2, True)), (body[:4], body[-2:])
                )
            path.unlink()
            self.assertEqual(_read(path, 4, False), b"")


class IdentifyTests(unittest.TestCase):
    def test_suffix_magic_custom_and_carve(self) -> None:
        tar = SlotDefinition(
            "unarchive.tar", "unarchive", "core", "a", suffixes=(".tar", ".tar.gz")
        )
        gz = SlotDefinition("unarchive.gz", "unarchive", "core", "a", suffixes=(".gz",))
        zipslot = SlotDefinition("unarchive.zip", "unarchive", "core", "a", magic=(b"PK\x03\x04",))
        tail = SlotDefinition(
            "unarchive.tail",
            "unarchive",
            "core",
            "a",
            identify=lambda p, h, t: (
                Match("unarchive.tail", p, 4, 3) if t.endswith(b"END") else None
            ),
        )
        slots = [gz, tar, zipslot, tail]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.tar.gz").write_bytes(b"x")
            make_zip(root / "noext", {"a": b"1"})
            make_zip(root / "doc.docx", {"a": b"1"})
            (root / "game.exe").write_bytes(b"HEADabcEND")
            self.assertEqual(identify(root / "a.tar.gz", slots).slot_id, "unarchive.tar")
            self.assertEqual(identify(root / "noext", slots).slot_id, "unarchive.zip")
            # doc 2.5: no slot claims .docx, so the PK head bytes decide (longest suffix first)
            self.assertEqual(identify(root / "doc.docx", slots).slot_id, "unarchive.zip")
            match = identify(root / "game.exe", slots)
            self.assertEqual(carve(match, root / "scratch").read_bytes(), b"abc")


class WorkspaceTests(unittest.TestCase):
    def test_ownership_and_policies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user = root / "user"
            user.mkdir()
            (user / "keep.txt").write_text("mine")
            with self.assertRaises(ViwoError) as err:
                resolve_target(user, OnExisting.REPLACE)
            self.assertEqual(err.exception.code, "refused")
            self.assertTrue((user / "keep.txt").exists())
            owned = resolve_target(root / "ws", OnExisting.ASK)
            (owned / "png").mkdir()
            (owned / ws.TRASH_DIR).mkdir()
            for policy, code in (
                (OnExisting.ASK, "needs_decision"),
                (OnExisting.CANCEL, "cancelled"),
            ):
                with self.assertRaises(ViwoError) as err:
                    resolve_target(owned, policy)
                self.assertEqual(err.exception.code, code)
            self.assertEqual(resolve_target(owned, OnExisting.NEW).name, "ws-2")
            self.assertEqual(resolve_target(owned, OnExisting.REPLACE), owned)
            self.assertFalse((owned / "png").exists())
            self.assertTrue((owned / ws.TRASH_DIR).exists())

    def test_lock_is_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, workspace_lock(Path(tmp)):
            with self.assertRaises(ViwoError) as err, workspace_lock(Path(tmp)):
                pass
            self.assertEqual(err.exception.code, "busy")


if __name__ == "__main__":
    unittest.main()


class BuiltinPluginTests(unittest.TestCase):
    def test_every_builtin_plugin_loads(self) -> None:
        from viwo.core.wiring.registry import BUILTIN_PLUGINS, load_enabled

        plugins, problems = load_enabled({pid: True for pid in BUILTIN_PLUGINS})
        self.assertEqual(sorted(plugins), sorted(BUILTIN_PLUGINS))
        self.assertEqual(problems, [])
