"""A minimal, first-party interpreter for Kaitai Struct `.ksy` definitions (doc 13.2), stdlib
only: no PyYAML (a tiny YAML subset reader below) and never the GPL kaitai-struct-compiler. It
reads the subset the bundled definitions need and parses bytes into a structured tree:

- `meta`: `id`, `endian` (`le`/`be`, the default for sized integers).
- `seq`: ordered fields, each `id` plus one of `type` (`u1`-`u8`, `s1`-`s8`, with an optional
  `le`/`be` suffix, or a user type named in `types`), `size` (an int or an expression over the
  sibling fields already read), or `contents` (expected magic bytes, a string or a byte list).
- `repeat: expr` with `repeat-expr` (a count) and `repeat: eos` (until the stream ends).
- `enum`: a field's integer mapped through a table in `enums` to its name.
- `types`: named sub-structures; `enums`: name -> {value: label}.

Anything outside this subset raises, so a definition ViWo cannot interpret fails by name rather
than parsing wrongly."""

import ast
import re

INTS = {f"{s}{n}": (n, s == "s") for s in ("u", "s") for n in (1, 2, 4, 8)}


def _scalar(text: str):
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_scalar(part.strip()) for part in inner.split(",")] if inner else []
    if re.fullmatch(r"0x[0-9a-fA-F]+", text):
        return int(text, 16)
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def _lines(text: str) -> list[tuple[int, str]]:
    out = []
    for raw in text.splitlines():
        body = raw.split("#", 1)[0] if "#" in raw and '"' not in raw and "'" not in raw else raw
        if body.strip():
            out.append((len(body) - len(body.lstrip(" ")), body.strip()))
    return out


def _parse_block(lines: list, i: int):
    return _parse_seq(lines, i) if lines[i][1].startswith("- ") else _parse_map(lines, i)


def _parse_map(lines: list, i: int):
    indent, result = lines[i][0], {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("- "):
        key, _, rest = lines[i][1].partition(":")
        rest = rest.strip()
        if rest:
            result[key.strip()], i = _scalar(rest), i + 1
        elif i + 1 < len(lines) and lines[i + 1][0] > indent:
            result[key.strip()], i = _parse_block(lines, i + 1)
        else:
            result[key.strip()], i = None, i + 1
    return result, i


def _parse_seq(lines: list, i: int):
    indent, result = lines[i][0], []
    while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("- "):
        inner_indent, inner = indent + 2, lines[i][1][2:]
        if ":" in inner:
            item = [(inner_indent, inner)]
            i += 1
            while i < len(lines) and lines[i][0] >= inner_indent:
                item.append(lines[i])
                i += 1
            value, _ = _parse_map(item, 0)
            result.append(value)
        else:
            result.append(_scalar(inner))
            i += 1
    return result, i


def load_ksy(text: str) -> dict:
    """The `.ksy` YAML (the subset above) as nested dicts and lists."""
    lines = _lines(text)
    if not lines:
        raise ValueError("empty .ksy definition")
    value, _ = _parse_block(lines, 0)
    return value


class Stream:
    def __init__(self, data: bytes) -> None:
        self.data, self.pos = data, 0

    def read(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError("the .ksy structure runs past the end of the data")
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def eof(self) -> bool:
        return self.pos >= len(self.data)


def _size(spec, scope: dict) -> int:
    if isinstance(spec, int):
        return spec
    return int(_eval(ast.parse(str(spec), mode="eval").body, scope))


def _eval(node, scope: dict) -> int:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return scope[node.id]
    if isinstance(node, ast.BinOp):
        ops = {ast.Add: int.__add__, ast.Sub: int.__sub__, ast.Mult: int.__mul__}
        return ops[type(node.op)](_eval(node.left, scope), _eval(node.right, scope))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand, scope)
    raise ValueError("unsupported expression in the .ksy definition")


def _contents(spec) -> bytes:
    if isinstance(spec, str):
        return spec.encode("latin-1")
    return bytes(ord(x) if isinstance(x, str) else x for x in spec)


def _one(field: dict, ksy: dict, endian: str, stream: Stream, scope: dict):
    if "contents" in field:
        want = _contents(field["contents"])
        got = stream.read(len(want))
        if got != want:
            raise ValueError(f"{field.get('id')}: expected {want!r}, found {got!r}")
        return got.decode("latin-1")
    kind = field.get("type")
    if kind in INTS or (kind and kind[:-2] in INTS and kind[-2:] in ("le", "be")):
        return _int(kind, endian, stream, ksy.get("enums", {}).get(field.get("enum")))
    if kind in ksy.get("types", {}):
        return _struct(ksy["types"][kind], ksy, endian, stream)
    if "size" in field:
        return stream.read(_size(field["size"], scope)).hex()
    raise ValueError(f"{field.get('id')}: no type, size or contents ViWo can read")


def _int(kind: str, endian: str, stream: Stream, enum):
    base = kind[:-2] if kind not in INTS else kind
    width, signed = INTS[base]
    order = "little" if (kind[-2:] if kind not in INTS else endian) in ("le", "little") else "big"
    value = int.from_bytes(stream.read(width), order, signed=signed)
    if enum is not None:
        return {"value": value, "enum": enum.get(int(value)) or enum.get(str(value))}
    return value


def _struct(node: dict, ksy: dict, endian: str, stream: Stream) -> dict:
    scope: dict = {}
    for field in node.get("seq", []):
        name = field.get("id")
        if field.get("repeat") == "eos":
            items = []
            while not stream.eof():
                items.append(_one(field, ksy, endian, stream, scope))
            scope[name] = items
        elif field.get("repeat") == "expr":
            count = _size(field["repeat-expr"], scope)
            scope[name] = [_one(field, ksy, endian, stream, scope) for _ in range(count)]
        else:
            scope[name] = _one(field, ksy, endian, stream, scope)
    return scope


def parse(ksy: dict, data: bytes) -> dict:
    """The structured tree of `data` under `ksy` (a loaded definition); ValueError when the data
    does not match (a bad magic, a short read, an unreadable construct)."""
    endian = (ksy.get("meta") or {}).get("endian", "le")
    return _struct(ksy, ksy, endian, Stream(data))
