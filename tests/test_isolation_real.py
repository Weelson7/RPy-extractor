"""L5: the isolation arm's QEMU tier against a real QEMU (doc 11.8, 17.2; skipped unless
VIWO_L5=1 and a QEMU is found: the pinned one under third_party/ or VIWO_QEMU). The guest is a
boot sector the test writes itself: it loops in place with a marker beside its code, which the
BIOS loads at 0x7C00, so every step is checked against bytes the test knows. A second guest
(`long_mode_sector`) enters 64-bit long mode with page tables of its own that map a virtual
address onto a different physical page, so the page walk and physical-memory access are proven
on a real vCPU's paging. No OS is booted."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.test_l5_tools import L5, real_runtime
from viwo.contracts.errors import ViwoError
from viwo.core.isolation import atomic_write, live
from viwo.core.isolation import session as sessions
from viwo.core.isolation.qemu import HARDWARE, QEMU

MARK, AT = b"VIWO-MARK-0123456789", 0x7C10
# long_mode_sector: PML4 at 0x1000; VA 0x40001000 -> PA 0x9000 (a copy of the marker) through
# PDPT[1] -> PD 0x5000 -> PT 0x4000; the first 2 MB identity-mapped by one large page. After the
# switch the guest counts in the qword at PA 0x9100, so a test sees whether it runs.
DTB, VA, PA, COUNTER = 0x1000, 0x40001000, 0x9000, 0x9100
LONG_CODE = bytes.fromhex(
    "fa31c08ed88ec08ed0bc007cfcbf0010b90028f3abbe007dbf0090b92000f3a4"  # zero 0x1000-0x6000,
    "c70600100320c70600200330c70608200350c70600308300c70600500340c70608400390"  # copy, tables
    "66b8001000000f22d80f20e06683c8200f22e066b9800000c00f32660d000100000f30"  # CR3, PAE, LME
    "0f0116d87c0f20c0660d010000800f22c0eae07c0800"  # lgdt, PG|PE, far jump to 0x7CE0 (64-bit)
)
LONG_LOOP = bytes.fromhex("48ff042500910000ebf6")  # inc qword [0x9100]; jmp back to it


def boot_sector() -> bytes:
    sector = bytearray(512)
    sector[0:2] = b"\xeb\xfe"  # jmp $: the guest spins where it starts
    sector[16 : 16 + len(MARK)] = MARK
    sector[510:512] = b"\x55\xaa"
    return bytes(sector) + bytes((1 << 20) - 512)


def long_mode_sector() -> bytes:
    """A boot sector that enters long mode with its own page tables, then counts forever."""
    sector = bytearray(512)
    sector[: len(LONG_CODE)] = LONG_CODE
    gdt = bytes(8) + bytes.fromhex("ffff0000009aaf00") + bytes.fromhex("ffff00000092cf00")
    sector[0xC0:0xD8] = gdt  # null, 64-bit code, data
    sector[0xD8:0xDE] = bytes.fromhex("1700c07c0000")  # GDTR: limit 23, base 0x7CC0
    sector[0xE0 : 0xE0 + len(LONG_LOOP)] = LONG_LOOP
    sector[0x100 : 0x100 + len(MARK)] = MARK  # 0x7D00, copied to PA 0x9000 before the switch
    sector[510:512] = bytes.fromhex("55aa")
    return bytes(sector) + bytes((1 << 20) - 512)


@L5
class RealQemuTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)  # first in, last out: after every session closed
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

    def _start(self, **guest) -> dict:
        guest = {"memory_mb": 64, "cpus": 1, "headless": True, **guest}
        req = sessions.IsolateRequest(
            self.ws, self.image, tier="qemu", guest=guest, snapshot=bool(guest)
        )
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
            sessions.start(self.rt, sessions.IsolateRequest(self.ws, self.image, tier="qemu"))
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
            self.ws, self.image, tier="qemu", guest={"memory_mb": 64, "cpus": 1, "headless": True}
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

    def test_a_process_view_walks_the_guests_own_page_tables(self) -> None:
        from viwo.core.isolation import guest

        self.image.write_bytes(long_mode_sector())
        self._start(accel="tcg")
        session = self._session()
        end = time.monotonic() + 30
        while session.read_mem(VA, len(MARK)) != MARK:  # the guest has switched to long mode
            self.assertLess(time.monotonic(), end, "the guest never reached long mode")
            time.sleep(0.2)
        with session.physical() as mem:  # PA 0x9000 holds it; PA 0x40001000 is not RAM at all
            self.assertEqual(mem.read(PA, len(MARK)), MARK)
        view = guest.ProcessView(session, {"pid": 1, "dtb": DTB, "mode": "x64"})
        self.assertEqual(view.read_mem(VA, len(MARK)), MARK)
        self.assertFalse(atomic_write(view, VA + 4, b"PAGE").blocked)
        with session.physical() as mem:
            self.assertEqual(mem.read(PA, 8), b"VIWOPAGE")  # landed where the walk said
        self.assertEqual(session.read_mem(VA, 8), b"VIWOPAGE")  # and the vCPU sees it there
        far = view.read_mem(0x7FFF0000, 4)  # nothing mapped: said, not garbage
        self.assertEqual((far, view.wall().wall.value), (b"", "not_ready"))
        self.assertIn("not resident", view.wall().detail)

    def test_locate_runs_volatility_on_a_real_dump_and_says_when_there_is_no_os(self) -> None:
        from tests.test_l5_tools import HOME
        from viwo.core import workers

        if workers.argv("volatility3", HOME) is None:
            self.skipTest("Volatility 3 not installed (viwo install volatility3)")
        self._start(accel="tcg")
        session = self._session()
        self._wait_for_mark(session)
        session.release()  # QEMU serves one control client at a time
        with mock.patch("viwo.core.thirdparty.home_of", lambda config: HOME):
            with self.assertRaises(ViwoError) as no_os:
                say = lambda e: self.lines.append(e.message)  # noqa: E731
                sessions.act(self.rt, self.ws, "locate", say=say)
        self.assertIn("Volatility could not read the guest", no_os.exception.message)
        self.assertTrue(any("Dumping the guest's RAM" in line for line in self.lines))
        self.assertFalse((sessions.folder(self.ws) / "guest-ram.elf").exists())  # removed


if __name__ == "__main__":
    unittest.main()
