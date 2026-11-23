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
from tests.test_isolation_tiers import FakeGdbStub
from viwo.contracts.analysis import AnalysisTarget
from viwo.contracts.patcher import PatchSession, PatchTarget, Wall, WallReport
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.core.capture.attach import attach_for
from viwo.core.context import core_context
from viwo.core.isolation import atomic_write, tiers
from viwo.core.isolation.scylla import ScyllaDump
from viwo.core.isolation.vbox_session import VBoxSession

FAKE_VBOX = """#!{python}
import sys, pathlib
args = sys.argv[1:]
here = pathlib.Path(__file__).parent
state = here / "vm-state"
with (here / "vbox-calls.log").open("a", encoding="utf-8") as fh:
    fh.write(" ".join(args) + "\\n")
if args[:1] == ["snapshot"] and "restore" in args and "missing" in args:
    sys.stderr.write("Could not find a snapshot named 'missing'\\n")
    sys.exit(1)
moves = {{"startvm": "running", "pause": "paused", "resume": "running", "poweroff": "poweroff"}}
for word, to in moves.items():
    if word in args:
        state.write_text(to)
if args[:1] == ["showvminfo"]:
    print('VMState="' + (state.read_text() if state.is_file() else "poweroff") + '"')
if args[:1] == ["createmedium"] or args[:1] == ["convertfromraw"]:
    out = args[args.index("--filename") + 1] if "--filename" in args else args[2]
    pathlib.Path(out).write_bytes(b"VDI")
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


class FakeDbgcStub(FakeGdbStub):
    """VirtualBox's gdb stub as found on 7.2.22: `M` refused, the console (qRcmd, whose last
    character it drops) reads and writes physical memory (`db`/`eb`/`eq` on %% addresses) and
    the control registers. 64 KB of guest RAM; paging off until the test sets the registers."""

    def __init__(self) -> None:
        super().__init__()
        self.mem = bytearray(0x10000)
        self.regs = {"cr0": 0x11, "cr3": 0, "cr4": 0, "efer": 0}

    def _handle(self, cmd: str):
        if cmd.startswith(("M", "X")):
            return "E81"
        if cmd.startswith("qRcmd,"):
            text = self._console(bytes.fromhex(cmd[6:]).decode()[:-1].split())
            return ([f"O{text.encode().hex()}"] if text else []) + ["OK"]
        return super()._handle(cmd)

    def _console(self, words: list[str]) -> str:
        if words[0] == "db":
            pa, n = int(words[1][2:], 16), int(words[2][1:], 16)
            lines = []
            for at in range(pa, pa + n, 16):
                chunk = self.mem[at : min(at + 16, pa + n)]
                cells = " ".join(f"{b:02x}" for b in chunk)
                cells = cells[:23] + "-" + cells[24:] if len(chunk) > 8 else cells
                text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                lines.append(f"%%{at:016x}: {cells:<48}  {text}")
            return "\n".join(lines) + "\n"
        if words[0] in ("eb", "eq"):
            pa, size = int(words[1][2:], 16), 1 if words[0] == "eb" else 8
            self.mem[pa : pa + size] = int(words[2], 16).to_bytes(size, "little")
            return ""
        if words[0] == "r":
            return f"{words[1]}={self.regs[words[1]]:#018x}\n"
        return f"Syntax error: Unknown command '{words[0]}'!\n"


class VirtualBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        self.vbdir = self.root / "vbox"
        tool = _tool(self.vbdir, "VBoxManage", FAKE_VBOX)
        none = self.root / "none.exe"
        body = f"[plugins]\ngeneric = on\n[tools]\nvirtualbox = {tool}\nqemu = {none}\n"
        (self.root / "rt").mkdir(parents=True, exist_ok=True)
        self.rt = runtime(self.root / "rt", body)
        self.image = self.root / "guest.img"
        self.image.write_bytes(b"\x55\xaa" * 256)
        self.addCleanup(self._tmp.cleanup)

    def _start(self, snapshot: bool = True, **target):
        ctx = core_context(self.rt, "isolate", self.root, self.root / "work")
        ctx.staging = self.root / "vms"
        target = PatchTarget(self.root / "G.exe", self.root / "ws", image=self.image, **target)
        return self.rt.backends["vbox"].start(target, ctx, snapshot=snapshot)

    def _stub(self, session) -> FakeDbgcStub:
        stub = FakeDbgcStub()
        session.info["gdb"] = stub.port
        return stub

    def test_start_boots_a_copy_closed_with_the_gdb_stub_on_loopback(self) -> None:
        binding = self.rt.bindings["isolation.vbox"]
        self.assertEqual((binding.bound, binding.main), (True, "vbox"))
        session = self._start(snapshot=True)
        self.assertIsInstance(session, VBoxSession)
        log, vm = _calls(self.vbdir), session.vm
        self.assertTrue(vm.startswith("viwo-G-"))  # one VM per workspace
        self.assertIn(f"convertfromraw {self.image}", log)  # a copy: the image is never attached
        self.assertNotIn(f"--medium {self.image}", log)
        self.assertEqual(self.image.read_bytes(), b"\x55\xaa" * 256)
        self.assertIn("--nic1 none", log)  # closed unless asked
        self.assertIn("--firmware bios", log)
        self.assertIn("--guest-debug-provider gdb", log)
        self.assertIn("--guest-debug-address 127.0.0.1", log)
        self.assertIn(f"startvm {vm} --type gui", log)
        self.assertIn(f"snapshot {vm} take base --live", log)  # live: no power cycle
        ctx = core_context(self.rt, "isolate", self.root, self.root / "w2")
        again = self.rt.backends["vbox"].reattach(session.record(), ctx)
        self.assertIsInstance(again, VBoxSession)
        self.assertTrue(again.running())

    def test_efi_tpm_network_share_and_an_installer_iso(self) -> None:
        share = self.root / "game"
        share.mkdir()
        self.image = self.root / "setup.iso"
        self.image.write_bytes(b"CD001")
        self._start(False, efi=True, network=True, share=share, headless=True)
        log = _calls(self.vbdir)
        self.assertIn("--firmware efi", log)
        self.assertIn("--tpm-type 2.0", log)  # a virtual TPM 2.0 with UEFI
        self.assertIn("--nic1 nat", log)
        self.assertIn("createmedium disk", log)  # the installer gets a new empty disk
        self.assertIn(f"--type dvddrive --medium {self.image}", log)
        self.assertIn(f"--hostpath {share} --readonly", log)
        self.assertIn("--type headless", log)

    def test_snapshots_rollback_dump_and_close_keep_the_vm_folder(self) -> None:
        session = self._start(snapshot=False)
        self.assertTrue(session.dump(self.root / "core.elf").ok)
        self.assertTrue(session.rollback("good").ok)
        self.assertFalse(session.rollback("missing").ok)  # VBoxManage non-zero -> FAILED
        session.close()
        log, vm = _calls(self.vbdir), session.vm
        self.assertIn(f"debugvm {vm} dumpvmcore --filename=", log)
        self.assertLess(log.index(f"controlvm {vm} poweroff"), log.index(f"snapshot {vm} restore"))
        self.assertIn(f"unregistervm {vm}\n", log)  # unregistered, not deleted
        folder = self.root / "vms" / vm
        (folder / f"{vm}.vbox").write_text("<VirtualBox/>")
        self._start(snapshot=False)
        self.assertIn("registervm", _calls(self.vbdir))  # the kept VM comes back
        self._start(snapshot=False, fresh=True)
        self.assertFalse((folder / f"{vm}.vbox").exists())  # fresh: discarded

    def test_memory_goes_through_the_console_with_paging_off(self) -> None:
        session = self._start(snapshot=False)
        stub = self._stub(session)
        stub.mem[0x7C10:0x7C14] = b"MARK"
        self.assertEqual(session.read_mem(0x7C10, 4), b"MARK")
        stub.mem[0x7D00:0x7D10] = b"Error: not ours."  # guest text in the dump is not a fault
        self.assertEqual(session.read_mem(0x7D00, 16), b"Error: not ours.")
        wall = atomic_write(session, 0x7C08, b"0123456789AB")  # an eq and four ebs
        self.assertFalse(wall.blocked, wall.detail)
        self.assertEqual(bytes(stub.mem[0x7C08:0x7C14]), b"0123456789AB")
        log = _calls(self.vbdir)
        self.assertIn(f"controlvm {session.vm} pause", log)  # suspended over VBoxManage
        self.assertIn(f"controlvm {session.vm} resume", log)

    def test_memory_through_vcpu_paging_and_a_wall_when_unmapped(self) -> None:
        session = self._start(snapshot=False)
        stub = self._stub(session)
        stub.regs.update(cr0=0x80000011, cr3=0x1000, cr4=0x20, efer=0x500)
        for at, entry in ((0x1000, 0x2003), (0x2008, 0x5003), (0x5000, 0x4003), (0x4008, 0x9003)):
            stub.mem[at : at + 8] = entry.to_bytes(8, "little")
        self.assertFalse(session.write_mem(0x40001000, b"PAGED").blocked)
        self.assertEqual(bytes(stub.mem[0x9000:0x9005]), b"PAGED")
        self.assertEqual(session.read_mem(0x40001000, 5), b"PAGED")
        self.assertEqual(session.write_mem(0x40003000, b"X").wall, Wall.NOT_READY)
        session.info["gdb"] = 1  # nothing listens: said, never a crash
        self.assertEqual(session.read_mem(0x40001000, 1), b"")
        self.assertIn("gdb stub", session.wall().detail)

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
