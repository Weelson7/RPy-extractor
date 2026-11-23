"""Android binary XML (AXML: `AndroidManifest.xml` and `res/**/*.xml` in an APK) read into a
tree and written out as readable text XML. The format is chunked: a string pool, the resource
ids of the attribute names, then namespace, element and text nodes, each attribute a typed value
(values.py). Every read is bounds-checked; anything damaged is a ValueError, never a crash."""

import re
import struct
from dataclasses import dataclass, field

from .strpool import Pool, chunk_head, read_pool
from .values import STRING, render

MAGIC = b"\x03\x00\x08\x00"
RES_MAP, NS_START, NS_END, START, END, CDATA = 0x0180, 0x0100, 0x0101, 0x0102, 0x0103, 0x0104
NONE = 0xFFFFFFFF
ANDROID = "http://schemas.android.com/apk/res/android"
MAX_DEPTH = 256
NAME = re.compile(r"[^\W\d][\w.\-]*")
BAD = re.compile("[^\t\n\r\x20-퟿-�\U00010000-\U0010ffff]")


@dataclass
class Attr:
    ns: str | None
    name: str
    rid: int | None  # the attribute name's resource id (resource map), when it has one
    raw: str | None
    code: int
    data: int


@dataclass
class Element:
    ns: str | None
    name: str
    line: int
    attrs: list[Attr] = field(default_factory=list)
    spaces: list[tuple[str, str]] = field(default_factory=list)  # (prefix, uri) declared here
    children: list = field(default_factory=list)  # Element or str (a text node)


@dataclass
class Doc:
    pool: Pool
    ids: list[int]
    root: Element | None
    comments: int = 0
    skipped: int = 0  # chunks of a kind not known, left out of the text


def is_axml(head: bytes) -> bool:
    return head[:4] == MAGIC


def _attrs(raw: bytes, at: int, count: int, step: int, doc: Doc) -> list[Attr]:
    out = []
    for n in range(count):
        ns, name, value, _, _, code, data = struct.unpack_from("<IIIHBBI", raw, at + n * step)
        rid = doc.ids[name] if name < len(doc.ids) else None
        text = doc.pool.get(value)
        out.append(Attr(doc.pool.get(ns), doc.pool.get(name) or "", rid, text, code, data))
    return out


def _element(raw: bytes, ext: int, line: int, doc: Doc) -> Element:
    ns, name, start, step, count = struct.unpack_from("<IIHHH", raw, ext)
    if step < 20:
        raise ValueError(f"line {line}: attribute records of {step} bytes")
    element = Element(doc.pool.get(ns), doc.pool.get(name) or "", line)
    element.attrs = _attrs(raw, ext + start, count, step, doc)
    return element


def _node(raw: bytes, at: int, head: int, kind: int, state: tuple) -> None:
    doc, stack, spaces = state
    line, comment = struct.unpack_from("<II", raw, at + 8)
    doc.comments += comment != NONE
    ext = at + head
    if kind == NS_START:
        prefix, uri = struct.unpack_from("<II", raw, ext)
        spaces.append((doc.pool.get(prefix) or "", doc.pool.get(uri) or ""))
    elif kind == START:
        element = _element(raw, ext, line, doc)
        element.spaces, spaces[:] = list(spaces), []
        if len(stack) >= MAX_DEPTH or (doc.root is not None and not stack):
            raise ValueError(f"line {line}: nesting too deep or a second root element")
        if stack:
            stack[-1].children.append(element)
        else:
            doc.root = element
        stack.append(element)
    elif kind == END:
        if not stack:
            raise ValueError(f"line {line}: an end tag with no element open")
        stack.pop()
    elif kind == CDATA and stack:
        (index,) = struct.unpack_from("<I", raw, ext)
        stack[-1].children.append(doc.pool.get(index) or "")
    elif kind == CDATA:  # text outside the root element: XML has no place for it
        doc.skipped += 1


def read_axml(raw: bytes) -> Doc:
    """The whole document; ValueError on anything that is not a whole binary XML file."""
    try:
        return _read(raw)
    except (struct.error, IndexError, UnicodeDecodeError) as exc:
        raise ValueError(f"damaged binary XML: {exc}") from None


