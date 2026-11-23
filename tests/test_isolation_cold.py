"""Cold patching inside the guest (doc 11.8, core.isolation.coldguest): the set's files are pulled
from the guest, kept as originals once, patched in a staged copy with the cold writer and pushed
back, all or nothing; restore pushes the originals back; unsafe names are refused; guest paths
are spelled the guest's way. The channels: QEMU's guest agent (a fake agent speaking its JSON
lines over loopback) and VirtualBox's guestcontrol (a fake VBoxManage), whose guest password
never shows in what is said. Properties over fakes; the real run needs a guest with its agent."""

from __future__ import annotations

import base64
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from tests.helpers import runtime
from viwo.contracts.errors import ViwoError
from viwo.contracts.patcher import PatchSession
from viwo.core.isolation import coldguest
from viwo.core.isolation.qga import Qga

GAME = b"MZ" + bytes(14) + b"\xaa\xbb" + bytes(16)
SET = {"patches": [{"file": "bin/Game.exe", "offset": "0x10", "original": "aa bb",
                    "patched": "cc dd"}]}  # fmt: skip


class Files(PatchSession):
    """A guest seen only through its files."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files, self.seen = files, []

    def get_file(self, path: str, creds: dict) -> bytes:
        self.seen.append(creds)
        if path not in self.files:
            raise ViwoError("failed", f"no {path}")
        return self.files[path]

    def put_file(self, path: str, data: bytes, creds: dict) -> None:
        self.files[path] = data

    suspend = resume = lambda self: None
    read_mem = lambda self, a, n: b""  # noqa: E731
    write_mem = snapshot = rollback = dump = wall = lambda self, *a: None  # noqa: E731


class ColdGuestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.where = Path(self._tmp.name)
        (self.where / "rt").mkdir()
        self.rt = runtime(self.where / "rt", "[plugins]\ngeneric = on\n")
        self.lines: list[str] = []
        self.guest = {"dir": "C:\\Games\\G", "creds": {"user": "viwo", "password": "pw"}}

    def _log(self, message: str, level: str = "info") -> None:
        self.lines.append(message)

    def test_guest_paths_are_spelled_the_guests_way(self) -> None:
        self.assertEqual(
            coldguest.guest_path("C:\\Games\\G\\", "bin/a.exe"), "C:\\Games\\G\\bin\\a.exe"
        )
        self.assertEqual(coldguest.guest_path("/opt/g", "bin/a"), "/opt/g/bin/a")

    def test_deploy_patches_the_guests_own_file_and_restore_puts_it_back(self) -> None:
        guest = Files({"C:\\Games\\G\\bin\\Game.exe": GAME})
        done = coldguest.deploy(self.rt, guest, self.where, SET, self.guest, self._log)
        self.assertEqual(done["deployed"], ["bin/Game.exe"])
        self.assertEqual(guest.files["C:\\Games\\G\\bin\\Game.exe"][0x10:0x12], b"\xcc\xdd")
        self.assertEqual(guest.seen[0]["user"], "viwo")
        again = coldguest.deploy(self.rt, guest, self.where, SET, self.guest, self._log)
        self.assertEqual(again["results"][0]["status"], "already")  # the original stays the first
        back = coldguest.restore(guest, self.where, self.guest, self._log)
        self.assertEqual(back["restored"], ["bin/Game.exe"])
        self.assertEqual(guest.files["C:\\Games\\G\\bin\\Game.exe"], GAME)

    def test_a_set_that_does_not_plan_clean_writes_nothing(self) -> None:
        other = GAME[:0x10] + b"\x00\x00" + GAME[0x12:]
        guest = Files({"C:\\Games\\G\\bin\\Game.exe": other})
        done = coldguest.deploy(self.rt, guest, self.where, SET, self.guest, self._log)
        self.assertEqual(done["deployed"], [])
        self.assertEqual(guest.files["C:\\Games\\G\\bin\\Game.exe"], other)

    def test_unsafe_names_are_refused(self) -> None:
        bad = {"patches": [{"file": "../../evil.exe", "offset": "0", "patched": "00"}]}
        with self.assertRaises(ViwoError):
            coldguest.deploy(self.rt, Files({}), self.where, bad, self.guest, self._log)

    def test_a_tier_without_a_file_channel_says_so(self) -> None:
        class Bare(Files):
            get_file = PatchSession.get_file

        with self.assertRaises(ViwoError) as said:
            coldguest.deploy(self.rt, Bare({}), self.where, SET, self.guest, self._log)
        self.assertIn("no channel into the guest's files", said.exception.message)


class VirtualBoxFilesTests(unittest.TestCase):
    def _session(self, ok: bool, calls: list):
        from types import SimpleNamespace

        from viwo.core.isolation.vbox_session import VBoxSession

        def run(argv, timeout=None):
            calls.append(argv)
            if ok and "copyfrom" in argv:
                Path(argv[-1]).write_bytes(b"FROM-GUEST")
            echo = " ".join(argv)  # a tool that prints its command line back on failure
            return SimpleNamespace(ok=ok, stdout="", stderr="" if ok else f"failed: {echo}")

        os_ = SimpleNamespace(process=SimpleNamespace(run=run))
        return VBoxSession(os_, ["VBoxManage"], {"vm": "viwo-g", "gdb": 1})

    def test_files_go_through_guestcontrol_and_the_password_is_never_said(self) -> None:
        calls: list = []
        creds = {"user": "viwo", "password": "hunter2"}
        session = self._session(True, calls)
        self.assertEqual(session.get_file("C:\\g\\a.exe", creds), b"FROM-GUEST")
        session.put_file("C:\\g\\a.exe", b"NEW", creds)
        self.assertEqual([c[3] for c in calls], ["copyfrom", "copyto"])
        self.assertIn("--username=viwo", calls[0])
        failing = self._session(False, [])
        with self.assertRaises(ViwoError) as said:
            failing.put_file("C:\\g\\a.exe", b"NEW", creds)
        self.assertNotIn("hunter2", said.exception.message)
        self.assertIn("<secret>", said.exception.message)
        with self.assertRaises(ViwoError):
            failing.get_file("C:\\g\\a.exe", {"user": "", "password": ""})  # an account needed


class FakeAgent:
    """qemu-ga over loopback: guest-sync and the guest-file calls on an in-memory file store."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {"/g/a": b"x" * 100_000}
        self.open: dict[int, list] = {}
        self._srv = socket.socket()
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            with conn, conn.makefile("rb") as stream:
                for line in stream:
                    conn.sendall(json.dumps(self._reply(json.loads(line))).encode() + b"\n")

    def _reply(self, msg: dict) -> dict:
        cmd, args = msg["execute"], msg.get("arguments", {})
        if cmd == "guest-sync":
            return {"return": args["id"]}
        if cmd == "guest-file-open":
            if args["mode"] == "rb" and args["path"] not in self.files:
                return {"error": {"desc": "No such file"}}
            handle = len(self.open) + 1
            self.open[handle] = [args["path"], args["mode"], 0, bytearray()]
            return {"return": handle}
        path, mode, at, buf = self.open[args["handle"]]
        if cmd == "guest-file-read":
            part = self.files[path][at : at + args["count"]]
            self.open[args["handle"]][2] = at + len(part)
            eof = at + len(part) >= len(self.files[path])
            return {"return": {"count": len(part), "buf-b64": base64.b64encode(part).decode(),
                               "eof": eof}}  # fmt: skip
        if cmd == "guest-file-write":
            buf += base64.b64decode(args["buf-b64"])
            return {"return": {"count": 0}}
        if mode == "wb":
            self.files[path] = bytes(buf)
        return {"return": {}}


class AgentTests(unittest.TestCase):
    def test_files_round_trip_through_the_agent(self) -> None:
        agent = FakeAgent()
        qga = Qga("127.0.0.1", agent.port)
        self.assertEqual(qga.read("/g/a"), b"x" * 100_000)  # more than one chunk
        qga.write("/g/b", b"y" * 70_000)
        self.assertEqual(agent.files["/g/b"], b"y" * 70_000)
        with self.assertRaises(ViwoError) as missing:
            qga.read("/g/none")
        self.assertIn("No such file", missing.exception.message)
        qga.close()

    def test_no_agent_is_said(self) -> None:
        with socket.socket() as free:
            free.bind(("127.0.0.1", 0))
            port = free.getsockname()[1]
        with self.assertRaises(ViwoError) as none:
            Qga("127.0.0.1", port, timeout=1.0)
        self.assertIn("qemu-ga", none.exception.message)


if __name__ == "__main__":
    unittest.main()
