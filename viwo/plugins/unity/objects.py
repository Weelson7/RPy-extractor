"""Everything else a Unity game holds (doc 16.0c): video clips, fonts and shaders in their own
formats, and every other object (scenes, prefabs, materials, animations, game objects and their
components, MonoBehaviour data) as JSON from its type tree, one file per serialized file. A
MonoBehaviour whose script layout the build stripped is listed with its script and counted; the
layouts come from the game's managed assemblies when they ship (Mono), else (IL2CPP) from the
stand-in assemblies Cpp2IL rebuilds from GameAssembly and the metadata (a separate process, MIT),
once per export, into the run's scratch folder."""

import gc
import json
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.types import DependencySpec

CPP2IL = DependencySpec.of("cpp2il")

FONT_EXT = {b"OTTO": ".otf", b"true": ".ttf", b"\x00\x01\x00\x00": ".ttf", b"ttcf": ".ttc"}
BLOB = 4096  # raw byte fields above this size are summarised, not inlined as hex


def _plain(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return raw.hex() if len(raw) <= BLOB else f"<{len(raw)} bytes>"
    return str(value)


def media(ctx, kind: str, data, obj, name: str) -> Path | None:
    """VideoClip -> its original file, Font -> .ttf/.otf, Shader -> readable source; None when
    the object holds nothing to write."""
    folder = ctx.staging / {"VideoClip": "video", "Font": "font", "Shader": "shader"}[kind]
    if kind == "VideoClip":
        from UnityPy.helpers.ResourceReader import get_resource_data

        res = data.m_ExternalResources
        if not res.m_Size:
            return None
        payload = get_resource_data(res.m_Source, obj.assets_file, res.m_Offset, res.m_Size)
        ext = Path(str(data.m_OriginalPath or "")).suffix.lower() or ".mp4"
    elif kind == "Font":
        payload = bytes(data.m_FontData or b"")
        if not payload:
            return None
        ext = FONT_EXT.get(payload[:4], ".ttf")
    else:
        payload, ext = data.export().encode("utf-8"), ".shader"
    folder.mkdir(parents=True, exist_ok=True)
    target = ws.next_free(folder / f"{name}{ext}")
    target.write_bytes(bytes(payload))
    return target


def _json(entry: dict) -> str:
    """One entry as JSON text that UTF-8 can hold: a string UnityPy kept as escaped bytes (a
    lone surrogate) is written with JSON escapes instead of breaking the file."""
    text = json.dumps(entry, default=_plain, ensure_ascii=False)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = json.dumps(entry, default=_plain, ensure_ascii=True)
    return text


class Dump:
    """One JSON array per serialized file, written as the objects come (a scene holds hundreds
    of thousands): `data/<file>.objects.json`. Handles are closed after every group (release)
    and reopened to append, so thousands of bundles never exhaust the descriptors. Counts what
    had no layout."""

    def __init__(self, staging: Path) -> None:
        self.folder = staging / "data"
        self.paths: dict[str, Path] = {}  # serialized file -> its JSON
        self.counts: dict[str, int] = {}
        self.open: dict[str, object] = {}
        self.written = 0
        self.no_layout: dict[str, int] = {}
        self.exhausted = False  # a layout asked for more memory than ViWo may take

    def add(self, obj, kind: str) -> None:
        source = Path(str(getattr(obj.assets_file, "name", "") or "unknown")).name
        try:
            entry = {"path_id": obj.path_id, "type": kind, "data": obj.read_typetree()}
        except Exception as exc:  # noqa: BLE001  (a stripped layout, or damage: listed, counted)
            self.exhausted = self.exhausted or isinstance(exc, MemoryError)
            self.no_layout[kind] = self.no_layout.get(kind, 0) + 1
            entry = {"path_id": obj.path_id, "type": kind, "unread": str(exc)[:160] or "memory"}
        text = _json(entry)  # made before anything is written: a failure leaves the file whole
        fh = self._handle(source)
        fh.write(("[\n" if not self.counts[source] else ",\n") + text)
        self.counts[source] += 1
        self.written += 1

    def _handle(self, source: str):
        if source in self.open:
            return self.open[source]
        if source not in self.paths:
            self.folder.mkdir(parents=True, exist_ok=True)
            self.paths[source] = ws.next_free(self.folder / f"{source}.objects.json")
            self.counts[source] = 0
        self.open[source] = open(self.paths[source], "a", encoding="utf-8")
        return self.open[source]

    def release(self) -> None:
        """Close what is open (after each group; the next one reopens to append)."""
        for fh in self.open.values():
            fh.close()
        self.open.clear()

    def close(self) -> tuple[str, list[str]]:
        """Finish every file: (what was dumped, for the log; the objects without a layout)."""
        self.release()
        for path in self.paths.values():
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n]\n")
        summary = f"{self.written} object(s) as JSON in {len(self.paths)} file(s) (data/)"
        notes = []
        for kind, n in sorted(self.no_layout.items()):
            mono = kind == "MonoBehaviour"
            why = "their script layout is not in the build" if mono else "unreadable"
            notes.append(f"{n} {kind}(s) listed without their fields: {why}")
        return (summary if self.written else ""), notes


