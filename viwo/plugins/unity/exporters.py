"""Unity export backends: UnityPy (main, in-process) and AssetStudioModCLI (spare)."""

from __future__ import annotations

import gc
import json
import re
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import option_bool
from viwo.contracts.slots import Exporter
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files

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
        try:
            with open(path, "rb") as fh:
                head = fh.read(4096)
        except OSError:  # held by an antivirus or locked: the copy step already reported it
            continue
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


def _flag(ctx, key: str, default: bool) -> bool:
    return option_bool(getattr(ctx, "options", None), key, default)


def _write(ctx, kind: str, name: str, ext: str, payload: bytes) -> Path | None:
    if not _wanted(ctx, ext):
        return None
    folder = ctx.staging / kind
    folder.mkdir(parents=True, exist_ok=True)
    target = ws.next_free(folder / f"{name}{ext}")
    target.write_bytes(payload)
    return target


def container_of(obj, files: list[Path], root: Path) -> str | None:
    """Game-relative disk file an object was loaded from (for the round trip map)."""
    node = getattr(obj, "assets_file", None)
    while node is not None and type(getattr(node, "parent", None)).__name__ != "Environment":
        node = getattr(node, "parent", None)
    name = Path(str(getattr(node, "name", "") or "")).name
    found = next((f for f in files if f.name == name), None)
    return found.relative_to(root).as_posix() if found and root in found.parents else None


def _export_object(ctx, obj, fallback: str, record: dict) -> int:
    kind = obj.type.name
    data = obj.parse_as_object()
    name = _name(data, fallback)
    if kind in ("Texture2D", "Sprite") and _wanted(ctx, ".png"):
        folder = ctx.staging / "images"
        folder.mkdir(parents=True, exist_ok=True)
        target = ws.next_free(folder / f"{name}.png")
        data.image.save(target)
        if kind == "Texture2D" and record.get("where"):
            record["map"][f"images/{target.name}"] = [record["where"], str(obj.path_id)]
        return 1
    if kind == "AudioClip":
        samples = data.samples or {}
        return sum(
            1
            for k, v in samples.items()
            if _write(ctx, "audio", _name(data, Path(k).stem), Path(k).suffix.lower() or ".wav", v)
        )
    if kind == "TextAsset":
        script = getattr(data, "m_Script", "")
        raw = (
            script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)
        )
        target = _write(ctx, "text", name, ".txt", raw)
        if target and record.get("where"):
            record["map"][f"text/{target.name}"] = [record["where"], str(obj.path_id)]
        return int(target is not None)
    if kind == "Mesh" and record.get("meshes", True):
        text = data.export()  # UnityPy Mesh.export(format="obj"): Wavefront OBJ text
        return int(
            bool(text) and _write(ctx, "mesh", name, ".obj", text.encode("utf-8")) is not None
        )
    return 0


EXPORTED = frozenset(("Texture2D", "Sprite", "AudioClip", "TextAsset", "Mesh"))


def _export_env(ctx, env, label: str, record: dict) -> tuple[int, list[str]]:
    exported, notes = 0, []
    for obj in env.objects:
        if obj.type.name not in EXPORTED:  # parsing the rest is wasted (and fails on IL2CPP)
            continue
        try:
            record["where"] = container_of(obj, record["files"], ctx.game_root)
            exported += _export_object(ctx, obj, f"{label}_{obj.path_id}", record)
        except Exception as exc:  # one broken object must not stop the export
            notes.append(f"{label}#{obj.path_id}: {exc}"[:200])
    return exported, notes


def _export_group(ctx, unitypy, files: list[Path], mapping: dict) -> tuple[int, list[str]]:
    """Load a folder's containers together; fall back to one file at a time."""
    record = {"files": files, "map": mapping, "meshes": _flag(ctx, "meshes", True)}
    try:
        return _export_env(
            ctx, unitypy.load(*[str(f) for f in files]), files[0].parent.name, record
        )
    except Exception:  # a broken file poisons a group load: retry files one by one
        exported, notes = 0, []
        for path in files:
            try:
                count, problems = _export_env(ctx, unitypy.load(str(path)), path.stem, record)
            except Exception as exc:  # unreadable container: note it and continue
                count, problems = 0, [f"{path.name}: {exc}"[:200]]
            exported, notes = exported + count, notes + problems
        return exported, notes


class UnityPyExporter(Exporter):
    backend_id, owner, license = "unitypy", "unity", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def dependencies(self):
        return (UNITYPY,)

    def export(self, ctx) -> Outcome:
        try:
            import UnityPy
        except ImportError:
            return Outcome(OutcomeKind.UNAVAILABLE, error=UNITYPY.hint)
        roots = [ctx.game_root]
        if _flag(ctx, "include_cache", False):
            roots += cache_roots(ctx.game_root)
        exported, notes, mapping = 0, [], {}
        for root in roots:
            for files in groups(unity_containers(root)).values():
                if ctx.cancel.cancelled:
                    break
                count, problems = _export_group(ctx, UnityPy, files, mapping)
                exported, notes = exported + count, notes + problems
                gc.collect()  # UnityPy keeps file handles until collected; Windows locks them
        ctx.log(f"UnityPy exported {exported} asset(s), {len(notes)} problem(s)", stage="export")
        (ctx.staging / ws.EXPORT_MAP).write_text(json.dumps(mapping), encoding="utf-8")
        return Outcome(OutcomeKind.OK, exported, notes=tuple(notes[:50]))


class AssetStudioModCli(Exporter):
    backend_id, owner, license, isolation = "assetstudiomod-cli", "unity", "MIT", "subprocess"

    def dependencies(self):
        return (ASSETSTUDIO,)

    @staticmethod
    def argv(ctx, tool) -> list[str]:
        """Flags verified against AssetStudioModCLI 0.20 --help (-m/-t/-o, convert, logger)."""
        types = ["tex2d", "sprite", "audio", "textAsset"] + (
            ["mesh"] if _flag(ctx, "meshes", True) else []
        )
        return [
            *tool.argv_prefix,
            str(ctx.game_root),
            "-m",
            "export",
            "-t",
            ",".join(types),
            "-o",
            str(ctx.staging),
            "--image-format",
            "png",
            "--audio-format",
            "wav",
            "--log-level",
            "warning",
        ]

    def export(self, ctx) -> Outcome:
        tool = ctx.os.tools.locate(ASSETSTUDIO)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=ASSETSTUDIO.hint)
        result = ctx.os.process.run(self.argv(ctx, tool), timeout=7200, cancel=ctx.cancel)
        if not result.ok:
            return Outcome(OutcomeKind.FAILED, error=(result.stderr or result.stdout)[-300:])
        return Outcome(OutcomeKind.OK, count_files(ctx.staging))
