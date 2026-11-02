"""Unity export backends: UnityPy (main, in-process) and AssetStudioModCLI (spare)."""

from __future__ import annotations

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
    executables=("AssetStudioModCLI",),
    install_dirs=("AssetStudioMod",),
    hint="install AssetStudioModCLI (MIT) from aelurum/AssetStudio",
)
CONTAINER_NAME = re.compile(
    r"^(globalgamemanagers.*|.*\.assets|level\d+|sharedassets\d+.*|.*\.bundle|data\.unity3d"
    r"|.*\.unity3d|cab-.*|unity default resources|unity_builtin_extra)$",
    re.IGNORECASE,
)


def unity_containers(root: Path) -> list[Path]:
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if CONTAINER_NAME.match(path.name):
            found.append(path)
            continue
        with open(path, "rb") as fh:
            if fh.read(7) == b"UnityFS":
                found.append(path)
    return found


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


class UnityPyExporter(Exporter):
    backend_id, owner, license = "unitypy", "unity", "MIT"

    def dependencies(self):
        return (UNITYPY,)

    def export(self, ctx) -> Outcome:
        try:
            import UnityPy
        except ImportError:
            return Outcome(OutcomeKind.UNAVAILABLE, error=UNITYPY.hint)
        exported, notes = 0, []
        for container in unity_containers(ctx.game_root):
            if ctx.cancel.cancelled:
                break
            try:
                env = UnityPy.load(str(container))
            except Exception as exc:  # unreadable container: note it and continue
                notes.append(f"{container.name}: {exc}"[:200])
                continue
            for obj in env.objects:
                try:
                    exported += _export_object(ctx, obj, f"{container.stem}_{obj.path_id}")
                except Exception as exc:  # one broken object must not stop the export
                    notes.append(f"{container.name}#{obj.path_id}: {exc}"[:200])
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
