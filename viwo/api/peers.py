"""Who is asking (doc 4.1): this machine or a LAN peer, and a token compared in constant time
whatever text a client sends."""

from __future__ import annotations

import hmac
import ipaddress

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
