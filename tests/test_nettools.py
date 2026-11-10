"""L3: `attach.net` (doc 11.2, rung D4): mitmproxy as a pinned third-party tool, started as a
tracked child. Properties: the launch is a local, regular-mode proxy on two distinct free
ports, bound to this machine only, with the flows saved under the target's own folder in the
workspace; the user is told where to point the game and what HTTPS needs; nothing asks for
elevation; a missing tool is unavailable with the install hint; the slot, its backend and its
pin agree; the shipped workbook opens it."""

import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime
from viwo.contracts.analysis import AnalysisTarget, LaunchSpec
from viwo.contracts.types import OutcomeKind
from viwo.core import thirdparty, workbooks
from viwo.core.capture.nettools import MITMPROXY, MitmproxyGui, free_port


class MitmproxyTests(unittest.TestCase):
    def ctx(self, root: Path, located: bool = True):
        said = []
        tool = SimpleNamespace(argv_prefix=(str(root / "mitmweb.exe"),), path=str(root / "m.exe"))
        host = SimpleNamespace(tools=SimpleNamespace(locate=lambda spec: tool if located else None))
        log = lambda message, level="info", stage="": said.append((level, message))  # noqa: E731
        return SimpleNamespace(os=host, staging=root / "ws" / ".runtime" / "t", log=log), said

    def test_a_local_regular_proxy_with_flows_in_the_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = AnalysisTarget("game-exe", "native_binary", (root / "Game.exe",), "generic")
            for _ in range(8):
                ctx, said = self.ctx(root)
                spec = MitmproxyGui().prepare(target, ctx)
                self.assertIsInstance(spec, LaunchSpec)
                argv = list(spec.argv)
                value = lambda flag: argv[argv.index(flag) + 1]  # noqa: E731
                self.assertEqual(
                    (value("--mode"), value("--listen-host")), ("regular", "127.0.0.1")
                )
                self.assertEqual(value("--web-host"), "127.0.0.1")  # this machine only
                ports = {int(value("--listen-port")), int(value("--web-port"))}
                self.assertEqual(len(ports), 2)
                for port in ports:  # free when handed over
                    with socket.socket() as probe:
                        probe.bind(("127.0.0.1", port))
                flows = Path(value("--save-stream-file"))
                self.assertEqual(flows.parent, ctx.staging.resolve())
                self.assertTrue(ctx.staging.is_dir())
                self.assertFalse({"local", "wireguard", "transparent"} & set(argv))  # no elevation
                level, message = said[0]
                self.assertEqual(level, "warn")
                self.assertIn(value("--listen-port"), message)
                self.assertIn("mitm.it", message)  # what HTTPS needs, said

    def test_a_missing_tool_is_unavailable_with_its_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _ = self.ctx(Path(tmp), located=False)
            target = AnalysisTarget("k", "native_binary", (Path(tmp) / "G.exe",), "generic")
            out = MitmproxyGui().prepare(target, ctx)
            self.assertEqual((out.kind, out.error), (OutcomeKind.UNAVAILABLE, MITMPROXY.hint))

    def test_slot_pin_and_workbook_agree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime(Path(tmp))
            slot = rt.slots["attach.net"]
            self.assertEqual((slot.family, slot.default_main), ("attach", "mitmproxy-gui"))
            self.assertIn("mitmproxy", {s.dep_id for s in rt.backends["mitmproxy-gui"].requires})
            pin = thirdparty.manifest()["tools"]["mitmproxy"]
            for os_id in ("windows", "linux"):
                self.assertTrue(pin[os_id]["url"].startswith("https://downloads.mitmproxy.org/"))
                self.assertRegex(pin[os_id]["sha256"], r"^[0-9a-f]{64}$")
            books = {b["id"]: b for b in workbooks.load(rt)[0]}
            book = books["mitmproxy-read-your-games-traffic"]
            self.assertEqual((book["opens"], book["stale"]), ("attach.net", False))
        self.assertNotEqual(free_port(), 0)


if __name__ == "__main__":
    unittest.main()
