"""L5: what a guest boots from, on the real tiers (doc 11.8; skipped unless VIWO_L5=1 and the
tier is installed). QEMU: UEFI from its own edk2 build, an installer .iso booted with a new empty
disk, and a host folder handed over as a read-only CD whose files read back by their full names.
VirtualBox: UEFI with a virtual TPM 2.0, the installer .iso on its DVD drive beside a new disk,
and the read-only shared folder. Each is checked in the hypervisor's own view of the VM."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_l5_tools import L5, real_runtime
from viwo.contracts.errors import ViwoError
from viwo.core.isolation import session as sessions
from viwo.core.isolation import share
from viwo.core.isolation.qemu import QEMU
from viwo.core.isolation.vbox import VBOX

DATA = b"GAME-DATA-0123456789"


def _pycdlib():
    try:
        import pycdlib

        return pycdlib
    except ImportError:
        return None


@L5
class RealMediaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)  # first in, last out: after every session closed
        self.root = Path(self._tmp.name)
        (self.root / "rt").mkdir()
        self.rt = real_runtime(self.root / "rt")
        if _pycdlib() is None:
            self.skipTest("pycdlib not installed (viwo install pycdlib)")
        self.ws = self.root / "ws"
        self.game = self.root / "game"
        (self.game / "Sub Dir").mkdir(parents=True)
        (
            self.game / "Sub Dir" / "a long name past sixty-four characters for Joliet to cut.bin"
        ).write_bytes(DATA)
        self.installer = share.build(self.game, self.root / "setup.iso", lambda *a: None)

    def tearDown(self) -> None:
        try:
            sessions.act(self.rt, self.ws, "stop")
        except ViwoError:
            pass

    def _start(self, tier: str) -> dict:
        guest = {"memory_mb": 256, "cpus": 1, "headless": True, "efi": True, "share": self.game}
        guest["gpu"] = True  # VirtualBox: VMSVGA with 3D; QEMU: said that it has none here
        if tier == "qemu":
            guest["accel"] = "tcg"
        req = sessions.IsolateRequest(self.ws, self.installer, tier=tier, guest=guest)
        info, held = sessions.start(self.rt, req)
        self.addCleanup(held.close)
        return info

    def test_qemu_uefi_installer_and_a_shared_folder(self) -> None:
        if self.rt.os.tools.locate(QEMU) is None:
            self.skipTest("QEMU not installed")
        self._start("qemu")
        session, _ = sessions._rejoin(self.rt, self.ws, None)
        self.addCleanup(session.release)
        files = [b.get("inserted", {}).get("file", "") for b in session._q().execute("query-block")]
        here = sessions.folder(self.ws) / "qemu"
        self.assertTrue(any(f.endswith("overlay.qcow2") for f in files), files)  # the new disk
        self.assertTrue(any(f.endswith("setup.iso") for f in files), files)  # the installer CD
        self.assertTrue(any(f.endswith("share.iso") for f in files), files)  # the shared folder
        self.assertTrue((here / "efi-vars.fd").is_file())  # UEFI variables of this session
        self.assertTrue(session.running())
        iso = _pycdlib().PyCdlib()
        iso.open(str(here / "share.iso"))
        try:
            import io

            out = io.BytesIO()
            name = "a long name past sixty-four characters for Joliet to cut.bin"
            iso.get_file_from_iso_fp(out, udf_path=f"/Sub Dir/{name}")
            self.assertEqual(out.getvalue(), DATA)  # the full name, the file's bytes
        finally:
            iso.close()

    def test_virtualbox_uefi_tpm_installer_and_shared_folder(self) -> None:
        if self.rt.os.tools.locate(VBOX) is None:
            self.skipTest("VirtualBox not installed")
        info = self._start("vbox")
        session, _ = sessions._rejoin(self.rt, self.ws, None)
        shown = session._run("showvminfo", info["vm"], "--machinereadable").stdout.lower()
        self.assertIn('firmware="efi', shown)
        self.assertIn('graphicscontroller="vmsvga"', shown)
        self.assertIn('accelerate3d="on"', shown)
        settings = next(line for line in shown.splitlines() if line.startswith("cfgfile="))
        vbox = Path(settings.split('"', 1)[1].rstrip('"').replace("\\\\", "\\"))
        self.assertIn('TrustedPlatformModule type="v2_0"', vbox.read_text(encoding="utf-8"))
        self.assertIn("setup.iso", shown)  # the installer on the DVD drive
        self.assertIn("disk.vdi", shown)  # beside a new empty disk
        self.assertIn('sharedfoldernamemachinemapping1="viwo-share"', shown)
        self.assertEqual(session.state(), "running")


if __name__ == "__main__":
    unittest.main()
