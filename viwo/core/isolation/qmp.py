"""A tiny QMP client (QEMU Machine Protocol: JSON lines over a socket) for snapshots and a guest
memory dump (doc 11.8 T2). Stdlib socket + json; QEMU's own control channel, not code of ViWo's
reaching into the guest."""

import json
import socket
import time


class QmpError(Exception):
    """A QMP `error` reply or a connection fault."""


class QmpClient:
    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = bytearray()
        self._greeting = self._read_json()  # the server's QMP greeting
        self.execute("qmp_capabilities")  # leave capabilities-negotiation mode

    @classmethod
    def connect(cls, host: str, port: int, deadline: float = 10.0) -> "QmpClient":
        end = time.monotonic() + deadline
        while True:
            try:
                sock = socket.create_connection((host, port), timeout=5.0)
                sock.settimeout(30.0)
                return cls(sock)
            except OSError:
                if time.monotonic() >= end:
                    raise
                time.sleep(0.2)

    def _read_json(self) -> dict:
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise QmpError("the QMP socket closed")
            self._buf.extend(chunk)
        line, _, rest = self._buf.partition(b"\n")
        self._buf = bytearray(rest)
        return json.loads(line.decode("utf-8"))

    def execute(self, command: str, **arguments):
        """Run one command; skip asynchronous events until its return (or raise on error)."""
        msg = {"execute": command}
        if arguments:
            msg["arguments"] = arguments
        self._sock.sendall(json.dumps(msg).encode("utf-8") + b"\n")
        while True:
            reply = self._read_json()
            if "error" in reply:
                raise QmpError(reply["error"].get("desc", command))
            if "return" in reply:
                return reply["return"]

    def monitor(self, line: str) -> str:
        """Run a human-monitor command (savevm/loadvm) and return its text output."""
        return self.execute("human-monitor-command", **{"command-line": line}) or ""

    def close(self) -> None:
        self._sock.close()
