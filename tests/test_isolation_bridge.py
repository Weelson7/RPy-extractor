"""The cold+live bridge (doc 11.8), Tier 3 (DRAKVUF/LibVMI) command construction, and the
isolation CLI/API surface. The bridge turns one located patch (the same file offset the cold
writer uses) into a live virtual-address write under the atomic suspend/write/verify/resume. VMI
reports not-ready off a bare-metal Linux VMI host and builds its CLI commands from located tools.
No VM or VMI host runs here."""

from __future__ import annotations

import stat
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import runtime
from viwo.contracts.errors import ViwoError
from viwo.contracts.patcher import PatcherBackend, PatchSession, PatchTarget, Wall, WallReport
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.core.context import core_context
from viwo.core.isolation import atomic_write, live
from viwo.core.isolation import session as sessions
from viwo.core.isolation.live import apply_live, located_va, write_located
from viwo.core.isolation.session import IsolateRequest
from viwo.core.isolation.vmi import VMI_READ, VmiPatcher, VmiSession, control_of


def make_pe(path: Path) -> None:
    """A minimal PE32+: .text at RVA 0x1000 / file offset 0x200, image base 0x140000000; the code
    holds `74 05 90` at RVA 0x1010 (file offset 0x210)."""
    head = bytearray(0x200)
    head[:2], head[0x3C:0x40] = b"MZ", (0x40).to_bytes(4, "little")
    head[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HH", head, 0x44, 0x8664, 1)
    struct.pack_into("<H", head, 0x54, 0xF0)
    struct.pack_into("<HxxxxxxxxxxxxxxxxxxxxxxQ", head, 0x58, 0x20B, 0x140000000)
    struct.pack_into("<8sIIII", head, 0x58 + 0xF0, b".text", 0x100, 0x1000, 0x200, 0x200)
    code = bytearray(b"\x90" * 0x200)
    code[0x10:0x13] = b"\x74\x05\x90"
    path.write_bytes(bytes(head) + bytes(code))


class DictSession(PatchSession):
    """A live target backed by an address->byte map, so atomic_write's readback verify holds."""

    def __init__(self) -> None:
        self.store: dict[int, int] = {}
        self.events: list = []
        self.refuse: set[int] = set()  # addresses whose write hits a wall
        self.heals: dict[int, bytes] = {}  # bytes the target puts back once it runs again
        self.closed = False

    def suspend(self) -> None:
        self.events.append("suspend")

    def resume(self) -> None:
        self.events.append("resume")
        for addr, data in self.heals.items():
            self.store.update({addr + i: b for i, b in enumerate(data)})

    def read_mem(self, addr: int, size: int) -> bytes:
        return bytes(self.store.get(a, 0) for a in range(addr, addr + size))

    def write_mem(self, addr: int, data: bytes) -> WallReport:
        self.events.append(("write", addr))
        if addr in self.refuse:
            return WallReport(Wall.NOT_READY, "refused by the test")
        for i, b in enumerate(data):
            self.store[addr + i] = b
        return WallReport()

    def record(self) -> dict:
        return {"token": 7}

    def close(self) -> None:
        self.closed = True

    def snapshot(self, name: str) -> Outcome:
        return Outcome(OutcomeKind.OK)

    def rollback(self, name: str) -> Outcome:
        return Outcome(OutcomeKind.OK)

    def dump(self, out: Path) -> Outcome:
        out.write_bytes(b"CORE")
        return Outcome(OutcomeKind.OK)

    def wall(self) -> WallReport:
        return WallReport()


class DictBackend(PatcherBackend):
    """A tier whose session is rejoined from its record, as QEMU's is."""

    backend_id, license, tier = "dict", "MIT", 0

    def __init__(self) -> None:
        self.session: DictSession | None = None

    def ready(self, os) -> WallReport:
        return WallReport()

    def start(self, target: PatchTarget, ctx, *, snapshot: bool = False):
        self.session, self.target = DictSession(), target
        return self.session

    def reattach(self, record: dict, ctx):
        if self.session is None or self.session.closed or record.get("token") != 7:
            return Outcome(OutcomeKind.UNAVAILABLE, error="gone")
        return self.session


TWO = {
    "schema": 1,
    "patches": [
        {"file": "Game.exe", "rva": "0x1010", "original": "74 05", "patched": "EB 05"},
        {"file": "Game.exe", "rva": "0x1012", "original": "90", "patched": "CC"},
    ],
}


class BridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        make_pe(self.game / "Game.exe")
        self.data = (self.game / "Game.exe").read_bytes()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_file_offset_maps_to_the_preferred_virtual_address(self) -> None:
        self.assertEqual(located_va(self.data, 0x210), 0x140001010)  # base + RVA 0x1010

    def test_base_override_rebases_onto_the_live_module(self) -> None:
        self.assertEqual(located_va(self.data, 0x210, base=0x7FF000000000), 0x7FF000001010)

    def test_write_located_is_atomic_at_the_virtual_address(self) -> None:
        session = DictSession()
        wall = write_located(session, self.data, 0x210, b"\xeb\x05")
        self.assertFalse(wall.blocked)
        self.assertEqual(session.store[0x140001010], 0xEB)
        self.assertEqual(session.events, ["suspend", ("write", 0x140001010), "resume"])

    def test_same_recipe_cold_offset_and_live_address(self) -> None:
        (self.root / "rt").mkdir(parents=True, exist_ok=True)
        rt = runtime(self.root / "rt", "[plugins]\ngeneric = on\n")
        patch_set = {
            "schema": 1,
            "patches": [
                {"file": "Game.exe", "rva": "0x1010", "original": "74 05", "patched": "EB 05"}
            ],
        }
        session = DictSession()
        report = apply_live(rt, session, self.game, patch_set)
        self.assertTrue(report["written"])
        r = report["results"][0]
        self.assertEqual(r["offset"], 0x210)  # the cold writer's file offset
        self.assertEqual(session.store[located_va(self.data, 0x210)], 0xEB)  # written live there
        self.assertEqual(r["wall"], "none")

    def _live(self, session, journal):
        (self.root / "rt").mkdir(parents=True, exist_ok=True)
        rt = runtime(self.root / "rt", "[plugins]\ngeneric = on\n")
        with mock.patch.object(live, "SETTLE", 0.01):
            return apply_live(rt, session, self.game, TWO, journal=journal)

    def test_a_journalled_set_records_what_it_replaced_and_undo_puts_it_back(self) -> None:
        session, journal = DictSession(), self.root / "j" / "journal.jsonl"
        va = located_va(self.data, 0x210)
        session.store.update({va: 0x74, va + 1: 0x05, va + 2: 0x90})
        report = self._live(session, journal)
        self.assertTrue(report["written"])
        self.assertEqual(report["journalled"], 2)
        self.assertEqual(session.read_mem(va, 3), b"\xeb\x05\xcc")
        self.assertEqual(live.undo(session, journal), {"restored": 2, "edits": 2})
        self.assertEqual(session.read_mem(va, 3), b"\x74\x05\x90")  # byte for byte
        self.assertFalse(journal.exists())
        self.assertEqual(live.undo(session, journal), {"restored": 0, "edits": 0})

    def test_a_set_is_all_or_nothing_when_one_edit_hits_a_wall(self) -> None:
        session, journal = DictSession(), self.root / "journal.jsonl"
        va = located_va(self.data, 0x210)
        session.store.update({va: 0x74, va + 1: 0x05, va + 2: 0x90})
        session.refuse.add(va + 2)  # the second edit cannot land
        report = self._live(session, journal)
        self.assertFalse(report["written"])
        self.assertEqual(report["rolled_back"], 1)
        self.assertEqual(session.read_mem(va, 3), b"\x74\x05\x90")  # the first one was put back
        self.assertFalse(journal.exists())  # nothing stays, nothing is journalled
        self.assertIn("put back", report["results"][0]["detail"])
        self.assertEqual(report["results"][1]["wall"], "not_ready")

    def test_bytes_the_target_puts_back_after_it_runs_are_an_integrity_wall(self) -> None:
        session = DictSession()
        session.heals[0x40] = b"\x74"  # a self-check restores its byte on resume
        self.assertFalse(atomic_write(session, 0x40, b"\xeb").blocked)  # unseen without settle
        wall = atomic_write(session, 0x40, b"\xeb", settle=0.01)
        self.assertEqual(wall.wall, Wall.INTEGRITY_CHECK)
        self.assertIn("put its bytes back", wall.detail)


class VmiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _rt(self, tools: dict[str, Path]):
        body = "[plugins]\ngeneric = on\n[tools]\n" + "".join(
            f"{k} = {v}\n" for k, v in tools.items()
        )
        (self.root / "rt").mkdir(parents=True, exist_ok=True)
        return runtime(self.root / "rt", body)

    def _fake(
        self,
        name: str,
        body: str = "#!{python}\nimport sys\nopen(sys.argv[-1],'wb').write(b'MEM')\n",
    ) -> Path:
        folder = self.root / "vmi"
        folder.mkdir(parents=True, exist_ok=True)
        script = folder / f"{name}.py"
        script.write_text(body.format(python=sys.executable))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        if sys.platform == "win32":
            wrapper = folder / f"{name}.cmd"
            wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
            return wrapper
        return script

    def test_not_ready_off_a_bare_metal_linux_vmi_host(self) -> None:
        rt = self._rt({})
        report = VmiPatcher().ready(rt.os)
        self.assertTrue(report.blocked)
        self.assertEqual(report.wall, Wall.NOT_READY)
        if sys.platform == "win32":
            self.assertIn("Windows", report.detail)  # the requirement rides in the wall's detail
        target = PatchTarget(exe=self.root / "G.exe", workspace=self.root / "ws")
        ctx = core_context(rt, "isolate", self.root, self.root / "work")
        self.assertEqual(rt.backends["libvmi"].start(target, ctx).kind, OutcomeKind.UNAVAILABLE)

    def test_control_prefers_virsh_then_falls_back_to_xl(self) -> None:
        virsh = self._fake("virsh")
        both = self._rt({"virsh": virsh, "xl": self._fake("xl")})
        self.assertEqual(control_of(both.os)[1], ("suspend", "resume"))  # virsh wins
        xl_only = self._rt({"xl": self._fake("xl")})
        self.assertEqual(control_of(xl_only.os)[1], ("pause", "unpause"))
        self.assertIsNone(control_of(self._rt({}).os))

    def test_write_is_a_not_ready_wall_and_dump_runs_the_read_tool(self) -> None:
        rt = self._rt(
            {"vmi-dump-memory": self._fake("vmi-dump-memory"), "virsh": self._fake("virsh")}
        )
        read_argv = rt.os.tools.locate(VMI_READ).argv_prefix
        session = VmiSession(rt.os, "guest", read_argv, control_of(rt.os))
        self.assertEqual(session.write_mem(0x1000, b"\x90").wall, Wall.NOT_READY)
        out = self.root / "core.raw"
        self.assertTrue(session.dump(out).ok)
        self.assertEqual(out.read_bytes(), b"MEM")  # vmi-dump-memory wrote the physical image


class IsolateCliApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "rt").mkdir(parents=True, exist_ok=True)
        self.rt = runtime(self.root / "rt", "[plugins]\ngeneric = on\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cli_list_names_the_three_tiers(self) -> None:
        from types import SimpleNamespace

        from viwo.cli_isolate import isolate

        args = SimpleNamespace(action="list", list=False)
        env = isolate(self.rt, args, None)
        tiers = {t["backend"]: t for t in env.data["tiers"]}
        self.assertEqual(set(tiers), {"vbox", "qemu", "libvmi"})
        self.assertEqual(tiers["qemu"]["tier"], 2)

    def test_start_refuses_when_no_tier_is_ready(self) -> None:
        req = IsolateRequest(self.root / "ws")  # nothing located here
        with self.assertRaises(ViwoError) as caught:
            sessions.start(self.rt, req)
        self.assertEqual(caught.exception.code, "unavailable")

    def test_start_unknown_tier_is_a_bad_request(self) -> None:
        req = IsolateRequest(self.root / "ws", tier="nope")
        with self.assertRaises(ViwoError) as caught:
            sessions.start(self.rt, req)
        self.assertEqual(caught.exception.code, "invalid_request")

    def test_one_shot_drive_starts_patches_and_closes(self) -> None:
        game = self.root / "game"
        game.mkdir()
        make_pe(game / "Game.exe")
        patchset = self.root / "two.patch.json"
        patchset.write_text(__import__("json").dumps(TWO), encoding="utf-8")
        backend = self.rt.backends["dict"] = DictBackend()
        req = IsolateRequest(self.root / "ws", exe=game / "Game.exe", tier="dict")
        probe = sessions.drive(self.rt, req)  # no set: start and close
        self.assertEqual((probe["tier"], probe["started"]), ("dict", True))
        self.assertTrue(backend.session.closed)
        report = sessions.drive(self.rt, req, patchset)
        self.assertTrue(report["written"])
        self.assertEqual(backend.session.store[0x140001010], 0xEB)
        self.assertTrue(backend.session.closed)  # and nothing is left to rejoin
        with self.assertRaises(ViwoError):
            sessions.act(self.rt, self.root / "ws", "status")

    def test_one_shot_cli_and_api_forms(self) -> None:
        from types import SimpleNamespace

        from viwo.api import handlers_isolation as api
        from viwo.cli_isolate import GUEST, isolate

        exe = self.root / "G.exe"
        exe.write_bytes(b"MZ")
        self.rt.backends["dict"] = DictBackend()
        guest = dict.fromkeys(GUEST, False) | {"memory_mb": 64, "cpus": 1, "accel": ""}
        args = SimpleNamespace(
            action=str(exe), list=False, workspace=self.root / "ws", image=None, tier="dict",
            pid=0, snapshot=False, patchset=None, base=0, **guest,
        )  # fmt: skip
        self.assertTrue(isolate(self.rt, args, None).data["started"])
        args.list = True  # --list still only lists
        self.assertIn("tiers", isolate(self.rt, args, None).data)
        args.list, args.action = False, str(self.root / "missing.exe")
        with self.assertRaises(ViwoError) as missing:
            isolate(self.rt, args, None)
        self.assertEqual(missing.exception.code, "not_found")
        app = SimpleNamespace(rt=self.rt, workspace=self.root / "ws")
        with mock.patch("viwo.api.handlers_capture._ours", lambda app: None):
            done = api.run_isolation(app, {"exePath": str(exe), "tier": "dict"})
            self.assertTrue(done["success"] and done["started"], done)
            self.assertFalse(api.run_isolation(app, {"tier": "dict"})["success"])  # no exe

    def test_an_action_without_a_session_says_none_runs(self) -> None:
        with self.assertRaises(ViwoError) as caught:
            sessions.act(self.rt, self.root / "ws", "status")
        self.assertEqual(caught.exception.code, "not_found")
        with self.assertRaises(ViwoError) as bad:
            sessions.act(self.rt, self.root / "ws", "explode")
        self.assertEqual(bad.exception.code, "invalid_request")

    def test_a_session_outlives_its_start_and_every_action_rejoins_it(self) -> None:
        ws_dir = self.root / "ws"
        backend = self.rt.backends["dict"] = DictBackend()
        guest = {"memory_mb": 512, "network": True}
        info, session = sessions.start(self.rt, IsolateRequest(ws_dir, tier="dict", guest=guest))
        self.assertEqual((info["tier"], info["token"]), ("dict", 7))
        self.assertEqual((backend.target.memory_mb, backend.target.network), (512, True))
        self.assertTrue((ws_dir / ".runtime" / "isolation" / "session.json").is_file())
        with self.assertRaises(ViwoError) as twice:
            sessions.start(self.rt, IsolateRequest(ws_dir, tier="dict"))
        self.assertEqual(twice.exception.code, "busy")
        self.assertEqual(sessions.act(self.rt, ws_dir, "status")["token"], 7)
        sessions.act(self.rt, ws_dir, "pause")
        sessions.act(self.rt, ws_dir, "resume")
        self.assertEqual(session.events, ["suspend", "resume"])
        self.assertEqual(sessions.act(self.rt, ws_dir, "snapshot")["snapshot"], "base")
        self.assertEqual(sessions.act(self.rt, ws_dir, "rollback", name="s1")["rollback"], "s1")
        dump = sessions.act(self.rt, ws_dir, "dump", name="core")
        self.assertEqual(Path(dump["dump"]).read_bytes(), b"CORE")
        self.assertTrue(Path(dump["dump"]).is_relative_to(ws_dir))  # never beside a game
        with self.assertRaises(ViwoError):
            sessions.act(self.rt, ws_dir, "dump", name="../up")
        with self.assertRaises(ViwoError):
            sessions.act(self.rt, ws_dir, "patch")  # no program, no set
        self.assertEqual(sessions.act(self.rt, ws_dir, "undo")["edits"], 0)
        self.assertTrue(sessions.act(self.rt, ws_dir, "stop")["stopped"])
        self.assertTrue(session.closed)
        with self.assertRaises(ViwoError) as gone:
            sessions.act(self.rt, ws_dir, "status")
        self.assertEqual(gone.exception.code, "not_found")

    def test_patch_action_writes_the_set_into_the_session_and_journals_it(self) -> None:
        game = self.root / "game"
        game.mkdir()
        make_pe(game / "Game.exe")
        patchset = self.root / "two.patch.json"
        patchset.write_text(__import__("json").dumps(TWO), encoding="utf-8")
        ws_dir = self.root / "ws"
        self.rt.backends["dict"] = DictBackend()
        _, session = sessions.start(self.rt, IsolateRequest(ws_dir, tier="dict"))
        opt = {"exe": game / "Game.exe", "patchset": patchset}
        with mock.patch.object(live, "SETTLE", 0.01):
            report = sessions.act(self.rt, ws_dir, "patch", **opt)
        self.assertTrue(report["written"])
        self.assertEqual(session.store[0x140001010], 0xEB)
        self.assertEqual(sessions.act(self.rt, ws_dir, "undo")["restored"], 2)

    def test_a_record_whose_guest_has_gone_is_dropped_and_said(self) -> None:
        ws_dir = self.root / "ws"
        backend = self.rt.backends["dict"] = DictBackend()
        sessions.start(self.rt, IsolateRequest(ws_dir, tier="dict"))
        backend.session.closed = True  # the guest ended by itself
        with self.assertRaises(ViwoError) as gone:
            sessions.act(self.rt, ws_dir, "status")
        self.assertIn("gone", gone.exception.message)
        self.assertFalse((ws_dir / ".runtime" / "isolation" / "session.json").exists())

    def test_api_actions_go_through_the_same_session(self) -> None:
        from types import SimpleNamespace

        from viwo.api import handlers_isolation as api

        self.rt.backends["dict"] = DictBackend()
        app = SimpleNamespace(rt=self.rt, workspace=self.root / "ws")
        with mock.patch("viwo.api.handlers_capture._ours", lambda app: None):
            started = api.run_isolation(app, {"action": "start", "tier": "dict", "memory": 256})
            self.assertTrue(started["success"] and started["started"], started)
            self.assertTrue(api.run_isolation(app, {"action": "pause"})["success"])
            self.assertFalse(api.run_isolation(app, {"action": "start", "tier": "dict"})["success"])
            self.assertFalse(api.run_isolation(app, {"action": "pause", "base": "x"})["success"])
            self.assertTrue(api.run_isolation(app, {"action": "stop"})["stopped"])

    def test_api_tiers_route_reports_readiness(self) -> None:
        from viwo.api.handlers_isolation import isolation_tiers

        app = __import__("types").SimpleNamespace(rt=self.rt)
        out = isolation_tiers(app, {})
        self.assertTrue(out["success"])
        self.assertEqual(len(out["tiers"]), 3)
        self.assertIn("enabled", out)


if __name__ == "__main__":
    unittest.main()