def layouts_off(env, dump, shared: dict) -> list[str]:
    """A rebuilt layout that does not fit its object reads a garbage length and asks for the
    machine's memory; the ceiling (doc 9.2) stops it. After one, the rebuilt layouts are not
    trusted for the rest of the export: said once, the remaining objects listed without fields."""
    if dump is None or not dump.exhausted or shared.get("generator") is None:
        return []
    shared["generator"] = env.typetree_generator = None
    gc.collect()
    return [
        "a rebuilt MonoBehaviour layout did not fit its object and asked for more memory than "
        "ViWo may take ([startup] memory_limit): the remaining MonoBehaviours are listed "
        "without their fields"
    ]


def assemblies(game_root: Path, ctx) -> tuple[Path | None, str]:
    """(the folder of assemblies that describe the game's scripts, "") or (None, why not)."""
    managed = next(iter(sorted(game_root.glob("*_Data/Managed"))), None)
    if managed is not None and any(managed.glob("*.dll")):
        return managed, ""
    if not any(game_root.glob("GameAssembly.*")):
        return None, "MonoBehaviour layouts unavailable: no managed assemblies and no IL2CPP build"
    tool = ctx.os.tools.locate(CPP2IL) if ctx is not None else None
    if tool is None:
        return None, f"IL2CPP: MonoBehaviour fields need Cpp2IL's stand-ins ({CPP2IL.hint})"
    out = Path(ctx.scratch) / "cpp2il-standins"
    argv = [*tool.argv_prefix, "--game-path", str(game_root), "--output-as", "dummydll"]
    ctx.log("Cpp2IL: stand-in assemblies for the MonoBehaviour layouts (IL2CPP)", stage="export")
    result = ctx.os.process.run([*argv, "--output-to", str(out)], timeout=1800, cancel=ctx.cancel)
    if not any(out.glob("*.dll")):
        why = (result.stderr or result.stdout or "").strip().splitlines()[-1:] or ["no output"]
        return None, f"IL2CPP: Cpp2IL wrote no stand-in assemblies ({why[0][:120]})"
    return out, ""


def layouts(env, game_root: Path, ctx=None):
    """(the MonoBehaviour layout generator, "") once per export, or (None, why not); the
    caller gives it to every environment it loads."""
    folder, why = assemblies(game_root, ctx)
    if folder is None:
        return None, why
    try:
        from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

        versions = (str(getattr(o.assets_file, "unity_version", "") or "") for o in env.objects)
        version = next((v for v in versions if v and v[0].isdigit()), "")
        if not version:
            return None, "MonoBehaviour layouts unavailable: no Unity version in these files"
        generator = TypeTreeGenerator(version)
        generator.load_local_dll_folder(str(folder))
    except Exception as exc:  # noqa: BLE001  (the generator is optional; say why it is absent)
        return None, f"MonoBehaviour layouts unavailable: {str(exc)[:120]}"
    return generator, ""
