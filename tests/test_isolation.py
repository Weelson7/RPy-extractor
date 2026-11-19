"""L3: the patcher / isolation arm (doc 11.8), Tier 1. Properties: the contract says WHICH wall
blocked an edit, never silently; the atomic live edit is suspend -> write -> verify -> resume;
VirtualBox is orchestrated through VBoxManage (virtual TPM 2.0, snapshots, pause/resume,
dumpvmcore) and unit-tested with a fake; QEMU (T2) and VMI (T3) are declared and announce their
requirement through wall(); Scylla's dump-to-patch is an attach-family tool. No real VM runs."""

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime
from viwo.contracts.analysis import AnalysisTarget
from viwo.contracts.patcher import PatchSession, PatchTarget, Wall, WallReport
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.core.capture.attach import attach_for
from viwo.core.context import core_context
from viwo.core.isolation import atomic_write, tiers
from viwo.core.isolation.scylla import ScyllaDump
from viwo.core.isolation.vbox import VBoxSession

FAKE_VBOX = """#!{python}
import sys, pathlib
args = sys.argv[1:]
log = pathlib.Path(__file__).with_name("vbox-calls.log")
with log.open("a", encoding="utf-8") as fh:
    fh.write(" ".join(args) + "\\n")
if args[:1] == ["snapshot"] and "restore" in args and "missing" in args:
    sys.stderr.write("Could not find a snapshot named 'missing'\\n")
    sys.exit(1)
print("0%...100%")
"""


