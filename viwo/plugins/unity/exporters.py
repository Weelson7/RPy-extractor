"""Unity export backends: UnityPy (main, in-process) and AssetStudioModCLI (spare)."""

from __future__ import annotations

import gc
import re
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.slots import Exporter
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

UNITYPY = DependencySpec(
    "unitypy", "UnityPy", kind="python", import_name="UnityPy", hint="pip install UnityPy"
)
ASSETSTUDIO = DependencySpec(
    "assetstudiomod",
    "AssetStudioModCLI",
    env_var="VIWO_ASSETSTUDIOMOD",
    executables=("AssetStudioModCLI",),
    install_dirs=("AssetStudioMod",),
    hint="install AssetStudioModCLI (MIT) from aelurum/AssetStudio",
)
CONTAINER_NAME = re.compile(
    r"^(globalgamemanagers.*|.*\.assets|level\d+|sharedassets\d+.*|.*\.bundle|data\.unity3d"
    r"|.*\.unity3d|cab-.*|unity default resources|unity_builtin_extra)$",
    re.IGNORECASE,
)


SIGNATURES = (b"UnityFS", b"UnityWeb", b"UnityRaw", b"UnityWebData")


def unity_containers(root: Path) -> list[Path]:
    """Every file Unity can load from disk: known names, or a Unity signature anywhere in
    the first 4 KB (bundles with a custom header, WebGL data, Addressables bundles)."""
    found = []
    for path in sorted(root.rglob("*")) if root.is_dir() else ():
        if not path.is_file():
            continue
        if CONTAINER_NAME.match(path.name):
            found.append(path)
            continue
        with open(path, "rb") as fh:
            head = fh.read(4096)
        if any(sig in head for sig in SIGNATURES):
            found.append(path)
    return found


def cache_roots(game_root: Path) -> list[Path]:
    """The game's own persistent-data/cache folders (outside the game folder), found from
    `<Game>_Data/app.info` (company, product). Read-only; opt-in via a plugin option."""
    info = next(iter(sorted(game_root.glob("*_Data/app.info"))), None)
    if info is None:
        return []
    lines = info.read_text(encoding="utf-8", errors="replace").splitlines() + ["", ""]
    company, product = lines[0].strip(), lines[1].strip()
    if not company or not product:
        return []
    home = Path.home()
    candidates = [
        home / "AppData" / "LocalLow" / company / product,
        home / "AppData" / "LocalLow" / "Unity" / f"{company}_{product}",
        home / ".config" / "unity3d" / company / product,
    ]
    return [c for c in candidates if c.is_dir()]


def groups(containers: list[Path]) -> dict[Path, list[Path]]:
    """Containers loaded together so cross-file references (.resS streams, sprites ->
    textures in other files) resolve: grouped by their folder."""
    out: dict[Path, list[Path]] = {}
    for path in containers:
        out.setdefault(path.parent, []).append(path)
    return out


def _name(data, fallback: str) -> str:
    raw = str(getattr(data, "m_Name", "") or "").strip()
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", raw).strip(" .")
    return clean or fallback


def _wanted(ctx, ext: str) -> bool:
    return ctx.selected_exts is None or ext in ctx.selected_exts


def _write(ctx, kind: str, name: str, ext: str, payload: bytes) -> int:
    if not _wanted(ctx, ext):
        return 0
    folder = ctx.staging / kind
    folder.mkdir(parents=True, exist_ok=True)
    ws.next_free(folder / f"{name}{ext}").write_bytes(payload)
    return 1


def _export_object(ctx, obj, fallback: str) -> int:
    kind = obj.type.name
    data = obj.parse_as_object()
    name = _name(data, fallback)
    if kind in ("Texture2D", "Sprite") and _wanted(ctx, ".png"):
        folder = ctx.staging / "images"
        folder.mkdir(parents=True, exist_ok=True)
        data.image.save(ws.next_free(folder / f"{name}.png"))
        return 1
    if kind == "AudioClip":
        samples = data.samples or {}
        return sum(
            _write(ctx, "audio", _name(data, Path(k).stem), Path(k).suffix.lower() or ".wav", v)
            for k, v in samples.items()
        )
    if kind == "TextAsset":
        script = getattr(data, "m_Script", "")
        raw = (
            script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)
        )
        return _write(ctx, "text", name, ".txt", raw)
    if kind == "Mesh":
        text = data.export()
        return _write(ctx, "models", name, ".obj", text.encode("utf-8")) if text else 0
    return 0


def _export_env(ctx, env, label: str) -> tuple[int, list[str]]:
    exported, notes = 0, []
    for obj in env.objects:
        try:
            exported += _export_object(ctx, obj, f"{label}_{obj.path_id}")
        except Exception as exc:  # one broken object must not stop the export
            notes.append(f"{label}#{obj.path_id}: {exc}"[:200])
    return exported, notes


def _export_group(ctx, unitypy, files: list[Path]) -> tuple[int, list[str]]:
    """Load a folder's containers together; fall back to one file at a time."""
    try:
        return _export_env(ctx, unitypy.load(*[str(f) for f in files]), files[0].parent.name)
    except Exception:  # a broken file poisons a group load: retry files one by one
        exported, notes = 0, []
        for path in files:
            try:
                count, problems = _export_env(ctx, unitypy.load(str(path)), path.stem)
            except Exception as exc:  # unreadable container: note it and continue
                count, problems = 0, [f"{path.name}: {exc}"[:200]]
            exported, notes = exported + count, notes + problems
        return exported, notes


class UnityPyExporter(Exporter):
    backend_id, owner, license = "unitypy", "unity", "MIT"

    def dependencies(self):
        return (UNITYPY,)

    def export(self, ctx) -> Outcome:
        try:
            import UnityPy
        except ImportError:
            return Outcome(OutcomeKind.UNAVAILABLE, error=UNITYPY.hint)
        roots = [ctx.game_root]
        if str(ctx.options.get("include_cache", "")).lower() in ("1", "true", "yes", "on"):
            roots += cache_roots(ctx.game_root)
        exported, notes = 0, []
        for root in roots:
            for files in groups(unity_containers(root)).values():
                if ctx.cancel.cancelled:
                    break
                count, problems = _export_group(ctx, UnityPy, files)
                exported, notes = exported + count, notes + problems
                gc.collect()  # UnityPy keeps file handles until collected; Windows locks them
        ctx.log(f"UnityPy exported {exported} asset(s), {len(notes)} problem(s)", stage="export")
        return Outcome(OutcomeKind.OK, exported, notes=tuple(notes[:50]))


class AssetStudioModCli(Exporter):
    backend_id, owner, license, isolation = "assetstudiomod-cli", "unity", "MIT", "subprocess"

    def dependencies(self):
        return (ASSETSTUDIO,)

    def export(self, ctx) -> Outcome:
        tool = ctx.os.tools.locate(ASSETSTUDIO)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=ASSETSTUDIO.hint)
        argv = [
            *tool.argv_prefix,
            str(ctx.game_root),
            "-m",
            "export",
            "-t",
            "tex2d,sprite,audio,textAsset,mesh",
            "-o",
            str(ctx.staging),
            "--image-format",
            "png",
        ]
        result = ctx.os.process.run(argv, timeout=7200, cancel=ctx.cancel)
        if not result.ok:
            return Outcome(OutcomeKind.FAILED, error=(result.stderr or result.stdout)[-300:])
        return Outcome(OutcomeKind.OK, sum(1 for p in ctx.staging.rglob("*") if p.is_file()))
