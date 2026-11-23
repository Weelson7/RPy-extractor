"""Tier 2 (QEMU, doc 11.8): the GDB remote serial protocol client and the QMP client exercised in
process against tiny loopback stubs the test stands up (the real wire protocol, no VM), the QEMU
session's out-of-guest memory read/write and suspend/resume over the gdbstub and snapshot/dump over
QMP, WHPX-else-TCG detection, and the backend's refusals. No real qemu runs."""

from __future__ import annotations

import json
import socket
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from tests.helpers import runtime
from viwo.contracts.patcher import PatchTarget
from viwo.contracts.types import OutcomeKind
from viwo.core.context import core_context
from viwo.core.isolation.gdb import GdbClient, _decode
from viwo.core.isolation.qemu import HARDWARE, QEMU, accel_of, accelerators, guest_args
from viwo.core.isolation.qemu_session import QemuSession


def _ck(body: str) -> bytes:
    return f"{sum(body.encode('latin-1')) & 0xFF:02x}".encode()


class FakeGdbStub:
    """A minimal gdbstub over a loopback socket: 256 bytes of guest memory, m/M, ?, c and the raw
    Ctrl-C interrupt. It speaks the real packet framing so the client is exercised end to end."""

    def __init__(self) -> None:
        self.mem = bytearray(256)
        self.interrupts = 0
        self._srv = socket.socket()
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _send(self, conn, body: str) -> None:
        conn.sendall(b"$" + body.encode("latin-1") + b"#" + _ck(body))

    def _serve(self) -> None:
        while True:  # a session connects once per memory access
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            try:
                self._loop(conn)
            except OSError:  # the client closed mid-reply
                pass
            finally:
                conn.close()

    def _loop(self, conn) -> None:
        while True:
            first = conn.recv(1)
            if not first:
                return
            if first == b"\x03":
                self.interrupts += 1
                self._send(conn, "T05thread:01;")
                continue
            if first != b"$":
                continue
            body = bytearray()
            while (ch := conn.recv(1)) not in (b"#", b""):
                body.extend(ch)
            conn.recv(2)
            conn.sendall(b"+")
            reply = self._handle(body.decode("latin-1"))
            if reply is not None:
                self._send(conn, reply)

    def _handle(self, cmd: str):
        if cmd in ("c", "D"):
            return None if cmd == "c" else "OK"
        if cmd == "?":
            return "S05"
        if cmd.startswith("m"):
            addr, size = (int(x, 16) for x in cmd[1:].split(","))
            return self.mem[addr : addr + size].hex()
        if cmd.startswith("M"):
            head, data = cmd[1:].split(":")
            addr = int(head.split(",")[0], 16)
            self.mem[addr : addr + len(bytes.fromhex(data))] = bytes.fromhex(data)
            return "OK"
        return ""


class FakeQmp:
    """A minimal QMP server: greeting, qmp_capabilities, stop/cont/query-status, human-monitor-
    command (an 'Error:' for a name holding 'bad', WHPX's refusal for one holding 'whpx') and
    dump-guest-memory writing the requested file."""

    def __init__(self) -> None:
        self._srv = socket.socket()
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        self.running, self.calls = True, []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            try:
                self._loop(conn)
            except OSError:
                pass
            finally:
                conn.close()

    def _loop(self, conn) -> None:
        conn.sendall(json.dumps({"QMP": {"version": {}}}).encode() + b"\n")
        buf = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                conn.sendall(json.dumps(self._reply(json.loads(line))).encode() + b"\n")

    def _reply(self, msg: dict) -> dict:
        args = msg.get("arguments", {})
        self.calls.append(msg["execute"])
        if msg["execute"] in ("stop", "cont"):
            self.running = msg["execute"] == "cont"
        if msg["execute"] == "query-status":
            return {"return": {"running": self.running}}
        if msg["execute"] == "human-monitor-command":
            line = args["command-line"]
            blocked = "Error: State blocked due to missing dirty memory tracking support"
            return {"return": blocked if "whpx" in line else "Error: no" if "bad" in line else ""}
        if msg["execute"] == "dump-guest-memory":
            Path(args["protocol"].removeprefix("file:")).write_bytes(b"CORE")
        return {"return": {}}


