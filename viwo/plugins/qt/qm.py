"""Qt compiled translations (`.qm`): a 16-byte magic then tagged blocks (`tag u8`, `length u32`
big-endian, payload). The Messages block (tag 0x69) holds each message as sub-records: source
(0x06), context (0x07), comment (0x08) in UTF-8 and the translation (0x03) in UTF-16-BE, ended by
0x01. `decode.qm` reads them into JSON for viewing; it is one way (the Hashes index Qt builds for
lookup is not re-authored here), said per file."""

import json
import struct

MAGIC = bytes.fromhex("3cb86418caef9c95cd211cbf60a1bddd")
MESSAGES = 0x69
LANGUAGE = 0xA7
SUB = {0x03: "translation", 0x06: "source", 0x07: "context", 0x08: "comment"}


def blocks(raw: bytes) -> dict[int, bytes]:
    if raw[:16] != MAGIC:
        raise ValueError("not a .qm file (no Qt translation magic)")
    out, pos = {}, 16
    while pos + 5 <= len(raw):
        tag = raw[pos]
        (length,) = struct.unpack_from(">I", raw, pos + 1)
        pos += 5
        if pos + length > len(raw):
            raise ValueError("a .qm block runs past the end of the file")
        out[tag] = raw[pos : pos + length]
        pos += length
    return out


def messages(raw: bytes) -> list[dict]:
    body = blocks(raw).get(MESSAGES, b"")
    out: list[dict] = []
    cur: dict = {}
    i = 0
    while i < len(body):
        sub = body[i]
        i += 1
        if sub == 0x01:
            out.append(cur)
            cur = {}
            continue
        if sub not in SUB:
            break
        (length,) = struct.unpack_from(">I", body, i)
        i += 4
        data = body[i : i + length]
        i += length
        enc = "utf-16-be" if sub == 0x03 else "utf-8"
        cur[SUB[sub]] = data.decode(enc, "replace")
    return out


def to_json(raw: bytes) -> bytes:
    language = blocks(raw).get(LANGUAGE, b"").decode("ascii", "replace")
    out = {"language": language, "messages": messages(raw)}
    return json.dumps(out, ensure_ascii=False, indent=2).encode("utf-8")
