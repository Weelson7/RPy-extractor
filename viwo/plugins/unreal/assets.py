"""export.unreal (doc 16.0c): Unreal assets decoded for any UE4/UE5 game, through UnrealAssetScout
(MIT, built on CUE4Parse; run as its own process): textures to PNG, meshes and skeletons to glTF,
animations, sounds, and every package as JSON. The engine version is read from the game's own
binaries (the `++UE5+Release-5.x` build string); cooked UE5 assets need the game's mappings
(`.usmap`), which the RUNTIME agent (UE4SS) writes into the workspace, or which the user gives;
without them those packages are counted and the way to get them is named."""

import re
import shutil
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.slots import Exporter, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files

from .keys import resolve_key

UAS = DependencySpec(
    "uas",
    "UnrealAssetScout",
    env_var="VIWO_UAS",
    executables=("uas",),
    hint="`viwo install uas` (MIT, Windows build)",
)
SLOT = SlotDefinition("export.unreal", "export", "unreal", "uas-export")
MODES = ("Textures", "Models", "Animations", "Audio", "Json")


def _w(text: str) -> bytes:
    """`text` as the UTF-16LE bytes Unreal stores its strings in, escaped for a regex."""
    return re.escape(text.encode("utf-16-le"))


BUILD = re.compile(_w("++UE") + rb"([45])\x00" + _w("+Release-") + rb"[45]\x00\.\x00((?:\d\x00)+)")
NEEDS_MAPPINGS = "could not load package"


def engine(game_root: Path) -> str:
    """`GAME_UE5_1` from the build string in the game's binaries (largest executables first)."""
    exes = sorted(ws.files(game_root, "*.exe"), key=lambda p: -p.stat().st_size)[:4]
    for exe in exes:
        with open(exe, "rb") as fh:
            found = BUILD.search(fh.read())
        if found:
            minor = found.group(2).replace(b"\x00", b"").decode()
            return f"GAME_UE{found.group(1).decode()}_{minor}"
    return ""


def paks_folders(game_root: Path) -> list[Path]:
    """Absolute: the tool runs in the scratch folder."""
    hits = {
        p.parent.resolve() for p in ws.files(game_root) if p.suffix.lower() in (".pak", ".utoc")
    }
    return sorted(hits)


def mappings(ctx) -> Path | None:
    """The user's `usmap` option, else the newest `.usmap` the RUNTIME agent (or anything
    else) left in the workspace, else one the game ships."""
    given = str((ctx.options or {}).get("usmap", "") or "").strip()
    if given and Path(given).is_file():
        return Path(given).resolve()
    roots = [r for r in (ctx.workspace and Path(ctx.workspace) / ".runtime", ctx.game_root) if r]
    found = [p for r in roots if r.is_dir() for p in r.rglob("*.usmap")]
    return max(found, key=lambda p: p.stat().st_mtime).resolve() if found else None


class UasExport(Exporter):
    backend_id, owner, license, isolation = "uas-export", "unreal", "MIT", "subprocess"
    requires = (UAS,)

    def export(self, ctx) -> Outcome:
        if (tool := ctx.os.tools.locate(UAS)) is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=UAS.hint)
        version = str((ctx.options or {}).get("engine", "") or "") or engine(ctx.game_root)
        folders = paks_folders(ctx.game_root)
        if not version or not folders:
            why = "no .pak/.utoc" if not folders else "no engine version found (option engine)"
            return Outcome(OutcomeKind.FAILED, error=f"Unreal asset export: {why}")
        usmap, failed, need = mappings(ctx), 0, 0
        for folder in folders:
            f, n, stop = self._folder(ctx, tool, folder, version, usmap)
            if stop is not None:
                return stop
            failed, need = failed + f, need + n
        for manifest in ctx.staging.rglob(".uas-manifest.json"):
            manifest.unlink()
        return Outcome(OutcomeKind.OK, count_files(ctx.staging), notes=_notes(failed, need, usmap))

    def _folder(self, ctx, tool, folder: Path, version: str, usmap):
        """Every mode over one Paks folder: (failed packages, those needing mappings, the
        outcome that stops the export, else None)."""
        first = next(iter(sorted(folder.glob("*.pak")) + sorted(folder.glob("*.utoc"))))
        key, problem = resolve_key(first, ctx)
        if problem:
            return 0, 0, Outcome(OutcomeKind.NEEDS_KEY, error=problem)
        base = ["-p", str(folder), "-g", version, "-z", "-c"]
        base += ["-u", str(usmap)] if usmap else []
        base += ["-a", f"0x{key}"] if key else []  # one process's command line, masked below
        failed = need = 0
        for mode in MODES:
            out = (ctx.staging / mode.lower()).resolve()
            result = ctx.os.process.run(
                [*tool.argv_prefix, "export", mode, "-o", str(out), *base],
                cwd=str(ctx.scratch) if ctx.scratch.is_dir() else None,
                timeout=6 * 3600,
                cancel=ctx.cancel,
                on_line=ctx.tool_output("export", mask=key),
            )
            text = result.stdout + result.stderr
            if key:  # the key is on that command line: whatever the tool echoes is masked
                text = text.replace(key, "<secret>").replace(key.upper(), "<secret>")
            if not result.ok:
                said = f"{mode}: {text.strip()[-200:] or f'exit {result.returncode}'}"
                return failed, need, Outcome(OutcomeKind.FAILED, error=said)
            lines = [ln for ln in text.splitlines() if "[FAILED]" in ln]
            failed += len(lines) if mode == "Json" else 0  # Json tries every package
            need += sum(NEEDS_MAPPINGS in ln for ln in lines) if mode == "Json" and not usmap else 0
            if out.is_dir() and not any(p.name != ".uas-manifest.json" for p in out.rglob("*")):
                shutil.rmtree(out, ignore_errors=True)
        return failed, need, None


def _notes(failed: int, need: int, usmap) -> tuple[str, ...]:
    if need:
        return (
            f"{need} package(s) need the game's mappings (.usmap): run the RUNTIME agent "
            "(UE4SS) once, or set [options.unreal] usmap",
        )
    return (f"{failed} package(s) could not be read",) if failed else ()
