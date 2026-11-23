"""A tiny GDB Remote Serial Protocol client over a stdlib socket (doc 11.8 T2). ViWo speaks the
wire protocol to QEMU's own gdbstub (`-gdb tcp::PORT -S`) to read and write guest memory and to
stop and continue the target from outside the guest. It is a protocol client, not hypervisor,
driver or evasion code (CLAUDE.md), and it needs no gdb binary located on this host."""

import socket
import time


class GdbError(Exception):
    """A gdbstub error reply (`Enn`) or a framing fault."""


def _checksum(data: str) -> str:
    return f"{sum(data.encode('latin-1')) & 0xFF:02x}"


def _decode(body: str) -> str:
    """Un-escape `}x` and expand `*` run-length encoding a stub may use in a reply."""
    out, i = [], 0
    while i < len(body):
        ch = body[i]
        if ch == "}" and i + 1 < len(body):
            out.append(chr(ord(body[i + 1]) ^ 0x20))
            i += 2
        elif ch == "*" and out and i + 1 < len(body):
            out.append(out[-1][-1] * (ord(body[i + 1]) - 29))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


class GdbClient:
    """One connection to a gdbstub. Memory ops need the target stopped (the caller suspends)."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = bytearray()

    @classmethod
    def connect(cls, host: str, port: int, deadline: float = 10.0) -> "GdbClient":
        """Open the connection, retrying while the stub's port is not up yet."""
        end = time.monotonic() + deadline
        while True:
            try:
                sock = socket.create_connection((host, port), timeout=5.0)
                sock.settimeout(10.0)
                return cls(sock)
            except OSError:
                if time.monotonic() >= end:
                    raise
                time.sleep(0.2)

    def _read(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise GdbError("the gdbstub closed the connection")
            self._buf.extend(chunk)
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def _recv_packet(self) -> str:
        while self._read(1) != b"$":
            pass
        body = bytearray()
        while (ch := self._read(1)) != b"#":
            body.extend(ch)
        self._read(2)  # the two checksum digits (trusted on a local socket)
        self._sock.sendall(b"+")
        return _decode(body.decode("latin-1"))

    def command(self, data: str) -> str:
        """Send one packet and return the reply's payload, re-sending on a NAK."""
        for _ in range(5):
            self._sock.sendall(b"$" + data.encode("latin-1") + b"#" + _checksum(data).encode())
            if self._read(1) == b"+":
                return self._recv_packet()
        raise GdbError(f"the gdbstub kept rejecting {data!r}")

    def read_mem(self, addr: int, size: int) -> bytes:
        reply = self.command(f"m{addr:x},{size:x}")
        if not reply or reply.startswith("E"):
            raise GdbError(f"read {size} bytes at {addr:#x}: {reply or 'empty reply'}")
        return bytes.fromhex(reply)

    def write_mem(self, addr: int, data: bytes) -> None:
        reply = self.command(f"M{addr:x},{len(data):x}:{data.hex()}")
        if reply != "OK":
            raise GdbError(f"write at {addr:#x}: {reply or 'empty reply'}")

    def interrupt(self) -> str:
        """Stop a running target (raw Ctrl-C byte); returns the stop reply."""
        self._sock.sendall(b"\x03")
        return self._recv_packet()

    def cont(self) -> None:
        """Resume; the stop reply is left on the wire until the next interrupt."""
        self._sock.sendall(b"$c#" + _checksum("c").encode())
        self._read(1)  # the ack for the continue packet

    def drop(self) -> None:
        """Close without detaching: QEMU keeps the guest stopped (a detach would resume it)."""
        self._sock.close()

    def close(self) -> None:
        try:
            self._sock.sendall(b"$D#" + _checksum("D").encode())
        except OSError:
            pass
        finally:
            self._sock.close()