def _read(raw: bytes) -> Doc:
    if not is_axml(raw):
        raise ValueError("not Android binary XML (no 0x0003 header)")
    _, _, total = chunk_head(raw, 0, len(raw))
    doc, stack, spaces, at = None, [], [], 8
    while at < total:
        kind, head, size = chunk_head(raw, at, total)
        if kind == 0x0001 and doc is None:
            doc = Doc(read_pool(raw, at, total), [], None)
        elif doc is None:
            raise ValueError("the string pool does not come first")
        elif kind == RES_MAP:
            doc.ids = list(struct.unpack_from(f"<{(size - head) // 4}I", raw, at + head))
        elif kind in (NS_START, NS_END, START, END, CDATA):
            _node(raw, at, head, kind, (doc, stack, spaces))
        else:
            doc.skipped += 1
        at += size
    if doc is None or doc.root is None or stack:
        raise ValueError("no root element, or an element left open")
    return doc


def value_text(attr: Attr) -> str:
    if attr.code == STRING:
        return attr.raw if attr.raw is not None else ""
    return render(attr.code, attr.data)


class _Writer:
    """The tree as text XML; problems counts names and characters XML cannot carry."""

    def __init__(self) -> None:
        self.lines, self.problems, self.prefixes = [], 0, [{"": ""}]
        self.undeclared: list[tuple[str, str]] = []
        self.flat = False

    def text(self, value: str, attr: bool = False) -> str:
        if BAD.search(value):
            self.problems += 1
            value = BAD.sub("�", value)
        value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        value = value.replace("\r", "&#13;")
        if attr:
            value = value.replace('"', "&quot;").replace("\n", "&#10;").replace("\t", "&#9;")
        return value

    def name(self, ns: str | None, name: str) -> str:
        if not NAME.fullmatch(name):
            self.problems += 1
            name = f"_bad{self.problems}"
        prefix = self.prefixes[-1].get(ns or "")
        if prefix is None:  # a namespace never declared: given a prefix of its own
            prefix = f"ns{len(self.prefixes[-1])}"
            self.prefixes[-1][ns or ""] = prefix
            self.undeclared.append((prefix, ns or ""))
        return f"{prefix}:{name}" if prefix else name

    def open_tag(self, el: Element) -> str:
        self.prefixes.append({**self.prefixes[-1], **{uri: p for p, uri in el.spaces}})
        self.undeclared, seen, attrs = [], set(), []
        tag = self.name(el.ns, el.name)
        for attr in el.attrs:
            name = self.name(attr.ns, attr.name)
            if name in seen:  # twice on one element: XML cannot hold it
                self.problems += 1
                name = f"_bad{self.problems}"
            seen.add(name)
            attrs.append(f'{name}="{self.text(value_text(attr), True)}"')
        spaces = el.spaces + self.undeclared
        decl = [f'xmlns{":" if p else ""}{p}="{self.text(u, True)}"' for p, u in spaces]
        return " ".join([tag, *decl, *attrs])

    def element(self, el: Element, depth: int) -> None:
        pad = "" if self.flat else "    " * depth
        head = self.open_tag(el)
        tag = head.split(" ", 1)[0]
        if not el.children:
            self.lines.append(f"{pad}<{head}/>")
        elif any(isinstance(c, str) for c in el.children):  # mixed content: one line, as is
            self.lines.append(f"{pad}<{head}>{self.inline(el.children)}</{tag}>")
        else:
            self.lines.append(f"{pad}<{head}>")
            for child in el.children:
                self.element(child, depth + 1)
            self.lines.append(f"{pad}</{tag}>")
        self.prefixes.pop()

    def inline(self, children: list) -> str:
        out = []
        for child in children:
            if isinstance(child, str):
                out.append(self.text(child))
                continue
            kept, flat = self.lines, self.flat
            self.lines, self.flat = [], True  # no indentation inside text: it would be text
            self.element(child, 0)
            out.append("".join(self.lines))
            self.lines, self.flat = kept, flat
        return "".join(out)


def to_text(doc: Doc) -> tuple[str, int]:
    """(the document as text XML, how many names or characters XML cannot carry were
    replaced: such a file goes back only unchanged)."""
    writer = _Writer()
    writer.element(doc.root, 0)
    body = "\n".join(writer.lines)
    return f'<?xml version="1.0" encoding="utf-8"?>\n{body}\n', writer.problems
