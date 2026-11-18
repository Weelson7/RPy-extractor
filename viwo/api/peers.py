"""Who is asking (doc 4.1): this machine or a LAN peer, and a token compared in constant time
whatever text a client sends."""

import hmac
import ipaddress
from pathlib import Path

from viwo.contracts.workspace import safe_member

WILDCARD_OR_LOOPBACK = {"0.0.0.0", "::", "", "127.0.0.1", "localhost", "::1"}


def same(sent: str, token: str) -> bool:
    """A constant-time comparison that any text a client sends can go through (non-ASCII)."""
    return bool(token) and hmac.compare_digest(
        sent.encode("utf-8", "surrogatepass"), token.encode("utf-8")
    )


def loopback(peer: str) -> bool:
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return address.is_loopback or bool(mapped and mapped.is_loopback)


# Workspace files are a game's data: served as what they are, opened as a page they get an
# origin of their own (no script, no cookie, no token of ViWo's). ViWo's own files run only
# its own scripts and are never put in a frame.
UNTRUSTED = {"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"}
OURS = {
    "Content-Security-Policy": "default-src 'self' data: blob:; script-src 'self' blob: "
    "'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' data: blob: "
    "https://www.gstatic.com; frame-ancestors 'none'; object-src 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def send_all(handler, headers: dict[str, str]) -> None:
    for name, value in headers.items():
        handler.send_header(name, value)


def under(root: Path, name: str) -> Path | None:
    """The file `name` names under root, or None. The name is checked before it is joined: a
    UNC or drive name is never resolved (resolving `\\\\host\\share` opens a connection)."""
    member = safe_member(name)
    target = root.joinpath(*member.parts).resolve() if member else None
    inside = target is not None and root.resolve() in target.parents and target.is_file()
    return target if inside else None
