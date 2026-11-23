"""Programs inside a guest (doc 11.8): the x86 page walk over guest physical memory (x64 with 1 GB
and 2 MB pages, PAE, legacy 32-bit, paging off), a process view that reads and writes through it
(split at page edges, all or nothing, a page not in RAM said as a wall), Volatility's rows grouped
and a process picked by pid or name, `locate` and the per-program dump driven through a fake
Volatility worker, and the live bridge taking each module's base from the located process and
undoing in the address space each edit was written in. Property: one walk, any OS, any language."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from tests.helpers import runtime
from viwo.contracts.errors import ViwoError
from viwo.contracts.patcher import MemoryFault, PatchSession, WallReport
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.core.isolation import guest, live, paging

P = 0x3  # present | writable


class Phys:
    """Guest physical memory as a sparse page map."""

    def __init__(self) -> None:
        self.pages: dict[int, bytearray] = {}

    def _page(self, pa: int) -> bytearray:
        return self.pages.setdefault(pa & ~0xFFF, bytearray(0x1000))

    def read(self, pa: int, n: int) -> bytes:
        out = bytearray()
        while n:
            take = min(n, 0x1000 - (pa & 0xFFF))
            out += self._page(pa)[pa & 0xFFF : (pa & 0xFFF) + take]
            pa, n = pa + take, n - take
        return bytes(out)

    def write(self, pa: int, data: bytes) -> None:
        for i, b in enumerate(data):
            self._page(pa + i)[(pa + i) & 0xFFF] = b

    def q(self, pa: int, value: int, size: int = 8) -> None:
        self.write(pa, value.to_bytes(size, "little"))


def x64_space() -> Phys:
    """PML4 0x1000. VA 0x40001000 -> PA 0x9000 (4 KB); VA 0x40200000 -> 2 MB page at 0x600000;
    VA 0x80000000 -> 1 GB page at 0x40000000; VA 0x40002000 not present."""
    m = Phys()
    m.q(0x1000, 0x2000 | P)  # PML4[0]
    m.q(0x2000 + 1 * 8, 0x5000 | P)  # PDPT[1]: VA 0x40000000
    m.q(0x2000 + 2 * 8, 0x40000000 | P | paging.LARGE)  # PDPT[2]: a 1 GB page
    m.q(0x5000, 0x4000 | P)  # PD[0] -> PT
    m.q(0x5000 + 1 * 8, 0x600000 | P | paging.LARGE | 0x1000)  # PD[1]: 2 MB page (PAT bit set)
    m.q(0x4000 + 1 * 8, 0x9000 | P | (1 << 63))  # PT[1], NX set
    m.q(0x4000 + 2 * 8, 0x7000)  # PT[2]: not present (paged out)
    return m


class PagingTests(unittest.TestCase):
    def test_x64_small_large_and_huge_pages(self) -> None:
        m = x64_space()
        self.assertEqual(paging.translate(m.read, 0x1000, 0x40001234), (0x9234, 0x1000 - 0x234))
        self.assertEqual(paging.translate(m.read, 0x1000, 0x40200010)[0], 0x600010)
        self.assertEqual(paging.translate(m.read, 0x1000, 0x80000010)[0], 0x40000010)
        self.assertEqual(paging.translate(m.read, 0x1ABC, 0x40001000)[0], 0x9000)  # PCID bits
        with self.assertRaises(paging.NotResident):
            paging.translate(m.read, 0x1000, 0x40002000)
        with self.assertRaises(MemoryFault):  # NotResident is a MemoryFault
            paging.translate(m.read, 0x1000, 0x7FFF00000000)

    def test_spans_split_at_page_edges_and_translate_first(self) -> None:
        m = x64_space()
        m.q(0x4000, 0xB000 | P)  # PT[0]: VA 0x40000000 -> 0xB000
        self.assertEqual(paging.spans(m.read, 0x1000, 0x40000FFE, 4), [(0xBFFE, 2), (0x9000, 2)])
        with self.assertRaises(paging.NotResident):  # the second page is out: nothing returned
            paging.spans(m.read, 0x1000, 0x40001FFE, 4)

    def test_pae_and_legacy_32_bit(self) -> None:
        m = Phys()
        m.q(0x3020 + 0 * 8, 0x4000 | 1)  # PAE: PDPT at 0x3020 (32-byte aligned)
        m.q(0x4000 + 2 * 8, 0x5000 | P)  # PD[2] (VA 0x00400000)
        m.q(0x5000 + 0x10 * 8, 0x8000 | P)  # PT[0x10]
        m.q(0x4000 + 3 * 8, 0xE00000 | P | paging.LARGE)  # PD[3]: 2 MB page
        self.assertEqual(paging.translate(m.read, 0x3020, 0x410123, "pae")[0], 0x8123)
        self.assertEqual(paging.translate(m.read, 0x3020, 0x600040, "pae")[0], 0xE00040)
        m.q(0x6000 + 1 * 4, 0x7000 | P, 4)  # x86: PD at 0x6000, PDE[1] -> PT 0x7000
        m.q(0x7000 + 2 * 4, 0xC000 | P, 4)
        m.q(0x6000 + 2 * 4, 0x800000 | P | paging.LARGE, 4)  # a 4 MB page
        self.assertEqual(paging.translate(m.read, 0x6000, 0x402010, "x86")[0], 0xC010)
        self.assertEqual(paging.translate(m.read, 0x6000, 0x800020, "x86")[0], 0x800020)
        self.assertEqual(paging.translate(m.read, 0, 0x1234, "phys"), (0x1234, 0x1000 - 0x234))

    def test_mode_of_control_registers(self) -> None:
        self.assertEqual(paging.mode_of(0x11, 0, 0), "phys")
        self.assertEqual(paging.mode_of(0x80000011, 0x20, 0x500), "x64")
        self.assertEqual(paging.mode_of(0x80000011, 0x20, 0), "pae")
        self.assertEqual(paging.mode_of(0x80000011, 0, 0), "x86")


class PhysSession(PatchSession):
    """A session whose only memory access is physical (as VirtualBox's)."""

    def __init__(self, mem: Phys | None) -> None:
        self.mem, self.events = mem, []

    @contextmanager
    def _phys(self):
        self.events.append("phys")
        yield self.mem

    def physical(self):
        return self._phys() if self.mem is not None else None

    def suspend(self) -> None:
        self.events.append("suspend")

    def resume(self) -> None:
        self.events.append("resume")

    def read_mem(self, addr: int, size: int) -> bytes:
        return b""

    def write_mem(self, addr: int, data: bytes) -> WallReport:
        return WallReport()

    def snapshot(self, name: str) -> Outcome:
        return Outcome(OutcomeKind.OK)

    def rollback(self, name: str) -> Outcome:
        return Outcome(OutcomeKind.OK)

    def dump(self, out: Path) -> Outcome:
        return Outcome(OutcomeKind.OK)

    def wall(self) -> WallReport:
        return WallReport()


class ProcessViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mem = x64_space()
        self.mem.q(0x4000, 0xB000 | P)
        self.view = guest.ProcessView(PhysSession(self.mem), {"pid": 8, "dtb": 0x1000})

    def test_read_and_write_cross_a_page_edge(self) -> None:
        self.assertFalse(self.view.write_mem(0x40000FFE, b"ABCD").blocked)
        self.assertEqual(self.mem.read(0xBFFE, 2) + self.mem.read(0x9000, 2), b"ABCD")
        self.assertEqual(self.view.read_mem(0x40000FFE, 4), b"ABCD")
        self.assertEqual(self.view.tag(), {"pid": 8, "dtb": 0x1000, "mode": "x64"})

    def test_a_page_not_in_ram_is_a_wall_and_nothing_is_written(self) -> None:
        wall = self.view.write_mem(0x40001FFE, b"WXYZ")
        self.assertEqual(wall.wall.value, "not_ready")
        self.assertIn("not resident", wall.detail)
        self.assertEqual(self.mem.read(0x9FFE, 2), b"\0\0")  # all or nothing
        self.assertEqual(self.view.read_mem(0x40002000, 1), b"")
        self.assertTrue(self.view.wall().blocked)

    def test_a_tier_without_physical_memory_says_so(self) -> None:
        view = guest.ProcessView(PhysSession(None), {"pid": 8, "dtb": 0x1000})
        self.assertIn("physical memory", view.write_mem(0x40001000, b"A").detail)

    def test_everything_else_is_the_sessions(self) -> None:
        inner = self.view.inner
        self.view.suspend()
        self.view.resume()
        self.assertEqual(inner.events[-2:], ["suspend", "resume"])
        self.assertTrue(self.view.snapshot("a").ok and self.view.dump(Path("x")).ok)
        self.assertTrue(self.view.rollback("a").ok and self.view.alive())


ROWS = [
    {"OS": "windows", "PID": 4, "Process": "System", "DTB": 0x1AA000, "Mode": "x64",
     "Module": "", "Base": 0, "Size": 0, "Path": ""},
    {"OS": "windows", "PID": 812, "Process": "VeryLongGameNa", "DTB": 0x2000, "Mode": "x64",
     "Module": "VeryLongGameName.exe", "Base": 0x140000000, "Size": 0x5000, "Path": "C:/g/V.exe"},
    {"OS": "windows", "PID": 812, "Process": "VeryLongGameNa", "DTB": 0x2000, "Mode": "x64",
     "Module": "GameAssembly.dll", "Base": 0x7FF800000000, "Size": 0x9000, "Path": "C:/g/G.dll"},
    {"OS": "windows", "PID": 900, "Process": "app.exe", "DTB": 0x3000, "Mode": "x64",
     "Module": "app.exe", "Base": 0x400000, "Size": 0x1000, "Path": "C:/a/app.exe"},
    {"OS": "windows", "PID": 901, "Process": "app.exe", "DTB": 0x4000, "Mode": "x64",
     "Module": "app.exe", "Base": 0x400000, "Size": 0x1000, "Path": "C:/a/app.exe"},
]  # fmt: skip


class PickTests(unittest.TestCase):
    def test_rows_group_into_processes(self) -> None:
        procs = guest.processes(ROWS)
        self.assertEqual([p["pid"] for p in procs], [4, 812, 900, 901])
        self.assertEqual(procs[0]["modules"], [])
        self.assertEqual(len(procs[1]["modules"]), 2)

    def test_pick_by_pid_full_name_or_truncated_name(self) -> None:
        procs = guest.processes(ROWS)
        self.assertEqual(guest.pick(procs, "812")["pid"], 812)
        self.assertEqual(guest.pick(procs, "verylonggamename.exe")["pid"], 812)
        with self.assertRaises(ViwoError) as two:
            guest.pick(procs, "app.exe")
        self.assertEqual(two.exception.code, "invalid_request")
        self.assertIn("900, 901", two.exception.message)
        with self.assertRaises(ViwoError) as none:
            guest.pick(procs, "nothing.exe")
        self.assertEqual(none.exception.code, "not_found")
        self.assertIn("VeryLongGameName.exe", none.exception.hint or "")


FAKE_VOLATILITY = """import json, pathlib, sys
args = sys.argv[1:]
pathlib.Path(sys.argv[0]).with_name("vol-args.json").write_text(json.dumps(args))
if "--dump" in args:
    out = pathlib.Path(args[args.index("-o") + 1])
    (out / "pid.812.0x140000000.dmp").write_bytes(b"MZ")
    print("[]")
else:
    print(json.dumps(ROWS))
"""


class LocateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        (self.root / "rt").mkdir()
        self.rt = runtime(self.root / "rt", "[plugins]\ngeneric = on\n")
        self.where = self.root / "ws" / ".runtime" / "isolation"
        script = self.root / "vol.py"
        script.write_text(f"ROWS = {ROWS!r}\n" + FAKE_VOLATILITY)
        self.argv = (sys.executable, str(script))
        self.session = PhysSession(Phys())
        self.lines: list[str] = []
        patch = mock.patch.object(guest, "_worker", lambda rt, log: self.argv)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self._tmp.cleanup)

    def _log(self, message: str, level: str = "info") -> None:
        self.lines.append(message)

    def test_locate_lists_then_keeps_one_and_removes_the_ram_image(self) -> None:
        self.session.dump = lambda out: (out.write_bytes(b"ELF"), Outcome(OutcomeKind.OK))[1]
        listed = guest.locate(self.rt, self.session, self.where, "", self._log)
        programs = [p["program"] for p in listed["processes"]]
        self.assertEqual(programs[:2], ["System", "VeryLongGameName.exe"])
        found = guest.locate(self.rt, self.session, self.where, "812", self._log)
        self.assertEqual(found["located"]["base"], hex(0x140000000))
        self.assertFalse((self.where / "guest-ram.elf").exists())  # the RAM image is gone
        self.assertEqual(guest.bases(self.where)["gameassembly.dll"], 0x7FF800000000)
        self.assertIsInstance(guest.view(self.session, self.where), guest.ProcessView)
        args = json.loads((self.root / "vol-args.json").read_text())
        self.assertEqual(args[:3], ["-q", "-r", "json"])
        self.assertIn("viwo_guest.Guest", args)
        self.assertTrue(any("Located VeryLongGameName.exe" in line for line in self.lines))
        dumped = guest.program(self.rt, self.session, self.where, self.where / "d", self._log)
        self.assertEqual(dumped["files"], ["pid.812.0x140000000.dmp"])
        args = json.loads((self.root / "vol-args.json").read_text())
        self.assertEqual(args[args.index("--pid") + 1], "812")
        self.assertIn("windows.dlllist", args)

    def test_a_failed_dump_or_volatility_is_said(self) -> None:
        self.session.dump = lambda out: Outcome(OutcomeKind.FAILED, error="no")
        with self.assertRaises(ViwoError) as dump:
            guest.locate(self.rt, self.session, self.where, "", self._log)
        self.assertIn("RAM dump failed", dump.exception.message)
        self.session.dump = lambda out: (out.write_bytes(b"ELF"), Outcome(OutcomeKind.OK))[1]
        self.argv = (sys.executable, "-c", "import sys; sys.stderr.write('no kernel'); sys.exit(1)")
        with self.assertRaises(ViwoError) as vol:
            guest.locate(self.rt, self.session, self.where, "", self._log)
        self.assertIn("no kernel", vol.exception.message)
        with self.assertRaises(ViwoError):  # no tier without physical memory
            guest.locate(self.rt, PhysSession(None), self.where, "", self._log)
        with self.assertRaises(ViwoError):  # a program dump needs a located process
            guest.program(self.rt, self.session, self.root / "none", self.root / "d", self._log)


