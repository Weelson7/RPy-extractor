"""What makes a live patch hold up in a real guest (doc 11.8, core.isolation.patching): a located
program that restarted is located again and one that is gone is said (with the vm_detected
hint); pages not in RAM yet are waited for and the wait is said; bytes the program puts back are
written again while held, each revert counted; a module other processes map too is said; a
whole-guest snapshot is taken first when asked. Properties over a fake physical memory."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_isolation_guest import P, PhysSession, x64_space
from viwo.contracts.errors import ViwoError
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.core.isolation import guest, patching


def _view(base: int = 0x40000000, shared: int = 0) -> dict:
    module = {"name": "Game.exe", "base": base, "size": 0x2000, "path": "C:/g/Game.exe"}
    return {"pid": 8, "process": "Game.exe", "dtb": 0x1000, "mode": "x64",
            "modules": [{**module, "shared": shared}]}  # fmt: skip


class PatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.where = Path(self._tmp.name)
        self.mem = x64_space()
        self.mem.q(0x4000, 0xB000 | P)  # VA 0x40000000 -> PA 0xB000: the program's header
        self.mem.write(0xB000, b"MZ")
        self.session = PhysSession(self.mem)
        self.lines: list[tuple[str, str]] = []

    def _log(self, message: str, level: str = "info") -> None:
        self.lines.append((level, message))

    def _save(self, view: dict) -> None:
        (self.where / guest.VIEW).write_text(json.dumps(view), encoding="utf-8")

    def test_a_program_still_in_place_keeps_its_view(self) -> None:
        self._save(_view())
        self.assertTrue(guest.present(self.session, _view()))
        self.assertEqual(patching.fresh_view(None, self.session, self.where, self._log)["pid"], 8)

    def test_a_restarted_program_is_located_again(self) -> None:
        self.mem.write(0xB000, b"\0\0")  # its header is gone from where it was located
        self._save(_view())

        def again(rt, session, where, want, log):
            self.assertEqual(want, "Game.exe")
            self._save({**_view(), "pid": 12})

        with mock.patch.object(guest, "locate", again):
            view = patching.fresh_view(None, self.session, self.where, self._log)
        self.assertEqual(view["pid"], 12)
        self.assertTrue(any("locating it again" in m for _, m in self.lines))

    def test_a_program_that_is_gone_is_said_with_the_vm_hint(self) -> None:
        self.mem.write(0xB000, b"\0\0")
        self._save(_view())
        gone = ViwoError("not_found", "no process 'Game.exe' in the guest")
        with mock.patch.object(guest, "locate", side_effect=gone):
            with self.assertRaises(ViwoError) as said:
                patching.fresh_view(None, self.session, self.where, self._log)
        self.assertIn("gone from the guest", said.exception.message)
        self.assertIn("vm_detected", said.exception.hint)
        self.assertIsNone(guest.load(self.where))  # the stale view is dropped

    def test_pages_not_in_ram_are_waited_for(self) -> None:
        not_yet = {"written": False, "results": [{"detail": "0x1 is not resident (level 12)"}]}
        done = {"written": True, "results": [{"detail": ""}]}
        with mock.patch.object(patching.live, "apply_live", side_effect=[not_yet, done]), \
                mock.patch.object(patching.time, "sleep"):  # fmt: skip
            report = patching._until_resident(patching.live.apply_live, 5, self._log)
        self.assertTrue(report["written"])
        self.assertTrue(any("not in guest RAM yet" in m for _, m in self.lines))
        with mock.patch.object(patching.live, "apply_live", return_value=not_yet):
            once = patching._until_resident(patching.live.apply_live, 0, self._log)
        self.assertNotIn("waited", once)  # no wait asked: one try, as before

    def test_hold_writes_back_what_the_program_reverts(self) -> None:
        self.mem.write(0x9000, b"NEW")
        view = guest.ProcessView(self.session, _view())
        entry = {"addr": 0x40001000, "old": b"OLD".hex(), "new": b"NEW".hex(), **view.tag()}
        reads = iter([b"OLD", b"NEW", b"NEW"])
        clock = iter([0.0, 0.1, 0.2, 0.3, 9.9])
        fake_read = lambda s, a, n: next(reads, b"NEW")  # noqa: E731
        with mock.patch.object(guest.ProcessView, "read_mem", fake_read), \
                mock.patch.object(patching.time, "monotonic", lambda: next(clock, 99.0)), \
                mock.patch.object(patching.time, "sleep"):  # fmt: skip
            reverts = patching._hold(view, [entry], 1.0, self._log)
        self.assertEqual(reverts, 1)
        self.assertTrue(any("put back" in m for _, m in self.lines))

    def test_shared_modules_are_said(self) -> None:
        patch_set = {"patches": [{"file": "bin/Game.exe"}]}
        self.assertEqual(patching._shared(_view(shared=3), patch_set, self._log),
                         ["Game.exe (3 other processes)"])  # fmt: skip
        self.assertEqual(patching._shared(_view(), patch_set, self._log), [])

    def test_locate_counts_the_other_processes_that_map_each_module(self) -> None:
        procs = guest.processes([
            {"OS": "windows", "PID": p, "Process": "x", "DTB": 0, "Mode": "x64",
             "Module": m, "Base": 1, "Size": 1, "Path": f"C:/w/{m}"}
            for p, m in ((1, "a.exe"), (1, "k32.dll"), (2, "b.exe"), (2, "k32.dll"), (3, "K32.DLL"))
        ])  # fmt: skip
        counted = guest._shared(procs[0], procs)
        self.assertEqual([m["shared"] for m in counted["modules"]], [0, 2])  # case-insensitive

    def test_patch_takes_a_snapshot_first_when_asked(self) -> None:
        patch_set = self.where / "s.patch.json"
        patch_set.write_text(json.dumps({"patches": []}), encoding="utf-8")
        opt = {"exe": self.where / "Game.exe", "patchset": patch_set, "snapshot": True}
        with mock.patch.object(patching.patchsets, "load", return_value={"patches": []}), \
                mock.patch.object(patching.live, "apply_live",
                                  return_value={"written": False, "results": []}):  # fmt: skip
            report = patching.patch(None, self.session, self.where, opt, self._log)
        self.assertTrue(report["snapshot"].startswith(patching.SNAPSHOT + "-"))
        with self.assertRaises(ViwoError):
            patching.patch(None, self.session, self.where, {}, self._log)

    def test_a_program_that_exits_after_the_patch_puts_the_guest_back(self) -> None:
        self._save(_view())
        rolled: list[str] = []
        self.session.rollback = lambda name: rolled.append(name) or Outcome(OutcomeKind.OK)

        def exits(*args):  # the patch lands, then the program's check ends it
            self.mem.write(0xB000, b"\0\0")
            return {"written": True, "results": []}

        opt = {"exe": self.where / "Game.exe", "patchset": self.where / "s.json", "snapshot": True}
        with mock.patch.object(patching.patchsets, "load", return_value={"patches": []}), \
                mock.patch.object(patching.live, "apply_live", exits):  # fmt: skip
            report = patching.patch(None, self.session, self.where, opt, self._log)
        self.assertTrue(report["exited"])
        self.assertEqual(rolled, [report["snapshot"]])
        self.assertEqual(report["rolled_back"], report["snapshot"])

    def test_undo_only_puts_back_what_is_still_its_own(self) -> None:
        view = guest.ProcessView(self.session, _view())
        self.mem.write(0x9000, b"NEW")
        entry = {"addr": 0x40001000, "old": b"OLD".hex(), "new": b"NEW".hex(), **view.tag()}
        journal = self.where / "journal.jsonl"
        journal.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        self.mem.write(0x9000, b"XYZ")  # the guest changed since (another boot, another program)
        self.assertEqual(patching.live.undo(self.session, journal)["restored"], 0)
        self.assertEqual(self.mem.read(0x9000, 3), b"XYZ")  # not overwritten
        self.mem.write(0x9000, b"NEW")
        self.assertEqual(patching.live.undo(self.session, journal)["restored"], 1)
        self.assertEqual(self.mem.read(0x9000, 3), b"OLD")

    def test_no_write_without_the_old_bytes(self) -> None:
        view = guest.ProcessView(self.session, _view())
        log: list[dict] = []
        with mock.patch.object(patching.live, "located_va", lambda d, o, b: 0x40002000):
            wall = patching.live.write_located(view, b"", 0, b"NEW", 0, log)  # not resident
        self.assertTrue(wall.blocked)
        self.assertEqual(log, [])

    def test_a_raw_edit_stays_in_the_vcpus_address_space_of_the_moment(self) -> None:
        self.session.cpu_paging = lambda: {"dtb": 0x1000, "mode": "x64"}
        self.mem.write(0x9000, b"OLD")
        log: list[dict] = []
        with mock.patch.object(patching.live, "located_va", lambda d, o, b: 0x40001000):
            wall = patching.live.write_located(self.session, b"", 0, b"NEW", 0, log)
        self.assertFalse(wall.blocked, wall.detail)
        self.assertEqual((log[0]["dtb"], log[0]["old"]), (0x1000, b"OLD".hex()))  # undo finds it
        self.assertIs(guest.pinned(guest.ProcessView(self.session, _view())).inner, self.session)


if __name__ == "__main__":
    unittest.main()
