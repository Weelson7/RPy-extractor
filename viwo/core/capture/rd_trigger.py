"""Unattended capture trigger, run by a Python that has RenderDoc's `renderdoc` module (the
installed `qrenderdoc --py`): finds the game renderdoccmd launched on this machine through
RenderDoc's target control, waits, asks for one frame capture, and returns once the capture
file exists. A separate process; not imported by ViWo.

Usage: python rd_trigger.py <delay seconds> <timeout seconds>
       (or VIWO_RD_DELAY / VIWO_RD_TIMEOUT in the environment, since qrenderdoc passes no argv)
Exit 0 when a capture was written, 2 when no target was found, 3 on timeout.
"""

import os
import sys
import time

import renderdoc as rd  # type: ignore  # provided by the RenderDoc install


def targets(deadline: float) -> int:
    """The newest target-control ident on this machine (the game ViWo just launched), waiting
    until it registers; an older RenderDoc-injected process is skipped."""
    while time.time() < deadline:
        ident = newest = rd.EnumerateRemoteTargets("", 0)
        while ident:
            newest = ident
            ident = rd.EnumerateRemoteTargets("", ident)
        if newest:
            return newest
        time.sleep(0.5)
    return 0


def main(delay: float, timeout: float) -> int:
    deadline = time.time() + timeout
    ident = targets(deadline)
    if not ident:
        return 2
    conn = rd.CreateTargetControl("", ident, "viwo", True)
    if conn is None:
        return 2
    try:
        time.sleep(delay)
        conn.TriggerCapture(1)
        while time.time() < deadline:
            msg = conn.ReceiveMessage(None)
            if msg.type == rd.TargetControlMessageType.NewCapture:
                print(f"capture {msg.newCapture.path}", flush=True)
                return 0
            time.sleep(0.1)
    finally:
        conn.Shutdown()
    return 3


if __name__ == "__main__":
    args = sys.argv[1:3] if len(sys.argv) >= 3 else []
    delay = float(args[0] if args else os.environ.get("VIWO_RD_DELAY", "30"))
    timeout = float(args[1] if args else os.environ.get("VIWO_RD_TIMEOUT", "180"))
    sys.exit(main(delay, timeout))
