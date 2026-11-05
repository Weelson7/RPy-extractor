"""decode.cr2w (doc 16.0c): Cyberpunk 2077 resources into forms anything opens, through WolvenKit's
console (GPL-3.0, run only as its own process). One run takes a whole batch of extracted files:
`export` turns textures into PNG and meshes and animations into glTF, `convert serialize` turns
every CR2W resource into JSON (embedded buffers included). WolvenKit's export settings ViWo needs
are written off screen into its own copy under third_party (minimal prompts); others stay."""

import json
from pathlib import Path

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from .rdar import CLASSES

WOLVENKIT = DependencySpec(
    "wolvenkit",
    "WolvenKit CLI",
    env_var="VIWO_WOLVENKIT",
    executables=("WolvenKit.CLI",),
    hint="`viwo install wolvenkit` (GPL-3.0, run as its own process)",
)
SUFFIXES = tuple(sorted({f".{ext}" for ext in CLASSES.values()} | {".cr2w"}))
SLOT = SlotDefinition("decode.cr2w", "decode", "redengine", "wolvenkit-export", suffixes=SUFFIXES)
SETTINGS = {
    "XbmExportArgs": {"UncookExtension": "png"},
    "MeshExportArgs": {"meshExportType": "MeshOnly", "MaterialRepo": "", "withMaterials": False},
}
# what `export` turns into a real file format; for any other class it only dumps raw buffers
EXPORTS = frozenset({".xbm", ".mesh", ".morphtarget", ".cubemap", ".anims", ".texarray"})
BATCH = 150  # files per run: the command line stays far under the Windows limit


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
        said, failed = "", 0
        for command in commands(paths, ctx.game_root):
            result = ctx.os.process.run(
                [*tool.argv_prefix, *command, "-o", str(dest), "-v", "Minimal"],
                cwd=str(dest),  # whatever it writes beside its output stays in the run
                timeout=6 * 3600,
                cancel=ctx.cancel,
            )
            text = result.stdout + result.stderr
            lines = [
                line[line.index("Failed to ") :]
                for line in text.splitlines()
                if "Failed to " in line
            ]
            failed += len(lines)
            said = said or (lines[0][:300] if lines else "")
            said = said or ("" if result.ok else text.strip()[-300:])
        files = sum(1 for p in dest.rglob("*") if p.is_file())
        if not files:
            return Outcome(OutcomeKind.FAILED, error=said or "WolvenKit wrote nothing")
        note = f"{len(paths)} CR2W file(s) through WolvenKit: {files} PNG/glTF/JSON file(s)"
        partial = f"WolvenKit could not convert {failed} file(s)" if failed else "WolvenKit failed"
        partial = f"{partial}, e.g. {said.strip()}" if said else ""
        return Outcome(OutcomeKind.OK, files, error=partial, notes=(note,))


def commands(paths: list[Path], game_root) -> list[list[str]]:
    """`export` for the classes it converts, `convert serialize` for all, in batches."""
    runs = []
    exports = [str(p) for p in paths if p.suffix.lower() in EXPORTS]
    for start in range(0, len(exports), BATCH):
        runs.append(["export", *exports[start : start + BATCH], "-gp", str(game_root)])
    for start in range(0, len(paths), BATCH):
        runs.append(["convert", "serialize", *(str(p) for p in paths[start : start + BATCH])])
    return runs
