"""decode.cr2w (doc 16.0c): Cyberpunk 2077 resources into forms anything opens, through WolvenKit's
console (GPL-3.0, run only as its own process). One run takes a whole batch of extracted files:
`export` turns textures into PNG and meshes and animations into glTF, `convert serialize` turns
every CR2W resource into JSON (embedded buffers included). WolvenKit's export settings ViWo needs
are written off screen into its own copy under third_party (minimal prompts); others stay."""

import contextlib
import json
from pathlib import Path

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
BATCH = 150  # files per run: far under the Windows command-line limit
HEAVY = frozenset({".anims"})  # WolvenKit keeps these whole in memory: ten of them count as a run
START = 2 << 30  # the memory cap a run starts under (doc 9.2); what fails is retried, see _Runs
RETRIES = 12  # extra runs one call may spend on what failed


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
        for head, batch, tail in plans(paths, ctx.game_root):
            runs.go(head, batch, tail, START)
        files = sum(1 for p in dest.rglob("*") if p.is_file())
        if not files:
            return Outcome(OutcomeKind.FAILED, error=runs.said or "WolvenKit wrote nothing")
        note = f"{len(paths)} CR2W file(s) through WolvenKit: {files} PNG/glTF/JSON file(s)"
        partial = f"WolvenKit could not convert {runs.failed} file(s)" if runs.failed else ""
        partial = f"{partial}, e.g. {runs.said.strip()}" if partial and runs.said else partial
        return Outcome(OutcomeKind.OK, files, error=partial, notes=(note,))


class _Runs:
    """WolvenKit's runs for one call, each under a memory cap taken from the run's budget. How
    much a file needs cannot be told from its size (measured on Cyberpunk 2077: one 32 MB
    animation needs more than 3 GB, forty large textures more than 3 GB together), so a run
    starts under START and what it could not convert for want of memory (WolvenKit says so, or
    the run ended badly) is tried again: beside fewer files, then alone under twice the cap, up
    to ViWo's whole share. RETRIES bounds that; what still fails is counted and the first reason
    kept."""

    def __init__(self, ctx, tool, dest: Path) -> None:
        self.ctx, self.tool, self.dest = ctx, tool, dest
        budget = getattr(ctx, "memory", None)
        self.hold = budget.hold if budget else (lambda amount: contextlib.nullcontext())
        self.share = budget.share if budget else START
        self.left, self.failed, self.said = RETRIES, 0, ""

    def once(self, head: list[str], batch: list[str], tail: list[str], cap: int) -> tuple:
        """One run: (the files it could not convert, whether memory was what it lacked). A run
        that ended badly and named none lost them all."""
        argv = [*self.tool.argv_prefix, *head, *batch, *tail, "-o", str(self.dest)]
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
        first = next((ln[ln.index("Failed to ") :] for ln in lines if "Failed to " in ln), "")
        self.said = self.said or first[:300] or ("" if result.ok else text.strip()[-300:])
        named = [f for f in batch if any(f in ln or Path(f).name in ln for ln in lines)]
        short = "OutOfMemory" in text or not result.ok
        return named or ([] if result.ok else batch), short

    def go(self, head: list[str], batch: list[str], tail: list[str], cap: int) -> None:
        bad, short = self.once(head, batch, tail, cap)
        if not bad or (self.ctx.cancel is not None and self.ctx.cancel.cancelled):
            return
        if not short:  # WolvenKit cannot convert these: no second run changes that
            self.failed += len(bad)
        elif len(bad) < len(batch):  # beside fewer files they may fit
            self.again(head, bad, tail, cap)
        elif len(bad) > 1:
            half = len(bad) // 2
            self.again(head, bad[:half], tail, cap)
            self.again(head, bad[half:], tail, cap)
        elif cap < self.share:  # alone and still short: more room
            self.again(head, bad, tail, min(self.share, cap * 2))
        else:
            self.failed += 1

    def again(self, head: list[str], batch: list[str], tail: list[str], cap: int) -> None:
        if self.left <= 0:
            self.failed += len(batch)
            return
        self.left -= 1
        self.go(head, batch, tail, cap)


def plans(paths: list[Path], game_root) -> list[tuple[list[str], list[str], list[str]]]:
    """(command, files, closing arguments) per run, the files in their order: `export` for the
    classes it converts (a HEAVY file counts as fifteen, so ten make a run), `convert
    serialize` for all."""
    runs, batch, weight = [], [], 0
    for path in (p for p in paths if p.suffix.lower() in EXPORTS):
        cost = BATCH // 10 if path.suffix.lower() in HEAVY else 1
        if batch and weight + cost > BATCH:
            runs.append((["export"], batch, ["-gp", str(game_root)]))
            batch, weight = [], 0
        batch, weight = [*batch, str(path)], weight + cost
    if batch:
        runs.append((["export"], batch, ["-gp", str(game_root)]))
    for start in range(0, len(paths), BATCH):
        runs.append((["convert", "serialize"], [str(p) for p in paths[start : start + BATCH]], []))
    return runs


def commands(paths: list[Path], game_root) -> list[list[str]]:
    """The runs as command lines (what `plans` gives, flattened)."""
    return [[*head, *batch, *tail] for head, batch, tail in plans(paths, game_root)]
