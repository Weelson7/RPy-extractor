"""Sanitizer phases 2 and 3 (doc 5.1): rules whose findings write new files.

Phase 2 (`core.convert`, `core.convert_replace`): a copy in an open format of a workspace file
that a lossless decoder reads (the `decode.*` slot its extension is bound to, the same decoders
an extraction runs). Phase 3 (`core.transcode_audio`, `core.transcode_video`, lossy, opt-in):
a smaller copy through the pinned ffmpeg (`media.encode`), a separate process. A rule writes
into the cache folder core hands it; `commit` moves what it wrote into the workspace as DECODE
does (the extension's group folder, the collision rule, provenance) and returns the entries
undo needs to take the copies away again.
"""

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.sanitizer import RuleContext, SanitizerRule

from . import provenance
from .context import core_context, for_owner
from .decode import _why as why_failed
from .merger.ffmpeg import FFMPEG
from .pipeline.collect import sha256
from .pipeline.failover import run_with_failover
from .steps import tell

AUDIO_IN = (".wav", ".flac", ".aif", ".aiff")
VIDEO_IN = (".avi", ".mkv", ".mov", ".wmv", ".mpg", ".mpeg", ".m2v", ".ogv", ".webm", ".flv")
VIDEO_IN += (".bik",)  # Bink 1: ffmpeg reads it
PRESETS = {  # rule id -> (inputs, output suffix, ffmpeg arguments, what it makes)
    "core.transcode_audio": (
        AUDIO_IN,
        ".ogg",
        ["-vn", "-c:a", "libopus", "-b:a", "128k"],
        "Opus 128 kb/s in Ogg",
    ),
    "core.transcode_video": (
        VIDEO_IN,
        ".mp4",
        ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p"]
        + ["-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"],
        "H.264 / AAC MP4",
    ),
}


def lossless_slots(rt) -> dict[str, tuple[str, str]]:
    """suffix -> (decode slot, its owner) for each bound slot whose main decoder is lossless."""
    out: dict[str, tuple[str, str]] = {}
    for sid, slot in sorted(rt.slots.items()):
        binding = rt.bindings.get(sid)
        if slot.family != "decode" or binding is None or not binding.bound:
            continue
        if getattr(rt.backends.get(binding.main), "lossless", False):
            out.update(dict.fromkeys(slot.suffixes, (sid, slot.owner)))
    return out


@dataclass
class Known:
    """What a workspace says about itself: the files a decoder already read (their copies
    exist), and the plugins its run records name (None: no record names one)."""

    decoded: set[str] = field(default_factory=set)
    names: set[str] = field(default_factory=set)  # a batch decoder's origin names its slot
    owners: set[str] | None = None

    @classmethod
    def of(cls, workspace: Path) -> "Known":
        known = cls()
        for entry in provenance.entries(workspace):
            origin = str(entry.get("origin", ""))
            if origin.startswith("decode:"):
                rest = origin.removeprefix("decode:").partition(":")[2]
                source, _, out = rest.rpartition(":")
                known.decoded.add(source)
                name = Path(out).name.lower() if source.startswith("decode.") else ""
                while "." in name:  # a batch's `0001.xbm.png` was read from `0001.xbm`
                    name = name.rsplit(".", 1)[0]
                    known.names.add(name)
        owners: set[str] = set()
        for record in sorted((workspace / ws.RUNS_DIR).glob("*.json")):
            try:
                runs = json.loads(record.read_text(encoding="utf-8"))["result"]["plugins"]
                owners |= {str(run["id"]) for run in runs}
            except (OSError, ValueError, KeyError, TypeError):
                continue  # a damaged record tells nothing
        known.owners = owners or None
        return known