def _tool(folder: Path, name: str, body: str) -> Path:
    """A Python stand-in plus a .cmd wrapper so it runs on Windows (doc gotchas)."""
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / f"{name}.py"
    script.write_text(body.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    if sys.platform == "win32":
        wrapper = folder / f"{name}.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
        return wrapper
    return script


def _calls(folder: Path) -> str:
    log = folder / "vbox-calls.log"
    return log.read_text(encoding="utf-8") if log.is_file() else ""


class FakeSession(PatchSession):
    """An in-memory session proving atomic_write's order without a tool. `revert` makes the write
    not hold on readback (as a self-check would), to exercise the integrity-check wall."""

    def __init__(self, revert: bool = False) -> None:
        self.mem = bytearray(16)
        self.events: list[str] = []
        self.revert = revert

    def suspend(self) -> None:
        self.events.append("suspend")

    def resume(self) -> None:
        self.events.append("resume")

    def read_mem(self, addr: int, size: int) -> bytes:
        return bytes(self.mem[addr : addr + size])

    def write_mem(self, addr: int, data: bytes) -> WallReport:
        self.events.append("write")
        if not self.revert:
            self.mem[addr : addr + len(data)] = data
        return WallReport()

    def snapshot(self, name: str) -> Outcome:
        return Outcome(OutcomeKind.OK)

    def rollback(self, name: str) -> Outcome:
        return Outcome(OutcomeKind.OK)

    def dump(self, out: Path) -> Outcome:
        return Outcome(OutcomeKind.OK)

    def wall(self) -> WallReport:
        return WallReport()


class VirtualBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.vbdir = self.root / "vbox"
        tool = _tool(self.vbdir, "VBoxManage", FAKE_VBOX)
        body = f"[plugins]\ngeneric = on\n[tools]\nvirtualbox = {tool}\n"
        (self.root / "rt").mkdir(parents=True, exist_ok=True)
        self.rt = runtime(self.root / "rt", body)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _start(self, snapshot: bool = True):
        ctx = core_context(self.rt, "isolate", self.root, self.root / "work")
        ctx.staging = self.root / "vms"
        target = PatchTarget(exe=self.root / "G.exe", workspace=self.root / "ws")
        return self.rt.backends["vbox"].start(target, ctx, snapshot=snapshot)

    def test_binding_and_vtpm_and_snapshot_on_start(self) -> None:
        binding = self.rt.bindings["isolation.vbox"]
        self.assertTrue(binding.bound)
        self.assertEqual(binding.main, "vbox")
        session = self._start(snapshot=True)
        self.assertIsInstance(session, VBoxSession)
        log = _calls(self.vbdir)
        self.assertIn("createvm viwo-G", log)
        self.assertIn("--tpm-type 2.0", log)  # a virtual TPM 2.0
        self.assertIn("--firmware efi", log)
        self.assertIn("startvm viwo-G --type headless", log)
        self.assertIn("snapshot viwo-G take base", log)  # base snapshot for retries

    def test_snapshot_dump_memwall_and_close(self) -> None:
        session = self._start(snapshot=False)
        self.assertTrue(session.dump(self.root / "core.elf").ok)
        self.assertTrue(session.rollback("good").ok)
        self.assertFalse(session.rollback("missing").ok)  # VBoxManage non-zero -> FAILED
        wall = session.write_mem(0x1000, b"\x90")  # host-side poke is the guest debugger's job
        self.assertEqual(wall.wall, Wall.NOT_READY)
        self.assertTrue(session.wall().blocked)
        session.close()
        log = _calls(self.vbdir)
        self.assertIn("debugvm viwo-G dumpvmcore --filename", log)
        self.assertIn("controlvm viwo-G poweroff", log)
        self.assertIn("unregistervm viwo-G --delete", log)

    def test_atomic_write_resumes_even_when_the_write_is_walled(self) -> None:
        session = self._start(snapshot=False)
        wall = atomic_write(session, 0x2000, b"\x90\x90")
        self.assertEqual(wall.wall, Wall.NOT_READY)  # the write wall is surfaced, not swallowed
        log = _calls(self.vbdir)
        self.assertIn("controlvm viwo-G pause", log)
        self.assertIn("controlvm viwo-G resume", log)  # resumed anyway (finally)

    def test_tiers_announce_readiness_and_requirement(self) -> None:
        rows = {row["slot"]: row for row in tiers(self.rt)}
        self.assertEqual(set(rows), {"isolation.vbox", "isolation.qemu", "isolation.vmi"})
        self.assertTrue(rows["isolation.vbox"]["ready"])  # VBoxManage located
        self.assertEqual(rows["isolation.vbox"]["tier"], 1)
        for slot in ("isolation.qemu", "isolation.vmi"):
            self.assertFalse(rows[slot]["ready"])
            self.assertTrue(rows[slot]["requirement"])  # it says what it needs
            self.assertEqual(rows[slot]["wall"], "not_ready")

    def test_declared_tiers_refuse_with_their_requirement(self) -> None:
        ctx = core_context(self.rt, "isolate", self.root, self.root / "work2")
        target = PatchTarget(exe=self.root / "G.exe", workspace=self.root / "ws")
        qemu = self.rt.backends["qemu"].start(target, ctx)
        self.assertEqual(qemu.kind, OutcomeKind.UNAVAILABLE)
        vmi = self.rt.backends["libvmi"].start(target, ctx)
        self.assertEqual(vmi.kind, OutcomeKind.UNAVAILABLE)
        self.assertIn("Linux", vmi.error)


class AtomicWriteTests(unittest.TestCase):
    def test_atomic_order_and_verify(self) -> None:
        session = FakeSession()
        wall = atomic_write(session, 2, b"\xaa\xbb")
        self.assertFalse(wall.blocked)
        self.assertEqual(bytes(session.mem[2:4]), b"\xaa\xbb")
        self.assertEqual(session.events, ["suspend", "write", "resume"])

    def test_integrity_check_when_the_write_does_not_hold(self) -> None:
        session = FakeSession(revert=True)
        wall = atomic_write(session, 2, b"\xaa")
        self.assertEqual(wall.wall, Wall.INTEGRITY_CHECK)
        self.assertEqual(session.events[-1], "resume")  # resumed after the failed verify


class ScyllaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        tool = _tool(self.root / "scy", "Scylla_x64", "#!{python}\nimport time\ntime.sleep(5)\n")
        body = f"[plugins]\ngeneric = on\n[tools]\nscylla = {tool}\n"
        (self.root / "rt").mkdir(parents=True, exist_ok=True)
        self.rt = runtime(self.root / "rt", body)
        self.scy = tool

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_scylla_is_a_bound_attach_tool(self) -> None:
        binding = self.rt.bindings["attach.dump"]
        self.assertTrue(binding.bound)
        self.assertEqual(binding.main, "scylla-gui")
        self.assertIn("scylla-gui", [t["id"] for t in attach_for(self.rt, "native_binary")])

    def test_prepare_guides_and_launches_into_the_workspace(self) -> None:
        logs: list[str] = []
        ctx = core_context(
            self.rt, "attach", self.root, self.root / "work", lambda e: logs.append(e.message)
        )
        ctx.staging = self.root / "ws" / ".runtime" / "scylla-gui" / "g-exe"
        target = AnalysisTarget("g-exe", "native_binary", (self.root / "G.exe",), "user")
        spec = ScyllaDump().prepare(target, ctx)
        self.assertIn(str(self.scy), spec.argv)  # the located tool (a .cmd wrapper on Windows)
        self.assertEqual(spec.cwd, ctx.staging)
        self.assertTrue(ctx.staging.is_dir())
        self.assertTrue(any("rebuilt PE" in line for line in logs))  # it is guided, never faked


if __name__ == "__main__":
    unittest.main()