class LiveBasesTests(unittest.TestCase):
    def test_each_module_its_base_and_undo_in_its_own_space(self) -> None:
        mem = x64_space()
        mem.q(0x4000, 0xB000 | P)
        session = PhysSession(mem)
        view = guest.ProcessView(session, {"pid": 8, "dtb": 0x1000, "mode": "x64"})
        self.assertEqual(live._base({"g.exe": 5}, {"file": "bin/G.exe"}), 5)
        self.assertIsNone(live._base({"g.exe": 5}, {"file": "other.dll"}))
        self.assertEqual(live._base(7, {"file": "x"}), 7)
        log: list[dict] = []
        with mock.patch.object(live, "located_va", lambda data, off, base: base + off):
            wall = live.write_located(view, b"", 0x10, b"NEW", 0x40000000, log)
        self.assertFalse(wall.blocked, wall.detail)
        self.assertEqual(mem.read(0xB010, 3), b"NEW")
        self.assertEqual((log[0]["dtb"], log[0]["pid"]), (0x1000, 8))
        bare = guest.bound(session, log[0])
        self.assertIsInstance(bare, guest.ProcessView)  # undo walks the same page tables
        self.assertIs(guest.bound(session, {"addr": 1}), session)
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "journal.jsonl"
            journal.write_text(json.dumps(log[0]) + "\n")
            self.assertEqual(live.undo(session, journal), {"restored": 1, "edits": 1})
        self.assertEqual(mem.read(0xB010, 3), b"\0\0\0")


class WorkerScriptTests(unittest.TestCase):
    def test_the_worker_refuses_a_bad_command_line(self) -> None:
        sys.path.insert(0, str(Path(guest.__file__).parents[2] / "data" / "workers"))
        try:
            import memory
        finally:
            sys.path.pop(0)
        self.assertEqual(memory.main(["-f", "x"]), 2)


if __name__ == "__main__":
    unittest.main()