class Convert(SanitizerRule):
    """core.convert: an open-format copy beside the original. core.convert_replace: the same,
    then the original goes to the workspace trash (both journaled: undo brings it back)."""

    category, cost, default_enabled = "normalize", 5, False

    def __init__(self, rt, replace: bool = False) -> None:
        self.rt, self.replace = rt, replace
        self.rule_id = "core.convert_replace" if replace else "core.convert"
        self.slots = lossless_slots(rt)
        self.known: tuple[RuleContext, Known] | None = None  # read once per plan

    def unready(self) -> str:
        return "" if self.slots else "no lossless decode.* slot is bound"

    def applies_to(self, path: Path) -> bool:
        return path.suffix.lower() in self.slots

    def inspect(self, path: Path, ctx: RuleContext) -> list[dict]:
        if self.known is None or self.known[0] is not ctx:
            self.known = (ctx, Known.of(ctx.workspace))
        known, (slot, owner) = self.known[1], self.slots[path.suffix.lower()]
        rel = path.relative_to(ctx.workspace).as_posix()
        if owner != "core" and known.owners is not None and owner not in known.owners:
            return []  # another engine's decoder: a `.json` of a Unity game is no CR2W file
        if rel in known.decoded or path.name.lower() in known.names or not path.stat().st_size:
            return []
        backend = self.rt.bindings[slot].main
        what = f"{path.suffix[1:].upper()} to an open format by {slot} ({backend}), lossless"
        then = "; the original goes to the workspace trash" if self.replace else ""
        action = "replace" if self.replace else "convert"
        return [ctx.finding(self.rule_id, path, what + then, action, slot=slot, severity="info")]

    def fix(self, finding: dict, ctx: RuleContext) -> str:
        slot, src = finding["slot"], ctx.workspace.joinpath(*Path(finding["path"]).parts)
        binding = self.rt.bindings.get(slot)
        if binding is None or not binding.bound:
            raise OSError(f"{slot} is not bound now")
        work = ctx.cache.parent / f"{ctx.cache.name}-work"
        base = core_context(self.rt, "cleanup", ctx.workspace, work, ctx.sink, ctx.cancel)
        dctx = for_owner(base, self.rt, self.rt.slots[slot].owner, {})
        call = lambda b: b.decode(src, ctx.cache, dctx)  # noqa: E731
        outcome, used = run_with_failover(
            binding, self.rt.backends, call, into=ctx.cache, cancel=dctx.cancel
        )
        if not outcome.ok:  # the spare's reason, and the main's when the spare stood in
            more = f" ({' '.join(outcome.fallback.split())})" if outcome.fallback else ""
            raise OSError(f"{used or slot}: {why_failed(outcome)}{more}")
        for note in [outcome.fallback, *outcome.notes]:
            if note:  # never silent: a spare that stood in, what the copy does not show
                tell(ctx.sink, f"{finding['path']}: {note}", "apply", "warn")
        return f"decode:{used}:{finding['path']}"


class Transcode(SanitizerRule):
    """Phase 3, lossy, opt-in: a copy through the pinned ffmpeg (PRESETS); the original stays."""

    category, cost, default_enabled, lossy = "transcode", 10, False, True

    def __init__(self, rt, rule_id: str) -> None:
        self.rt, self.rule_id = rt, rule_id
        self.inputs, self.suffix, self.args, self.label = PRESETS[rule_id]
        self.why: tuple[RuleContext, str] | None = None  # unready(), looked up once per plan

    def unready(self) -> str:
        binding = self.rt.bindings.get("media.encode")
        if binding is None or not binding.bound or self.rt.os.tools.locate(FFMPEG) is None:
            return f"{self.rule_id}: ffmpeg (media.encode) is not bound: {FFMPEG.hint}"
        return ""

    def applies_to(self, path: Path) -> bool:
        return path.suffix.lower() in self.inputs

    def inspect(self, path: Path, ctx: RuleContext) -> list[dict]:
        if self.why is None or self.why[0] is not ctx:
            self.why = (ctx, self.unready())
        if not path.stat().st_size or self.why[1]:
            return []
        what = f"{path.suffix[1:].upper()} to {self.label}: LOSSY, the original stays"
        return [ctx.finding(self.rule_id, path, what, "transcode", lossy=True, severity="info")]

    def fix(self, finding: dict, ctx: RuleContext) -> str:
        tool = self.rt.os.tools.locate(FFMPEG)
        if tool is None:
            raise OSError(FFMPEG.hint)
        src = ctx.workspace.joinpath(*Path(finding["path"]).parts)
        out = ctx.cache / f"{src.stem}{self.suffix}"
        argv = [*tool.argv_prefix, "-y", "-loglevel", "error", "-i", str(src), *self.args]
        result = self.rt.os.process.run([*argv, str(out)], timeout=6 * 3600, cancel=ctx.cancel)
        if not result.ok or not out.is_file():
            lines = (result.stderr or result.stdout or "ffmpeg failed").strip().splitlines()
            raise OSError(f"ffmpeg: {(lines or ['failed'])[-1][-200:]}")
        return f"transcode:ffmpeg:{finding['path']}"


def phase_rules(rt) -> list[SanitizerRule]:
    return [Convert(rt), Convert(rt, replace=True), *(Transcode(rt, rid) for rid in PRESETS)]


def commit(workspace: Path, cache: Path, origin: str, made: list[dict]) -> None:
    """Move every file `fix` wrote into the workspace as DECODE does (the extension's group
    folder, the collision rule) with its provenance entry; each lands in `made` as it moves,
    so a failure half-way leaves the moved ones undoable."""
    entries = []
    for file in sorted(p for p in cache.rglob("*") if p.is_file()):
        member = file.relative_to(cache).as_posix()
        folder = workspace / ws.ext_folder(ws.ext_of(file))
        folder.mkdir(parents=True, exist_ok=True)
        target = ws.next_free(folder / file.name)
        shutil.move(str(file), str(target))
        rel, digest = target.relative_to(workspace).as_posix(), sha256(target)
        made.append({"made": rel, "sha256": digest})
        entries.append(
            {"path": rel, "origin": f"{origin}:{member}", "sha256": digest}
            | {"size": target.stat().st_size, "kind": "derived", "container": "", "member": member}
        )
    provenance.add(workspace, entries)
