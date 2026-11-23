"""A small client for the QEMU guest agent (doc 11.8 T2): files inside the guest, read and
written by `qemu-ga` running in it, over the virtio-serial channel QEMU exposes on loopback.
JSON lines; `guest-sync` first to drop anything a previous client left; file content in base64
chunks. ViWo speaks the protocol; the agent is the guest's own (virtio-win guest tools on
Windows, the qemu-guest-agent package on Linux)."""

import base64
import json
import random
import socket

from viwo.contracts.errors import ViwoError

CHUNK = 48 * 1024
NO_AGENT = (
    "no guest agent answers: install qemu-ga in the guest (virtio-win guest tools on Windows)"
)


class Qga:
    def __init__(self, host: str, port: int, timeout: float = 10.0) -> None:
        try:
            self._sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as exc:
            raise ViwoError("unavailable", NO_AGENT) from exc
        self._buf = bytearray()
        token = random.randrange(1, 1 << 30)
        if self._call("guest-sync", id=token) != token:
            raise ViwoError("unavailable", NO_AGENT)

    def _line(self) -> dict:
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ViwoError("unavailable", NO_AGENT)
            self._buf.extend(chunk)
        line, _, rest = self._buf.partition(b"\n")
        self._buf = bytearray(rest)
        return json.loads(line) if line.strip() else {}

    def _call(self, command: str, **arguments):
        try:
            message = json.dumps({"execute": command, "arguments": arguments})
            self._sock.sendall(message.encode() + b"\n")
            while True:
                reply = self._line()
                if "error" in reply:
                    raise ViwoError(
                        "failed", f"guest agent {command}: {reply['error'].get('desc')}"
                    )
                if "return" in reply:
                    return reply["return"]
        except (OSError, ValueError) as exc:
            raise ViwoError("unavailable", f"{NO_AGENT} ({exc})") from exc

    def read(self, path: str) -> bytes:
        handle, out = self._call("guest-file-open", path=path, mode="rb"), bytearray()
        try:
            while True:
                part = self._call("guest-file-read", handle=handle, count=CHUNK)
                out += base64.b64decode(part.get("buf-b64", ""))
                if part.get("eof") or not part.get("count"):
                    return bytes(out)
        finally:
            self._call("guest-file-close", handle=handle)

    def write(self, path: str, data: bytes) -> None:
        handle = self._call("guest-file-open", path=path, mode="wb")
        try:
            for at in range(0, len(data), CHUNK):
                chunk = base64.b64encode(data[at : at + CHUNK]).decode()
                self._call("guest-file-write", handle=handle, **{"buf-b64": chunk})
        finally:
            self._call("guest-file-close", handle=handle)

    def close(self) -> None:
        self._sock.close()
