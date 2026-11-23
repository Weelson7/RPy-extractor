"""L5: the isolation arm's QEMU tier against a real QEMU (doc 11.8, 17.2; skipped unless
VIWO_L5=1 and a QEMU is found: the pinned one under third_party/ or VIWO_QEMU). The guest is a
boot sector the test writes itself: it loops in place with a marker beside its code, which the
BIOS loads at 0x7C00, so every step is checked against bytes the test knows. No OS is booted."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from tests.test_l5_tools import L5, real_runtime
from viwo.contracts.errors import ViwoError
from viwo.core.isolation import atomic_write, live
from viwo.core.isolation import session as sessions
from viwo.core.isolation.qemu import HARDWARE, QEMU

MARK, AT = b"VIWO-MARK-0123456789", 0x7C10


def boot_sector() -> bytes:
    sector = bytearray(512)
    sector[0:2] = b"\xeb\xfe"  # jmp $: the guest spins where it starts
    sector[16 : 16 + len(MARK)] = MARK
    sector[510:512] = b"\x55\xaa"
    return bytes(sector) + bytes((1 << 20) - 512)


@L5
class RealQemuTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        (self.root / "rt").mkdir()
        self.rt = real_runtime(self.root / "rt")
        if self.rt.os.tools.locate(QEMU) is None:
            self.skipTest("QEMU not installed (viwo install qemu, or VIWO_QEMU)")
        self.ws = self.root / "ws"
        self.image = self.root / "boot.img"
        self.image.write_bytes(boot_sector())
        self.lines: list[str] = []

    def tearDown(self) -> None:
        try:
            sessions.act(self.rt, self.ws, "stop")
        except ViwoError:
            pass
        self._tmp.cleanup()

    def _start(self, **guest) -> dict:
        guest = {"memory_mb": 64, "cpus": 1, "headless": True, **guest}
        req = sessions.IsolateRequest(self.ws, self.image, guest=guest, snapshot=bool(guest))
        info, session = sessions.start(self.rt, req, lambda e: self.lines.append(e.legacy_line()))
        self.addCleanup(session.close)
        return info

    def _session(self):
        session, _ = sessions._rejoin(self.rt, self.ws, None)
        self.addCleanup(session.release)
        return session

    def _wait_for_mark(self, session) -> None:
        end = time.monotonic() + 30
        while session.read_mem(AT, len(MARK)) != MARK:  # the BIOS has not loaded the sector yet
            self.assertLess(time.monotonic(), end, "the boot sector never reached 0x7C00")
            time.sleep(0.2)

    def test_tcg_session_patches_journals_snapshots_and_rolls_back(self) -> None:
        info = self._start(accel="tcg")
        self.assertEqual((info["tier"], info["accel"]), ("qemu", "tcg"))
        self.assertEqual(self.image.read_bytes(), boot_sector())  # the image is not opened to write
        with self.assertRaises(ViwoError) as twice:  # one session per workspace
            sessions.start(self.rt, sessions.IsolateRequest(self.ws, self.image))
        self.assertEqual(twice.exception.code, "busy")
        session = self._session()
        self._wait_for_mark(session)
        self.assertTrue(session.running())  # a read leaves the guest as it found it
        session.release()  # QEMU serves one control client at a time
        made = sessions.act(self.rt, self.ws, "snapshot", name="clean")
        self.assertEqual(made["snapshot"], "clean")
        log: list[dict] = []
        wall = live.write_located(session, b"", AT, b"PATCHED!", log=log)
        self.assertFalse(wall.blocked, wall.detail)
        self.assertEqual(session.read_mem(AT, 8), b"PATCHED!")
        self.assertEqual(log[0]["old"], MARK[:8].hex())  # the journal holds what was replaced
        journal = sessions.folder(self.ws) / "journal.jsonl"
        journal.write_text("".join(json.dumps(e) + "\n" for e in log))
        session.release()
        self.assertEqual(sessions.act(self.rt, self.ws, "undo"), {
            "tier": "qemu", "action": "undo", "restored": 1, "edits": 1})  # fmt: skip
        self.assertEqual(session.read_mem(AT, len(MARK)), MARK)
        self.assertFalse(atomic_write(session, AT, b"SECOND!!").blocked)
        with self.assertRaises(ViwoError) as held:  # the channel is held: busy, not "gone"
            sessions.act(self.rt, self.ws, "status")
        self.assertEqual(held.exception.code, "busy")
        session.release()
        sessions.act(self.rt, self.ws, "rollback", name="clean")
        self.assertEqual(session.read_mem(AT, len(MARK)), MARK)  # the snapshot took it back

    def test_pause_resume_dump_and_stop(self) -> None:
        self._start(accel="tcg")
        session = self._session()
        self._wait_for_mark(session)
        session.release()
        self.assertFalse(sessions.act(self.rt, self.ws, "pause")["running"])
        self.assertTrue(sessions.act(self.rt, self.ws, "resume")["running"])
        dump = sessions.act(self.rt, self.ws, "dump", name="core")
        self.assertGreater(dump["size"], 64 << 20)  # the whole guest RAM, as an ELF core
        with open(dump["dump"], "rb") as fh:
            self.assertEqual(fh.read(4), b"\x7fELF")
        self.assertTrue(sessions.act(self.rt, self.ws, "stop")["stopped"])
        with self.assertRaises(ViwoError) as gone:
            sessions.act(self.rt, self.ws, "status")
        self.assertEqual(gone.exception.code, "not_found")

    def test_hardware_acceleration_runs_and_says_what_it_cannot_do(self) -> None:
        req = sessions.IsolateRequest(
            self.ws, self.image, guest={"memory_mb": 64, "cpus": 1, "headless": True}
        )
        info, held = sessions.start(self.rt, req)
        self.addCleanup(held.close)
        if info["accel"] != HARDWARE:
            self.skipTest(f"no {HARDWARE} on this machine: QEMU fell back to {info['accel']}")
        session = self._session()
        self._wait_for_mark(session)
        self.assertFalse(atomic_write(session, AT, b"HW-WRITE").blocked)
        session.release()
        if os.name == "nt":  # WHPX cannot save state: said, not a silent failure
            with self.assertRaises(ViwoError) as blocked:
                sessions.act(self.rt, self.ws, "snapshot", name="s1")
            self.assertEqual(blocked.exception.code, "unavailable")
            self.assertIn("WHPX", blocked.exception.message)


if __name__ == "__main__":
    unittest.main()
