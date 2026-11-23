"""The way back of decode.axml: edited text XML to Android binary XML, laid out as aapt2 lays it
out (the string pool with the attribute names that have resource ids first, the resource map,
then the nodes; each element's attributes sorted as aapt2 sorts them). The original file is the
reference: an unchanged text gives the original bytes back; each attribute name's resource id
and value type come from it, so `android:versionName="1"` stays a string where the original had
one. A namespaced attribute the original never used is refused by name: its resource id lives
in the framework, which ViWo does not read. Comments in the original's nodes are not kept."""

import struct
import xml.parsers.expat

from .axml import (
    ANDROID,
    CDATA,
    END,
    NONE,
    NS_END,
    NS_START,
    RES_MAP,
    START,
    Doc,
    read_axml,
    to_text,
    value_text,
)
from .strpool import write_pool
from .values import STRING, guess, parse, type_name


class Oracle:
    """What the original says: per (namespace, name) its resource id and every value type the
    file gave it; per (element's place in document order, its name, the attribute, the text
    decode showed) the typed value it was, reused as it was where that text is unchanged."""

    def __init__(self, doc: Doc) -> None:
        self.ids, self.types, self.values = {}, {}, {}
        todo, n = [doc.root], 0
        while todo:
            element = todo.pop()
            todo += reversed([c for c in element.children if not isinstance(c, str)])
            for attr in element.attrs:
                key = (attr.ns or "", attr.name)
                self.ids.setdefault(key, attr.rid)
                self.types.setdefault(key, set()).add(attr.code)
                self.values[(n, element.name, key, value_text(attr))] = (attr.code, attr.data)
            n += 1

    def typed(self, where: tuple, key: tuple, text: str, line: int) -> tuple[int, int, bool]:
        """(type, data, is a string) of one attribute value: as it was where unchanged, else by
        the types the original gave that attribute, else by its text."""
        found = self.values.get((*where, key, text))
        if found is not None:
            return found[0], found[1], found[0] == STRING
        known = self.types.get(key, set())
        for code in sorted(known - {STRING}):
            try:
                return code, parse(code, text), False
            except ValueError:
                continue
        if STRING in known or not known:
            code, data = guess(text) if not known else (STRING, 0)
            return code, data, code == STRING
        names = ", ".join(type_name(c) for c in sorted(known))
        raise ValueError(f"line {line}: {key[1]}={text!r} is not a {names} as in the original")


def _events(text: bytes) -> list[tuple]:
    """The edited document as events, in order, with their line numbers (expat)."""
    events, open_spaces = [], []
    parser = xml.parsers.expat.ParserCreate(namespace_separator=" ")
    parser.buffer_text, parser.ordered_attributes = True, True
    line = lambda: parser.CurrentLineNumber  # noqa: E731

    def start_ns(prefix, uri):
        open_spaces.append((prefix or "", uri or ""))
        events.append(("ns", prefix or "", uri or "", line()))

    def end_ns(prefix):
        uri = next(u for p, u in reversed(open_spaces) if p == (prefix or ""))
        events.append(("nsend", prefix or "", uri, line()))

    parser.StartNamespaceDeclHandler, parser.EndNamespaceDeclHandler = start_ns, end_ns
    parser.StartElementHandler = lambda name, attrs: events.append(("start", name, attrs, line()))
    parser.EndElementHandler = lambda name: events.append(("end", name, line()))
    parser.CharacterDataHandler = lambda data: events.append(("text", data, line()))
    try:
        parser.Parse(text, True)
    except xml.parsers.expat.ExpatError as exc:
        raise ValueError(f"the edited XML does not parse: {exc}") from None
    return events


def _split(name: str) -> tuple[str, str]:
    uri, _, local = name.rpartition(" ")
    return uri, local


class _Strings:
    """The pool being built: attribute names with resource ids first (each its own entry, so a
    plain attribute of the same name never picks up the id), then every other string."""

    def __init__(self, named: dict) -> None:
        self.named = sorted(named.items(), key=lambda item: item[1])  # (key, rid) by rid
        self.index = {key: n for n, (key, _) in enumerate(self.named)}
        self.plain: dict[str, int] = {}

    def ref(self, text: str | None) -> int:
        if text is None:
            return NONE
        return self.plain.setdefault(text, len(self.named) + len(self.plain))

    def name_ref(self, key: tuple[str, str]) -> int:
        return self.index[key] if key in self.index else self.ref(key[1])

    def chunk(self, utf8: bool) -> bytes:
        strings = [key[1] for key, _ in self.named] + list(self.plain)
        ids = [rid for _, rid in self.named]
        resmap = struct.pack(f"<HHI{len(ids)}I", RES_MAP, 8, 8 + 4 * len(ids), *ids)
        return write_pool(strings, utf8) + resmap