class GdbClientTests(unittest.TestCase):
    def test_decode_handles_escape_and_run_length(self) -> None:
        self.assertEqual(_decode("}]"), "}")  # 0x5d ^ 0x20 = 0x7d
        self.assertEqual(_decode("0*%"), "0" * (ord("%") - 29 + 1))  # RLE repeats the last char

    def test_read_write_roundtrip_over_the_wire(self) -> None:
        stub = FakeGdbStub()
        client = GdbClient.connect("127.0.0.1", stub.port)
        client.write_mem(0x10, b"\x90\xeb\x05")
        self.assertEqual(client.read_mem(0x10, 3), b"\x90\xeb\x05")
        self.assertEqual(stub.mem[0x10:0x13], b"\x90\xeb\x05")
        client.close()

    def test_interrupt_and_continue(self) -> None:
        stub = FakeGdbStub()
        client = GdbClient.connect("127.0.0.1", stub.port)
        client.cont()  # the stub keeps running, no reply
        self.assertTrue(client.interrupt().startswith("T05"))  # the stop reply on Ctrl-C
        self.assertEqual(stub.interrupts, 1)
        client.close()


class QemuSessionTests(unittest.TestCase):
    def _session(self) -> QemuSession:
        self.gdb_stub, self.qmp_stub = FakeGdbStub(), FakeQmp()
        info = {"qmp": self.qmp_stub.port, "gdb": self.gdb_stub.port, "accel": "tcg", "pid": 0}
        return QemuSession(info)

    def test_atomic_write_suspends_writes_verifies_resumes_over_gdbstub(self) -> None:
        from viwo.core.isolation import atomic_write

        session = self._session()
        wall = atomic_write(session, 0x20, b"\xcc\xcc")
        self.assertFalse(wall.blocked)  # it landed and read back equal
        self.assertEqual(self.gdb_stub.mem[0x20:0x22], b"\xcc\xcc")
        calls = [c for c in self.qmp_stub.calls if c in ("stop", "cont")]
        self.assertEqual((calls[0], calls[-1]), ("stop", "cont"))  # stopped over QMP, then run
        self.assertNotIn("cont", calls[:-1])  # never running between the write and the readback
        self.assertTrue(self.qmp_stub.running)
        session.close()

    def test_a_read_leaves_a_paused_guest_paused(self) -> None:
        session = self._session()
        session.suspend()
        self.assertEqual(session.read_mem(0x20, 2), b"\x00\x00")
        self.assertFalse(session.running())
        self.assertEqual(session.record()["gdb"], self.gdb_stub.port)
        session.release()
        self.assertTrue(session.answers())  # a released handle reconnects
        session.close()

    def test_whpx_snapshot_refusal_and_bad_names_are_said(self) -> None:
        session = self._session()
        blocked = session.snapshot("whpx")
        self.assertEqual(blocked.kind, OutcomeKind.UNAVAILABLE)
        self.assertIn("WHPX", blocked.error)
        self.assertFalse(session.snapshot("a; quit").ok)  # never reaches the monitor
        self.assertNotIn("quit", self.qmp_stub.calls)
        session.close()

    def test_snapshot_dump_over_qmp(self) -> None:
        session = self._session()
        self.assertTrue(session.snapshot("base").ok)  # savevm: empty output = success
        self.assertFalse(session.snapshot("bad").ok)  # the stub returns an Error for 'bad'
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "core.elf"
            self.assertTrue(session.dump(out).ok)
            self.assertEqual(out.read_bytes(), b"CORE")
        session.close()


class QemuBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _tool(self, body: str) -> Path:
        folder = self.root / "qemu"
        folder.mkdir(parents=True, exist_ok=True)
        script = folder / "qemu-system-x86_64.py"
        script.write_text(body.format(python=sys.executable))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        if sys.platform == "win32":
            wrapper = folder / "qemu-system-x86_64.cmd"
            wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
            return wrapper
        return script

    def _rt(self, tool: Path | None):
        body = "[plugins]\ngeneric = on\n"
        if tool is not None:
            body += f"[tools]\nqemu = {tool}\n"
        (self.root / "rt").mkdir(parents=True, exist_ok=True)
        return runtime(self.root / "rt", body)

    def test_hardware_first_then_tcg_and_tcg_alone_for_a_whpx_snapshot(self) -> None:
        rt = self._rt(self._tool("#!{python}\nprint('Accelerators: tcg whpx kvm')\n"))
        prefix = rt.os.tools.locate(QEMU).argv_prefix
        self.assertEqual(accelerators(rt.os, prefix, "", False)[0], [HARDWARE, "tcg"])
        order, why = accelerators(rt.os, prefix, "", True)
        if HARDWARE == "whpx":
            self.assertEqual(order, ["tcg"])
            self.assertIn("snapshot", why)  # said, not silent
        self.assertEqual(accelerators(rt.os, prefix, "tcg", False)[0], ["tcg"])  # asked for

    def test_accel_of_names_the_hardware_accelerator_when_listed(self) -> None:
        rt = self._rt(self._tool("#!{python}\nprint('Accelerators: tcg whpx kvm')\n"))
        self.assertEqual(accel_of(rt.os, rt.os.tools.locate(QEMU).argv_prefix), HARDWARE)

    def test_accel_falls_back_to_tcg(self) -> None:
        rt = self._rt(self._tool("#!{python}\nprint('Accelerators: tcg')\n"))
        self.assertEqual(accel_of(rt.os, rt.os.tools.locate(QEMU).argv_prefix), "tcg")
        order, why = accelerators(rt.os, rt.os.tools.locate(QEMU).argv_prefix, "", False)
        self.assertEqual(order, ["tcg"])
        self.assertIn("TCG", why)

    def test_guest_is_closed_by_default_and_control_is_loopback_only(self) -> None:
        target = PatchTarget(exe=self.root / "G.exe", workspace=self.root / "ws")
        args = guest_args(target, "tcg", (1111, 2222))
        self.assertEqual(args[args.index("-nic") + 1], "none")
        self.assertIn("tcp:127.0.0.1:1111,server=on,wait=off", args)
        self.assertIn("tcp:127.0.0.1:2222", args)
        opened = PatchTarget(exe=target.exe, workspace=target.workspace, network=True)
        self.assertNotIn("-nic", guest_args(opened, "tcg", (1, 2)))
        self.assertNotIn("-S", args)
        halted = PatchTarget(exe=target.exe, workspace=target.workspace, halted=True)
        self.assertIn("-S", guest_args(halted, "tcg", (1, 2)))

    def test_a_qemu_that_exits_at_once_is_reported_after_every_accelerator(self) -> None:
        rt = self._rt(self._tool("#!{python}\nprint('Accelerators: tcg')\n"))
        ctx = core_context(rt, "isolate", self.root, self.root / "work")
        ctx.staging = self.root / "vm"
        image = self.root / "disk.img"
        image.write_bytes(b"\0" * 512)
        target = PatchTarget(exe=self.root / "G.exe", workspace=self.root / "ws", image=image)
        failed = rt.backends["qemu"].start(target, ctx)
        self.assertEqual(failed.kind, OutcomeKind.FAILED)
        self.assertIn("exited", failed.error)

    def test_reattach_to_a_gone_session_says_it_has_exited(self) -> None:
        rt = self._rt(None)
        gone = rt.backends["qemu"].reattach({"qmp": 1, "gdb": 2, "pid": 0}, None)
        self.assertEqual(gone.kind, OutcomeKind.UNAVAILABLE)

    def test_start_refuses_without_qemu_or_image(self) -> None:
        tool = self._tool("#!{python}\nprint('Accelerators: tcg')\n")
        rt = self._rt(tool)
        ctx = core_context(rt, "isolate", self.root, self.root / "work")
        ctx.staging = self.root / "vm"
        target = PatchTarget(exe=self.root / "G.exe", workspace=self.root / "ws")  # no image
        no_image = rt.backends["qemu"].start(target, ctx)
        self.assertEqual(no_image.kind, OutcomeKind.UNAVAILABLE)
        self.assertIn("image", no_image.error)
        no_tool = self._rt(None).backends["qemu"].start(target, ctx)
        self.assertEqual(no_tool.kind, OutcomeKind.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
