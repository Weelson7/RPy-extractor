"""D4 `attach.net` (doc 11.2): "Continue in mitmproxy" starts mitmproxy's own web interface
(MIT, pinned, a separate process) as a tracked child, a local proxy for the user's own game
traffic. Regular proxy mode only: nothing is redirected by force and nothing needs elevation;
the game, or the system, is pointed at the proxy by the user, who also decides whether to
trust mitmproxy's certificate authority (the workbook says how). The flows are saved in the
workspace as they come. ViWo writes no capture code of its own."""

import socket

from viwo.contracts.analysis import AnalysisTarget, Handoff, LaunchSpec
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from .handoffs import ATTACH

MITMPROXY = DependencySpec.of("mitmproxy")


def free_port() -> int:
    """A local port nothing listens on now (the OS picks it)."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class MitmproxyGui(Handoff):
    backend_id, license, isolation = "mitmproxy-gui", "MIT", "subprocess"
    label, accepts, families = "Continue in mitmproxy", ("native_binary",), ATTACH
    self_check_args = ("--version",)
    network = "none"  # doc 11.6: it relays the user's own traffic and fetches nothing itself

    requires = (MITMPROXY,)

    def prepare(self, target: AnalysisTarget, ctx) -> LaunchSpec | Outcome:
        if (tool := ctx.os.tools.locate(MITMPROXY)) is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=MITMPROXY.hint)
        ctx.staging.mkdir(parents=True, exist_ok=True)
        flows = (ctx.staging / "flows.mitm").resolve()
        proxy, web = free_port(), free_port()
        ctx.log(  # never silent: where to point the game, and what HTTPS needs
            f"mitmproxy listens on 127.0.0.1:{proxy} (its window: http://127.0.0.1:{web}/). "
            f"Point {target.paths[0].name} or the system proxy at it; HTTPS shows once you trust "
            f"mitmproxy's certificate (open http://mitm.it through the proxy). Flows: {flows}",
            "warn",
            "attach",
        )
        argv = (*tool.argv_prefix, "--mode", "regular", "--listen-host", "127.0.0.1")
        argv += ("--listen-port", str(proxy), "--web-host", "127.0.0.1", "--web-port", str(web))
        return LaunchSpec((*argv, "--save-stream-file", str(flows)), flows.parent)