def _sort_key(attr: tuple) -> tuple:
    """aapt2's order: attributes with a resource id by id, then the rest by namespace, name."""
    key, rid = attr[0], attr[1]
    return (0, rid, "", "") if rid is not None else (1, 0, key[0], key[1])


def _attrs(event: tuple, oracle: Oracle, n: int) -> list[tuple]:
    _, tag, pairs, line = event
    where, out = (n, _split(tag)[1]), []
    for name, text in zip(pairs[::2], pairs[1::2]):
        key = _split(name)
        if key not in oracle.ids and key[0]:
            raise ValueError(
                f"line {line}: {key[1]} in {key[0]} is new to this file and its resource id "
                "is not known (only attributes the original uses can be added)"
            )
        code, data, is_string = oracle.typed(where, key, text, line)
        out.append((key, oracle.ids.get(key), text, code, data, is_string))
    return sorted(out, key=_sort_key)


def _start(event: tuple, oracle: Oracle, pool: _Strings, n: int) -> bytes:
    uri, local = _split(event[1])
    attrs = _attrs(event, oracle, n)
    special = {"id": 0, "class": 0, "style": 0}
    body = b""
    for n, (key, rid, text, code, data, is_string) in enumerate(attrs, 1):
        if key[1] in special and (not key[0] or (key[1] == "id" and key[0] == ANDROID)):
            special[key[1]] = special[key[1]] or n
        raw = pool.ref(text) if is_string else NONE
        data = raw if is_string else data
        ns = pool.ref(key[0]) if key[0] else NONE
        body += struct.pack("<IIIHBBI", ns, pool.name_ref(key), raw, 8, 0, code, data)
    head = (pool.ref(uri) if uri else NONE, pool.ref(local), 20, 20, len(attrs))
    return struct.pack("<IIHHHHHH", *head, *special.values()) + body


def _node(kind: int, line: int, ext: bytes) -> bytes:
    return struct.pack("<HHIII", kind, 16, 16 + len(ext), line, NONE) + ext


def _nodes(events: list, oracle: Oracle, pool: _Strings) -> bytes:
    out, starts = [], 0
    for event in events:
        kind, line = event[0], event[-1]
        if kind in ("ns", "nsend"):
            ext = struct.pack("<II", pool.ref(event[1]), pool.ref(event[2]))
            out.append(_node(NS_START if kind == "ns" else NS_END, line, ext))
        elif kind == "start":
            out.append(_node(START, line, _start(event, oracle, pool, starts)))
            starts += 1
        elif kind == "end":
            uri, local = _split(event[1])
            ext = struct.pack("<II", pool.ref(uri) if uri else NONE, pool.ref(local))
            out.append(_node(END, line, ext))
        elif event[1].strip():  # whitespace between elements is layout, not content
            ext = struct.pack("<IHBBI", pool.ref(event[1]), 8, 0, 0, 0)
            out.append(_node(CDATA, line, ext))
    return b"".join(out)


def encode_axml(text: bytes, original: bytes) -> bytes:
    """The binary XML of an edited text; ValueError naming what cannot go back."""
    doc = read_axml(original)
    shown, problems = to_text(doc)
    if text.lstrip(b"\xef\xbb\xbf").replace(b"\r\n", b"\n") == shown.encode("utf-8"):
        return original  # unchanged: the original bytes, not a rebuild
    if problems:
        raise ValueError(
            f"the original holds {problems} name(s) or character(s) XML cannot carry "
            "(shown replaced): this file goes back only unchanged"
        )
    oracle, events = Oracle(doc), _events(text)
    keys = [k for e in events if e[0] == "start" for k in _keys(e)]
    pool = _Strings({k: oracle.ids[k] for k in keys if oracle.ids.get(k) is not None})
    nodes = _nodes(events, oracle, pool)
    body = pool.chunk(doc.pool.utf8) + nodes
    return struct.pack("<HHI", 0x0003, 8, 8 + len(body)) + body


def _keys(event: tuple) -> list[tuple[str, str]]:
    return [_split(name) for name in event[2][::2]]
