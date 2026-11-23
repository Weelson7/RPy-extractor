"""Tier 3, LibVMI (doc 11.8): attach to a running Xen or KVMi domain, guest physical memory
through the LibVMI worker (a fake one here, speaking the same JSON lines over a file of guest
RAM), so a process view reads and writes through it; pause, snapshot and restore through a fake
virsh or xl; rejoin by domain; and every refusal said (no host, no LibVMI, no control, a domain
that is off or missing). The domain is the user's: closing never destroys it. No host runs here."""

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import runtime
from viwo.contracts.patcher import PatchTarget, Wall
from viwo.contracts.types import OutcomeKind
from viwo.core.context import core_context
from viwo.core.isolation import atomic_write, guest, vmi
from viwo.core.isolation.vmi import VmiPatcher, VmiSession, control_of

FAKE_CTRL = """#!{python}
import pathlib, sys
here = pathlib.Path(__file__).parent
with (here / "ctrl-calls.log").open("a", encoding="utf-8") as fh:
    fh.write(pathlib.Path(__file__).stem + " " + " ".join(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if args[:1] == ["domstate"]:
    print("shut off" if args[1] == "off" else "running")
if args[:1] == ["list"]:
    print("Name ID Mem VCPUs State Time(s)")
    print(args[1] + " 1 1024 1 -b---- 1.0")
"""

FAKE_LIBVMI = """import json, pathlib, sys
mem_file = pathlib.Path(__file__).with_name("phys.bin")
mem = bytearray(mem_file.read_bytes()) if mem_file.is_file() else bytearray(0x10000)
if sys.argv[1] == "missing":
    print(json.dumps({"ok": False, "error": "no domain missing"}), flush=True)
    sys.exit(1)
print(json.dumps({"ok": True, "mode": "xen", "argv": sys.argv[1:]}), flush=True)
for line in sys.stdin:
    req = json.loads(line)
    pa = req["pa"]
    if pa >= len(mem):
        print(json.dumps({"ok": False, "error": "out of guest RAM"}), flush=True)
    elif req["op"] == "read":
        print(json.dumps({"ok": True, "hex": mem[pa : pa + req["n"]].hex()}), flush=True)
    else:
        data = bytes.fromhex(req["hex"])
        mem[pa : pa + len(data)] = data
        mem_file.write_bytes(mem)
        print(json.dumps({"ok": True}), flush=True)
"""
DUMPER = "#!{python}\nimport sys\nopen(sys.argv[-1], 'wb').write(b'MEM')\n"


class VmiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        worker = self.root / "vmi" / "libvmi_io.py"
        worker.parent.mkdir(parents=True, exist_ok=True)
        worker.write_text(FAKE_LIBVMI)
        for patch in (
            mock.patch.object(vmi, "WORKER", worker),
            mock.patch.object(vmi, "_no_host", lambda: False),
            mock.patch.object(vmi, "has_libvmi", lambda: True),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def _rt(self, tools: dict[str, Path]):
        lines = "".join(f"{k} = {v}\n" for k, v in tools.items())
        (self.root / "rt").mkdir(parents=True, exist_ok=True)
        return runtime(self.root / "rt", "[plugins]\ngeneric = on\n[tools]\n" + lines)

    def _fake(self, name: str, body: str = FAKE_CTRL) -> Path:
        folder = self.root / "vmi"
        script = folder / f"{name}.py"
        script.write_text(body.format(python=sys.executable))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        if sys.platform == "win32":
            wrapper = folder / f"{name}.cmd"
            wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
            return wrapper
        return script

    def _calls(self) -> str:
        log = self.root / "vmi" / "ctrl-calls.log"
        return log.read_text(encoding="utf-8") if log.is_file() else ""

    def _start(self, rt, *args: str, snapshot: bool = False):
        target = PatchTarget(exe=self.root / "G.exe", workspace=self.root / "ws", args=args)
        ctx = core_context(rt, "isolate", self.root, self.root / "work")
        ctx.staging = self.root / "vmi-session"
        return rt.backends["libvmi"].start(target, ctx, snapshot=snapshot)

    def test_not_ready_off_a_bare_metal_linux_vmi_host(self) -> None:
        rt = self._rt({})
        with mock.patch.object(vmi, "_no_host", lambda: True):
            report = VmiPatcher().ready(rt.os)
            self.assertEqual(report.wall, Wall.NOT_READY)
            self.assertIn("Linux", report.detail)  # the requirement rides in the wall's detail
            self.assertEqual(self._start(rt).kind, OutcomeKind.UNAVAILABLE)
        with mock.patch.object(vmi, "has_libvmi", lambda: False):
            self.assertIn("libvmi.so", VmiPatcher().ready(rt.os).detail)
        self.assertIn("virsh", VmiPatcher().ready(rt.os).detail)  # no hypervisor control

    def test_control_prefers_virsh_then_falls_back_to_xl(self) -> None:
        both = self._rt({"virsh": self._fake("virsh"), "xl": self._fake("xl")})
        self.assertEqual(control_of(both.os)[1], "virsh")
        self.assertEqual(control_of(self._rt({"xl": self._fake("xl")}).os)[1], "xl")
        self.assertIsNone(control_of(self._rt({}).os))

    def test_kvm_session_attaches_walks_snapshots_and_leaves_the_domain_running(self) -> None:
        dumper = self._fake("vmi-dump-memory", DUMPER)
        rt = self._rt({"virsh": self._fake("virsh"), "vmi-dump-memory": dumper})
        session = self._start(rt, "win10", "/run/kvmi.sock", snapshot=True)
        self.assertIsInstance(session, VmiSession)
        self.assertEqual((session.domain, session.info["kvmi"]), ("win10", "/run/kvmi.sock"))
        view = guest.ProcessView(session, {"pid": 4, "dtb": 0, "mode": "phys"})
        self.assertFalse(atomic_write(view, 0x1FFE, b"ABCD").blocked, view.wall().detail)
        self.assertEqual(view.read_mem(0x1FFE, 4), b"ABCD")  # across a page edge
        self.assertEqual(view.write_mem(0x20000, b"X").wall, Wall.NOT_READY)  # LibVMI refused
        self.assertEqual(session.write_mem(0x1000, b"X").detail, vmi.NO_VA)  # locate first
        self.assertTrue(session.rollback("base").ok)
        self.assertTrue(session.dump(self.root / "core.raw").ok)
        self.assertEqual((self.root / "core.raw").read_bytes(), b"MEM")
        log = self._calls()
        for line in ("snapshot-create-as win10 base", "suspend win10", "resume win10"):
            self.assertIn(line, log)
        self.assertIn("snapshot-revert win10 base", log)
        session.close()
        self.assertNotIn("destroy", self._calls())  # the user's domain keeps running
        ctx = core_context(rt, "isolate", self.root, self.root / "w2")
        self.assertIsInstance(rt.backends["libvmi"].reattach(session.record(), ctx), VmiSession)

    def test_xen_saves_and_restores_and_refusals_are_said(self) -> None:
        rt = self._rt({"xl": self._fake("xl")})
        session = self._start(rt, "hvm1")
        self.assertTrue(session.running())
        self.assertTrue(session.snapshot("s1").ok)
        self.assertIn("save -c hvm1", self._calls())
        self.assertFalse(session.rollback("never").ok)  # no saved state: said
        (self.root / "vmi-session" / "s1.xl").write_bytes(b"x")
        self.assertTrue(session.rollback("s1").ok)
        self.assertIn("destroy hvm1", self._calls())
        self.assertIn("restore", self._calls())
        self.assertEqual(session.dump(self.root / "c").kind, OutcomeKind.UNAVAILABLE)
        missing = self._start(rt, "missing")
        self.assertEqual(missing.kind, OutcomeKind.UNAVAILABLE)
        self.assertIn("no domain missing", missing.error)
        off = self._start(self._rt({"virsh": self._fake("virsh")}), "off")
        self.assertIn("not running", off.error)


if __name__ == "__main__":
    unittest.main()
