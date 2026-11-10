"""decode.cr2w (doc 16.0c): Cyberpunk 2077 resources into forms anything opens, through WolvenKit's
console (GPL-3.0, run only as its own process). One run takes a whole batch of extracted files:
`export` turns textures into PNG and meshes and animations into glTF, `convert serialize` turns
every CR2W resource into JSON (embedded buffers included). WolvenKit's export settings ViWo needs
are written off screen into its own copy under third_party (minimal prompts); others stay."""

import contextlib
import json
from pathlib import Path
from typing import Callable, Iterator, NamedTuple

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from .rdar import CLASSES

WOLVENKIT = DependencySpec.of("wolvenkit")
SUFFIXES = tuple(sorted({f".{ext}" for ext in CLASSES.values()} | {".cr2w"}))
SLOT = SlotDefinition("decode.cr2w", "decode", "redengine", "wolvenkit-export", suffixes=SUFFIXES)
SETTINGS = {
    "XbmExportArgs": {"UncookExtension": "png"},
    "MeshExportArgs": {"meshExportType": "MeshOnly", "MaterialRepo": "", "withMaterials": False},
}
# what `export` turns into a real file format; for any other class it only dumps raw buffers
EXPORTS = frozenset({".xbm", ".mesh", ".morphtarget", ".cubemap", ".anims", ".texarray"})
BATCH = 150  # files per run at most: far under the Windows command-line limit
# What a run needs, measured on Cyberpunk 2077 2.x under caps (doc 8): about 1.2 GB before
# WolvenKit reads a file, then per byte of file what the table says while it exports
# (animations unfold the most: 8 MB needs 4 GB, 32 MB 8 GB) and ten times while it serializes.
BASE = 1200 << 20
EXPORT_COST, SERIAL_COST, ANIM_COST = 15, 10, 250
START = 2 << 30  # the room a run is planned for, and its cap (doc 9.2)
SECOND = 10  # files per run when what failed is run again, with twice the room
ALONE = 6  # runs of one file under ViWo's whole share one call may spend


def quiet_settings(folder: Path) -> None:
    """Textures as PNG, meshes without the materials (they need an uncooked depot WolvenKit
    would otherwise ask for) in its appsettings.json; ViWo's values win, the rest stays."""
    path = folder / "appsettings.json"
    try:
        current = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    except ValueError:
        current = {}
    merged = {**current}
    for section, values in SETTINGS.items():
        merged[section] = {**current.get(section, {}), **values}
    if merged != current:
        path.write_text(json.dumps(merged, indent=2), encoding="utf-8")


class WolvenKitExport(Decoder):
    backend_id, owner, license, isolation = "wolvenkit-export", "redengine", "GPL-3.0", "subprocess"
    requires = (WOLVENKIT,)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        return self.decode_many([path], dest, ctx)

    def decode_many(self, paths: list[Path], dest: Path, ctx) -> Outcome:
        if (tool := ctx.os.tools.locate(WOLVENKIT)) is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=WOLVENKIT.hint)
        if "third_party" in Path(tool.path).parts:  # ViWo's own copy, never the user's install
            quiet_settings(Path(tool.path).parent)
        else:
            ctx.log("WolvenKit settings left as they are (not ViWo's copy): textures may be DDS")
        dest.mkdir(parents=True, exist_ok=True)
        runs = _Runs(ctx, tool, dest)
        for run in plans(paths, ctx.game_root):
            runs.first(run)
        runs.second()
        files = sum(1 for p in dest.rglob("*") if p.is_file())
        if not files:
            return Outcome(OutcomeKind.FAILED, error=runs.said or "WolvenKit wrote nothing")
        note = f"{len(paths)} CR2W file(s) through WolvenKit: {files} PNG/glTF/JSON file(s)"
        partial = f"WolvenKit could not convert {runs.failed} file(s)" if runs.failed else ""
        partial = f"{partial}, e.g. {runs.said.strip()}" if partial and runs.said else partial
        return Outcome(OutcomeKind.OK, files, error=partial, notes=(note,))


class Run(NamedTuple):
    """One WolvenKit command line: the command, its files, what closes it, the cost per byte."""

    head: tuple[str, ...]
    files: list[Path]
    tail: tuple[str, ...]
    cost: Callable[[Path], int]

    def need(self) -> int:
        return BASE + sum(self.cost(p) * _size(p) for p in self.files)


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


