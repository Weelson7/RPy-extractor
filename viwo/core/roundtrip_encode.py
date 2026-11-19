"""The way back for decoded files (doc 18.3): an edited file DECODE wrote (a PNG, a WAV, a
glTF, a text table) is encoded back into the format of the member it was decoded from, by the
decoder that read it (`Decoder.encode`); that member then goes through PLAN, PACK and VERIFY as
any other edit. A file whose decoder has no way back is named with the decoder's reason."""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from viwo.contracts import workspace as ws

from .pipeline.collect import sha256
from .provenance import entries
from .roundtrip_edits import Edit


@dataclass
class Way:
    slot: str  # the decode.* slot that read the member
    backend: str  # the backend that writes it back
    source: Path  # the workspace file decode read: the member as extracted
    derived: str  # the edited decoded file (workspace path)
    drop: str = ""  # the member the encoded one replaces (a .rpyc for its .rpy), removed

    def shown(self, member: str) -> dict:
        out = {
            "file": self.derived,
            "member": member,
            "encoder": self.slot,
            "backend": self.backend,
        }
        return out | ({"replaces": self.drop} if self.drop else {})


def origin_parts(origin: str) -> tuple[str, str, str]:
    """`decode:<backend>:<source or slot>:<file in the decoder's output>` -> the three parts."""
    backend, _, rest = origin.removeprefix("decode:").partition(":")
    source, _, out = rest.rpartition(":")
    return backend, source, out


class _Index:
    """The provenance map by path and by file name (a file SORT moved keeps its name)."""

    def __init__(self, workspace: Path) -> None:
        self.by_path, self.by_name = defaultdict(list), defaultdict(list)
        for entry in entries(workspace):
            if not str(entry.get("origin", "")).startswith("decode:"):
                self.by_path[entry["path"]].append(entry)
                self.by_name[Path(entry["path"]).name.lower()].append(entry)

    def sources(self, rt, used: str, source: str, out: str) -> tuple[str, list[dict]]:
        """(decode slot, provenance entries of the file it read). A batch decoder's origin
        names its slot: the file is the one whose name starts the output's
        (`0000000000001234.xbm` for `0000000000001234.xbm.png`)."""
        slot = rt.slots.get(source)
        if slot is not None and slot.family == "decode":
            name = Path(out).name.lower()
            while "." in name:
                name = name.rsplit(".", 1)[0]
                if name in self.by_name and Path(name).suffix in slot.suffixes:
                    return source, self.by_name[name]
            return source, []
        found = self.by_path.get(source) or self.by_name.get(Path(source).name.lower(), [])
        suffix = Path(source).suffix.lower()
        slots = [s for s in rt.slots.values() if s.family == "decode" and suffix in s.suffixes]
        mine = [s for s in slots if used in _bound(rt, s.slot_id)]
        return next((s.slot_id for s in mine or slots), ""), found


def _bound(rt, slot: str) -> tuple[str, ...]:
    binding = rt.bindings.get(slot)
    return (binding.main, binding.spare) if binding else ()


def _encoder(rt, slot: str, used: str):
    """The backend that writes the member back: the one that decoded it, else one bound in its
    slot that encodes; (backend or None, the reason when none)."""
    found = [rt.backends[n] for n in (used, *_bound(rt, slot)) if n in rt.backends]
    for backend in found:
        if backend.encodes:
            return backend, ""
    return None, found[0].one_way if found else f"{slot} is not bound"


def ways_back(rt, workspace: Path, decoded: list) -> tuple[list[Edit], list[str]]:
    """The edits that edited decoded files become, and those that cannot go back, each with
    its reason (never silent)."""
    index, edits, skipped, seen = _Index(workspace), [], [], {}
    for entry, file in decoded:
        backend, source, out = origin_parts(str(entry.get("origin", "")))
        slot, every = index.sources(rt, backend, source, out)
        found = [e for e in every if e.get("kind") in ("member", "loose", "exported")]
        why = _blocked(workspace, slot, (every, found), seen)
        encoder, one_way = _encoder(rt, slot, backend) if not why else (None, "")
        if encoder is not None:
            rel = ws.safe_member(found[0]["path"])
            why = _refusal(encoder, workspace.joinpath(*rel.parts))
        if why or encoder is None:
            skipped.append(f"{entry['path']}: {why or f'{slot} is one way: {one_way}'}")
            continue
        seen[found[0]["path"]] = entry["path"]
        for target in found:  # every container that held the same member
            rel = ws.safe_member(target["path"])
            way = Way(slot, encoder.backend_id, workspace.joinpath(*rel.parts), entry["path"])
            member = encoder.member_back(target.get("member", ""))
            way.drop = target.get("member", "") if member != target.get("member", "") else ""
            kind, container = target["kind"], target.get("container", "")
            edits.append(Edit(file, kind, container, member, target.get("plugin", ""), way))
    return edits, skipped


def _blocked(workspace: Path, slot: str, sources: tuple, seen: dict) -> str:
    """Why an edited decoded file cannot go back, "" when it can. sources: (every provenance
    entry of the file it was decoded from, those a packer can write back)."""
    every, found = sources
    if not slot:
        return "no decoder known for the file it came from"
    if every and not found:
        where = f"{every[0]['path']}, the file it was decoded from,"
        return f"{where} came out of a nested container or a wrapper: no way back into it yet"
    if not found:
        return "the file it was decoded from is no longer in the workspace (moved or trashed)"
    first = found[0]["path"]
    if first in seen:
        return f"{seen[first]} goes back into the same member ({first}); edit one of them"
    rel = ws.safe_member(first)
    source = workspace.joinpath(*rel.parts) if rel else None
    if source is None or not source.is_file():
        return f"{first}, the file it was decoded from, is missing"
    if sha256(source) != found[0]["sha256"]:
        return f"{first}, the file it was decoded from, was edited too: that edit is used"
    return ""


def _refusal(encoder, source: Path) -> str:
    try:
        return encoder.refuses(source)
    except Exception as exc:  # noqa: BLE001 (a look that crashes: said, the file skipped)
        return f"{source.name} could not be read: {exc}"[:300]


def encode_all(rt, items: list, work: Path, ctx) -> list[dict]:
    """Encode every planned decoded edit into `work`; each item then carries the encoded file
    (what VERIFY compares the packed member with). A failure leaves the item and is returned
    as a result of its own."""
    failed = []
    for n, item in enumerate(items):
        for i, (member, way) in enumerate(sorted(item.ways.items())):
            out = work / "encoded" / f"{n}-{i}" / Path(member).name
            out.parent.mkdir(parents=True, exist_ok=True)
            ctx.log(f"Encoding {way.derived} -> {member} ({way.slot})", stage="repack")
            error = _encode_one(rt.backends[way.backend], item.members[member], way, out, ctx)
            if not error:
                item.members[member] = out
                continue
            del item.members[member]
            ctx.log(f"{way.derived}: not encoded: {error}", "warn", "repack")
            head = {"container": item.container, "slot": way.slot, "backend": way.backend}
            failed.append({**head, "members": 1, "failed": [member], "error": error})
    return failed


def _encode_one(backend, edited: Path, way: Way, out: Path, ctx) -> str:
    try:
        outcome = backend.encode(edited, way.source, out, ctx)
    except Exception as exc:  # noqa: BLE001 (an encoder's crash is this file's failure)
        return f"{type(exc).__name__}: {exc}"[:300]
    if outcome.ok and out.is_file():
        return ""
    return outcome.error or f"{way.backend} wrote nothing"
