"""The way back for decode.cr2w (doc 18.3) through WolvenKit's console, the pinned tool that
exported the files (GPL-3.0, its own process). An edited JSON goes back with `convert
deserialize`; an edited PNG, DDS, TGA or glTF with `import --keep` next to a copy of the original
resource, so WolvenKit rebuilds it from the raw file with the original's settings (the copy sits
beside the raw file and in the output folder: where WolvenKit looks for it). One run per file,
under a memory cap held out of the budget like the export's (export._Runs)."""

import hashlib
import shutil
from pathlib import Path

from viwo.contracts.types import Outcome, OutcomeKind

from .export import SERIAL_COST, WOLVENKIT, Run, _export_cost, _Runs

RAW = (".png", ".dds", ".tga", ".glb", ".gltf")


def sha256_of(path: Path) -> str:
    with open(path, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def _run(edited: Path, original: Path, work: Path) -> Run:
    """The command for one edited file, its inputs laid out in `work`."""
    suffix = edited.suffix.lower()
    if suffix == ".json":
        raw = work / f"{original.name}.json"
        shutil.copyfile(edited, raw)
        return Run(("convert", "deserialize"), [raw], (), lambda path: SERIAL_COST)
    if suffix not in RAW:
        raise ValueError(f"WolvenKit imports {', '.join(RAW)} and .json, not {suffix}")
    raw = work / f"{original.name.split('.')[0]}{suffix}"
    shutil.copyfile(edited, raw)
    shutil.copyfile(original, work / original.name)
    return Run(("import",), [raw], ("-k",), _export_cost)


def wolvenkit_encode(edited: Path, original: Path, out: Path, ctx) -> Outcome:
    if (tool := ctx.os.tools.locate(WOLVENKIT)) is None:
        return Outcome(OutcomeKind.UNAVAILABLE, error=WOLVENKIT.hint)
    work, made = out.parent / "wolvenkit-in", out.parent / "wolvenkit-out"
    for folder in (work, made):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    try:
        run = _run(edited, original, work)
    except (ValueError, OSError) as exc:
        return Outcome(OutcomeKind.FAILED, error=f"{edited.name}: {exc}")
    if run.head == ("import",):
        shutil.copyfile(original, made / original.name)
    runs = _Runs(ctx, tool, made)
    bad, _, said = runs.once(run, runs.cap(run))
    found = next((p for p in made.rglob(original.name) if p.is_file()), None)
    if bad or found is None or sha256_of(found) == sha256_of(original):
        why = said or f"WolvenKit wrote no new {original.name}"
        return Outcome(OutcomeKind.FAILED, error=f"{edited.name}: {why}"[:300])
    shutil.copyfile(found, out)
    return Outcome(OutcomeKind.OK, 1, notes=(f"{edited.name} -> {original.name} (WolvenKit)",))