class _Runs:
    """WolvenKit's runs for one call, each under a memory cap held out of the run's budget
    (doc 9.2). A run is planned to fit START and capped at what it is estimated to need; what
    it could not convert is run again once, ten files at a time with twice the room (a batch
    of large textures fails without a word about memory); what then fails for want of memory
    (WolvenKit says so, or the run ended badly) gets ViWo's whole share, alone, ALONE times at
    most. What still fails is counted, with the first reason."""

    def __init__(self, ctx, tool, dest: Path) -> None:
        self.ctx, self.tool, self.dest = ctx, tool, dest
        budget = getattr(ctx, "memory", None)
        self.hold = budget.hold if budget else (lambda amount: contextlib.nullcontext())
        self.share = budget.share if budget else START
        self.again, self.alone, self.failed, self.said = [], ALONE, 0, ""

    def cap(self, run: Run, scale: int = 1) -> int:
        return min(self.share, scale * max(START, run.need()))

    def once(self, run: Run, cap: int) -> tuple[list[Path], set[Path], str]:
        """One run: (the files it could not convert, those of them short of memory, the first
        reason). A run that ended badly and named none lost them all."""
        names = [str(p) for p in run.files]
        argv = [*self.tool.argv_prefix, *run.head, *names, *run.tail, "-o", str(self.dest)]
        with self.hold(cap):
            result = self.ctx.os.process.run_capped(
                cap,
                [*argv, "-v", "Minimal"],
                cwd=str(self.dest),  # whatever it writes beside its output stays in the run
                timeout=6 * 3600,
                cancel=self.ctx.cancel,
                on_line=self.ctx.tool_output("decode", every=5.0),  # WolvenKit's lines, live
            )
        text = result.stdout + result.stderr
        lines = [ln for ln in text.splitlines() if "Failed to " in ln or "Exception" in ln]
        said = {p: [ln for ln in lines if str(p) in ln or p.name in ln] for p in run.files}
        bad = [p for p in run.files if said[p]] or ([] if result.ok else run.files)
        short = {p for p in bad if not result.ok or any("OutOfMemory" in ln for ln in said[p])}
        first = next((ln[ln.index("Failed to ") :] for ln in lines if "Failed to " in ln), "")
        return bad, short, first[:300] or ("" if result.ok else text.strip()[-300:])

    def stopped(self) -> bool:
        return self.ctx.cancel is not None and self.ctx.cancel.cancelled

    def first(self, run: Run) -> None:
        if not self.stopped():
            bad, _, _ = self.once(run, self.cap(run))
            self.again += [run._replace(files=bad)] if bad else []

    def second(self) -> None:
        for lost in self.again:
            for batch in _batches(lost.files, lost.cost, SECOND):
                if self.stopped():
                    return
                run = lost._replace(files=batch)
                bad, short, why = self.once(run, self.cap(run, 2))
                for path in bad:
                    self.last(run._replace(files=[path]), path in short, why)

    def last(self, run: Run, short: bool, why: str) -> None:
        """A file that failed twice: counted, unless memory was short and the share has more."""
        if short and self.alone > 0 and self.cap(run, 2) < self.share and not self.stopped():
            self.alone -= 1
            bad, _, why = self.once(run, self.share)
            if not bad:
                return
        self.failed, self.said = self.failed + 1, self.said or why


def _batches(paths: list[Path], cost, most: int = BATCH) -> Iterator[list[Path]]:
    """The files in their order, in runs of at most `most` whose estimated need fits START;
    a file that does not fit is a run by itself."""
    batch, held = [], BASE
    for path in paths:
        need = cost(path) * _size(path)
        if batch and (len(batch) >= most or held + need > START):
            yield batch
            batch, held = [], BASE
        batch, held = [*batch, path], held + need
    if batch:
        yield batch


def _export_cost(path: Path) -> int:
    return ANIM_COST if path.suffix.lower() == ".anims" else EXPORT_COST


def plans(paths: list[Path], game_root) -> list[Run]:
    """The runs, the files in their order: `export` for the classes it converts, `convert
    serialize` for all."""
    wanted = [p for p in paths if p.suffix.lower() in EXPORTS]
    tail = ("-gp", str(game_root))
    runs = [Run(("export",), b, tail, _export_cost) for b in _batches(wanted, _export_cost)]
    serial = lambda path: SERIAL_COST  # noqa: E731
    return runs + [Run(("convert", "serialize"), b, (), serial) for b in _batches(paths, serial)]


def commands(paths: list[Path], game_root) -> list[list[str]]:
    """The runs as command lines (what `plans` gives, flattened)."""
    return [[*r.head, *(str(p) for p in r.files), *r.tail] for r in plans(paths, game_root)]
