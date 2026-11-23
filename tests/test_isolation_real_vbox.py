"""L5: the isolation arm's VirtualBox tier against a real VirtualBox (doc 11.8, 17.2; skipped
unless VIWO_L5=1 and VBoxManage is found). The guest is test_isolation_real's long-mode boot
sector: 64-bit paging of its own (VA 0x40001000 -> PA 0x9000) and a counter it keeps bumping, so
every step is checked against bytes the test knows and a pause is seen to stop the guest. Proves
the session lifecycle, memory through the stub's console (VirtualBox's stub writes no other way),
the page walk on the vCPU's CR3 and on a given DTB, the journal and undo, live snapshots, the
ELF core and that the image itself is never written. No OS is booted."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from tests.test_isolation_real import COUNTER, DTB, MARK, PA, VA, long_mode_sector
from tests.test_l5_tools import L5, real_runtime
from viwo.contracts.errors import ViwoError
from viwo.core.isolation import atomic_write, guest, live
from viwo.core.isolation import session as sessions
from viwo.core.isolation.vbox import VBOX


@L5
class RealVirtualBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)  # first in, last out: after every session closed
        self.root = Path(self._tmp.name)
        (self.root / "rt").mkdir()
        self.rt = real_runtime(self.root / "rt")
        if self.rt.os.tools.locate(VBOX) is None:
            self.skipTest("VirtualBox not installed (VBoxManage, or VIWO_VBOXMANAGE)")
        self.ws = self.root / "ws"
        self.image = self.root / "long.img"
        self.image.write_bytes(long_mode_sector())

    def tearDown(self) -> None:
        try:
            sessions.act(self.rt, self.ws, "stop")
        except ViwoError:
            pass

    def _start(self) -> dict:
        guest_opts = {"memory_mb": 64, "cpus": 1, "headless": True}
        req = sessions.IsolateRequest(self.ws, self.image, tier="vbox", guest=guest_opts)
        info, session = sessions.start(self.rt, req)
        self.addCleanup(session.close)
        return info

    def _session(self):
        session, _ = sessions._rejoin(self.rt, self.ws, None)
        end = time.monotonic() + 60
        while session.read_mem(VA, len(MARK)) != MARK:  # the guest has reached long mode
            self.assertLess(time.monotonic(), end, f"no long mode: {session.wall().detail}")
            time.sleep(0.5)
        return session

    def _counter(self, session) -> int:
        with session.physical() as mem:
            return int.from_bytes(mem.read(COUNTER, 8), "little")

    def test_memory_paging_journal_undo_and_the_image_untouched(self) -> None:
        info = self._start()
        self.assertEqual(info["tier"], "vbox")
        session = self._session()
        self.assertEqual(self.image.read_bytes(), long_mode_sector())  # a copy was booted
        with session.physical() as mem:
            self.assertEqual(mem.read(PA, len(MARK)), MARK)
        view = guest.ProcessView(session, {"pid": 1, "dtb": DTB, "mode": "x64"})
        self.assertFalse(atomic_write(view, VA + 4, b"PAGE").blocked, view.wall().detail)
        self.assertEqual(session.read_mem(VA, 8), b"VIWOPAGE")  # the vCPU's own walk agrees
        log: list[dict] = []
        wall = live.write_located(session, b"", VA, b"PATCHED!", log=log)
        self.assertFalse(wall.blocked, wall.detail)
        self.assertEqual(log[0]["old"], b"VIWOPAGE".hex())
        journal = sessions.folder(self.ws) / "journal.jsonl"
        journal.write_text("".join(json.dumps(e) + "\n" for e in log))
        undone = sessions.act(self.rt, self.ws, "undo")
        self.assertEqual((undone["restored"], undone["edits"]), (1, 1))
        self.assertEqual(session.read_mem(VA, 8), b"VIWOPAGE")
        self.assertEqual(view.read_mem(0x7FFF0000, 4), b"")  # not mapped: a wall, said
        self.assertIn("not resident", view.wall().detail)

    def test_pause_stops_the_guest_snapshot_rollback_dump_and_stop(self) -> None:
        self._start()
        session = self._session()
        self.assertFalse(sessions.act(self.rt, self.ws, "pause")["running"])
        first = self._counter(session)
        time.sleep(1.0)
        self.assertEqual(self._counter(session), first)  # paused, and the stub kept it so
        self.assertTrue(sessions.act(self.rt, self.ws, "resume")["running"])
        time.sleep(1.0)
        self.assertGreater(self._counter(session), first)  # it runs again
        self.assertEqual(
            sessions.act(self.rt, self.ws, "snapshot", name="clean")["snapshot"], "clean"
        )
        self.assertFalse(atomic_write(session, VA, b"CHANGED!").blocked)
        sessions.act(self.rt, self.ws, "rollback", name="clean")
        session = self._session()  # the snapshot took the bytes back
        dump = sessions.act(self.rt, self.ws, "dump", name="core")
        with open(dump["dump"], "rb") as fh:
            self.assertEqual(fh.read(4), b"\x7fELF")
        self.assertGreater(dump["size"], 32 << 20)
        self.assertTrue(sessions.act(self.rt, self.ws, "stop")["stopped"])
        with self.assertRaises(ViwoError) as gone:
            sessions.act(self.rt, self.ws, "status")
        self.assertEqual(gone.exception.code, "not_found")


if __name__ == "__main__":
    unittest.main()
