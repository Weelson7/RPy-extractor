"""decode.axml (binary XML to text XML) and decode.arsc (`resources.arsc` to JSON), each with
its way back (doc 18.3). `.xml` is also the suffix of plain text XML (an APK's `assets/`, any
other folder): a file that is not binary XML is left as it is, already readable."""

import json
from pathlib import Path

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from .arsc import read_table
from .arsc_write import write_arsc
from .axml import is_axml, read_axml, to_text
from .axml_write import encode_axml

SLOTS = (
    SlotDefinition("decode.axml", "decode", "android", "axml-builtin", suffixes=(".xml",)),
    SlotDefinition("decode.arsc", "decode", "android", "arsc-builtin", suffixes=(".arsc",)),
)
TEXT_HEADS = (b"<", b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b" ", b"\t", b"\r", b"\n")


def _head(path: Path) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(8)


class AxmlDecoder(Decoder):
    backend_id, owner, license = "axml-builtin", "android", "MIT"
    parses_untrusted_in_process = True  # doc 8.4
    encodes = True  # text XML back to binary XML (axml_write.py)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        head = _head(path)
        if not is_axml(head):
            if head.startswith(TEXT_HEADS) or not head:
                return Outcome(OutcomeKind.OK, 0)  # plain text XML: already readable
            return Outcome(OutcomeKind.OK, 0, notes=("not Android binary XML: left as it is",))
        try:
            doc = read_axml(path.read_bytes())
            text, problems = to_text(doc)
        except (OSError, ValueError, RecursionError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{path.name}: {exc}"[:300])
        (dest / f"{path.stem}.text.xml").write_text(text, encoding="utf-8", newline="\n")
        notes = []
        if problems:
            notes.append(f"{problems} name(s) or character(s) XML cannot carry shown replaced: "
                         "the file goes back only unchanged")  # fmt: skip
        if doc.comments:
            notes.append(f"{doc.comments} node comment(s) not shown (aapt keeps none)")
        if doc.skipped:
            notes.append(f"{doc.skipped} chunk(s) of an unknown kind not shown")
        return Outcome(OutcomeKind.OK, 1, notes=tuple(notes))

    def refuses(self, original: Path) -> str:
        return "" if is_axml(_head(original)) else f"{original.name} is not binary XML"

    def encode(self, edited: Path, original: Path, out: Path, ctx) -> Outcome:
        try:
            out.write_bytes(encode_axml(edited.read_bytes(), original.read_bytes()))
        except (OSError, ValueError, RecursionError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{edited.name}: {exc}"[:300])
        return Outcome(OutcomeKind.OK, 1)


class ArscDecoder(Decoder):
    backend_id, owner, license = "arsc-builtin", "android", "MIT"
    parses_untrusted_in_process = True  # doc 8.4
    encodes = True  # edited values back into the table (arsc_write.py)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        try:
            table = read_table(path.read_bytes())
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{path.name}: {exc}"[:300])
        text = json.dumps(table.data, ensure_ascii=False, indent=1)
        (dest / f"{path.name}.json").write_text(text, encoding="utf-8")
        shown = ", ".join(table.data["not_shown"])
        return Outcome(OutcomeKind.OK, 1, notes=(f"not shown, kept as they are: {shown}",))

    def encode(self, edited: Path, original: Path, out: Path, ctx) -> Outcome:
        try:
            data = json.loads(edited.read_text(encoding="utf-8"))
            table, notes = write_arsc(data, original.read_bytes())
            out.write_bytes(table)
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{edited.name}: {exc}"[:300])
        return Outcome(OutcomeKind.OK, 1, notes=tuple(notes))
