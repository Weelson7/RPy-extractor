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

from tests.helpers import runtime
from viwo.contracts.patcher import PatchSession, PatchTarget, Wall, WallReport
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.core.context import core_context
from viwo.core.isolation.live import IsolateRequest, apply_live, drive, located_va, write_located
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

    def suspend(self) -> None:
        self.events.append("suspend")

    def resume(self) -> None:
        self.events.append("resume")

    def read_mem(self, addr: int, size: int) -> bytes:
        return bytes(self.store.get(a, 0) for a in range(addr, addr + size))

    def write_mem(self, addr: int, data: bytes) -> WallReport:
        self.events.append(("write", addr))
        for i, b in enumerate(data):
            self.store[addr + i] = b
        return WallReport()

    def snapshot(self, name: str) -> Outcome:
        return Outcome(OutcomeKind.OK)

    def rollback(self, name: str) -> Outcome:
        return Outcome(OutcomeKind.OK)

    def dump(self, out: Path) -> Outcome:
        return Outcome(OutcomeKind.OK)

    def wall(self) -> WallReport:
        return WallReport()


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

        args = SimpleNamespace(list=True, exe=None)
        env = isolate(self.rt, args, None)
        tiers = {t["backend"]: t for t in env.data["tiers"]}
        self.assertEqual(set(tiers), {"vbox", "qemu", "libvmi"})
        self.assertEqual(tiers["qemu"]["tier"], 2)

    def test_drive_refuses_when_no_tier_is_ready(self) -> None:
        from viwo.contracts.errors import ViwoError

        req = IsolateRequest(self.root / "G.exe", self.root / "ws")  # nothing located here
        with self.assertRaises(ViwoError) as caught:
            drive(self.rt, req)
        self.assertEqual(caught.exception.code, "unavailable")

    def test_drive_unknown_tier_is_a_bad_request(self) -> None:
        from viwo.contracts.errors import ViwoError

        req = IsolateRequest(self.root / "G.exe", self.root / "ws", tier="nope")
        with self.assertRaises(ViwoError) as caught:
            drive(self.rt, req)
        self.assertEqual(caught.exception.code, "invalid_request")

    def test_api_tiers_route_reports_readiness(self) -> None:
        from viwo.api.handlers_isolation import isolation_tiers

        app = __import__("types").SimpleNamespace(rt=self.rt)
        out = isolation_tiers(app, {})
        self.assertTrue(out["success"])
        self.assertEqual(len(out["tiers"]), 3)
        self.assertIn("enabled", out)


if __name__ == "__main__":
    unittest.main()
