"""Plugin registry and slot/backend collection (doc 8; revised for 1.0: nothing hardcoded).

Built-ins are discovered by scanning the packages under `viwo.plugins`; drop-in plugins come
from the folders listed in `[plugins] custom_dirs` (each carrying a `plugin.json`, doc 2.8) and
from the `viwo.plugins` entry-point group of installed packages. Every plugin is known by its
manifest id. A broken plugin disables only itself (D2).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import inspect
import json
import pkgutil
import re
import sys
from pathlib import Path
from typing import Callable, Iterable

import viwo.plugins as _builtins
from viwo import __version__
from viwo.contracts.plugin import CliCommand, EnginePlugin
from viwo.contracts.slots import Backend, SlotDefinition
from viwo.contracts.workspace import safe_member

ALWAYS_ON = "generic"
ENTRY_POINT_GROUP = "viwo.plugins"
RESERVED = {"mixed", "auto", "core", "none"}
_REQ = re.compile(r"^\s*(>=|<=|==|>|<)?\s*(\d+(?:\.\d+){0,2})\s*$")
DISCOVERY_PROBLEMS: list[str] = []
Factory = Callable[[], EnginePlugin]


def plugin_class(module, wanted: str = "") -> type[EnginePlugin]:
    """The plugin class of a module: `wanted`, the `PLUGIN` marker, or its one subclass."""
    name = wanted or getattr(module, "PLUGIN", "")
    if name:
        return getattr(module, name)
    found = [
        cls
        for _, cls in inspect.getmembers(module, inspect.isclass)
        if issubclass(cls, EnginePlugin)
        and cls is not EnginePlugin
        and cls.__module__ == module.__name__
    ]
    if len(found) != 1:
        raise TypeError(f"{module.__name__}: expected one EnginePlugin class, found {len(found)}")
    return found[0]


def _discover_builtins() -> dict[str, str]:
    """Manifest id -> "module:Class" for every package under viwo.plugins.

    pkgutil (not a folder scan): inside the frozen build (viwo.exe) the packages live in the
    PYZ archive and PyInstaller's importer lists them through iter_modules."""
    out: dict[str, str] = {}
    for info in sorted(pkgutil.iter_modules(_builtins.__path__), key=lambda i: i.name):
        if not info.ispkg:
            continue
        module_name = f"{_builtins.__name__}.{info.name}"
        try:
            cls = plugin_class(importlib.import_module(module_name))
            plugin_id = cls().manifest.plugin_id
        except Exception as exc:  # a broken built-in must not stop the app (D2)
            DISCOVERY_PROBLEMS.append(f"plugin {info.name} disabled: {exc}")
            continue
        if plugin_id != info.name:
            DISCOVERY_PROBLEMS.append(f"plugin {info.name}: manifest id is '{plugin_id}'")
        out[plugin_id] = f"{module_name}:{cls.__name__}"
    return out


BUILTIN_PLUGINS: dict[str, str] = _discover_builtins()


def load_plugin(entry: str) -> EnginePlugin:
    module_name, class_name = entry.split(":", 1)
    plugin = getattr(importlib.import_module(module_name), class_name)()
    if not isinstance(plugin, EnginePlugin):
        raise TypeError(f"{entry} is not an EnginePlugin")
    return plugin


def version_ok(requirement: str, version: str = __version__) -> bool:
    """`>=1.0`, `==1.2.3`, `<2` ... against the running ViWo version (missing parts = 0)."""
    match = _REQ.match(requirement)
    if match is None:
        return False
    op, wanted = match.group(1) or ">=", [int(x) for x in match.group(2).split(".")]
    have = [int(x) for x in version.split(".")][: len(wanted)]
    compare = {">=": have >= wanted, "<=": have <= wanted, "==": have == wanted}
    return {**compare, ">": have > wanted, "<": have < wanted}[op]


def read_manifest(folder: Path) -> dict:
    """plugin.json of a drop-in folder, validated (doc 2.8; `entry` or `module` + `class`)."""
    meta = json.loads((folder / "plugin.json").read_text(encoding="utf-8"))
    if "entry" in meta and ("module" not in meta or "class" not in meta):
        meta["module"], _, meta["class"] = str(meta["entry"]).partition(":")
    for key in ("id", "module", "class"):
        if not isinstance(meta.get(key), str) or not meta[key]:
            raise ValueError(f"plugin.json needs a string '{key}'")
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", meta["id"]) or meta["id"] in RESERVED:
        raise ValueError(f"plugin id '{meta['id']}' is not a valid slug")
    for name, requirement in dict(meta.get("requires", {})).items():
        if name == "viwo" and not version_ok(str(requirement)):
            raise ValueError(f"needs viwo {requirement}, this is {__version__}")
    ui = meta.get("ui")
    if ui is not None and (not isinstance(ui, str) or safe_member(ui) is None):
        raise ValueError("'ui' must be a relative file inside the plugin folder")
    return meta


def load_dropin(folder: Path, meta: dict) -> EnginePlugin:
    """Import the plugin module from its own folder and instantiate the declared class."""
    target = folder / meta["module"]
    target = target / "__init__.py" if target.is_dir() else target.with_suffix(".py")
    if not target.is_file():
        raise FileNotFoundError(f"module {meta['module']} not found in {folder}")
    name = f"viwo_dropin_{meta['id']}"
    search = [str(target.parent)] if target.name == "__init__.py" else None
    spec = importlib.util.spec_from_file_location(name, target, submodule_search_locations=search)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    plugin = getattr(module, meta["class"])()
    if not isinstance(plugin, EnginePlugin):
        raise TypeError(f"{meta['class']} is not an EnginePlugin")
    if plugin.manifest.plugin_id != meta["id"]:
        raise ValueError(f"manifest id '{plugin.manifest.plugin_id}' differs from '{meta['id']}'")
    plugin.cli_enabled = bool(meta.get("cli", False))  # CLI add-ons are an explicit opt-in
    if meta.get("ui"):
        plugin.ui_path = folder / str(meta["ui"])
    return plugin


def dropin_manifests(custom_dirs: Iterable[Path], problems: list[str]) -> dict[str, tuple]:
    """id -> (factory, meta) for every plugin.json under the custom dirs, then entry points."""
    found: dict[str, tuple[Factory, dict]] = {}
    for root in custom_dirs:
        for folder in sorted(p for p in Path(root).glob("*") if (p / "plugin.json").is_file()):
            try:
                meta = read_manifest(folder)
            except Exception as exc:  # noqa: BLE001 (any manifest problem disables it)
                problems.append(f"plugin {folder.name} ({root}) disabled: {exc}")
                continue
            found[meta["id"]] = ((lambda f=folder, m=meta: load_dropin(f, m)), meta)
    for ep in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
        found.setdefault(ep.name, ((lambda e=ep: e.load()()), {"id": ep.name, "enabled": True}))
    return found


def _wanted(enabled: dict[str, bool], plugin_id: str, meta: dict) -> bool:
    for key in (plugin_id, f"custom.{plugin_id}"):
        if key in enabled:
            return enabled[key]
    return bool(meta.get("enabled", False))  # drop-ins are opt-in (doc 9.2)


def load_enabled(
    enabled: dict[str, bool], custom_dirs: Iterable[Path] = ()
) -> tuple[dict[str, EnginePlugin], list[str]]:
    """Instantiate enabled built-ins and drop-ins; `generic` is always on."""
    plugins: dict[str, EnginePlugin] = {}
    problems: list[str] = list(DISCOVERY_PROBLEMS)
    for plugin_id, entry in BUILTIN_PLUGINS.items():
        if plugin_id != ALWAYS_ON and not enabled.get(plugin_id, True):
            continue
        try:
            plugins[plugin_id] = load_plugin(entry)
        except Exception as exc:  # a broken plugin must not stop the app (D2)
            problems.append(f"plugin {plugin_id} disabled: {exc}")
    external = dropin_manifests(custom_dirs, problems)
    for plugin_id, (make, meta) in external.items():
        if not _wanted(enabled, plugin_id, meta):
            continue
        if plugin_id in plugins and not meta.get("override"):
            problems.append(
                f"plugin {plugin_id}: a built-in has this id; set override in plugin.json"
            )
            continue
        try:
            plugins[plugin_id] = make()
        except Exception as exc:  # noqa: BLE001
            problems.append(f"plugin {plugin_id} disabled: {exc}")
    for plugin_id in enabled:
        name = plugin_id.removeprefix("custom.")
        if name not in BUILTIN_PLUGINS and name not in external:
            problems.append(f"unknown plugin '{plugin_id}' in [plugins] ignored")
    return plugins, problems


def cli_commands(
    plugins: dict[str, EnginePlugin], core: Iterable[str]
) -> tuple[dict[str, tuple[str, CliCommand]], list[str]]:
    """name -> (plugin id, command) for every plugin add-on; a clash needs `override`."""
    taken, found, problems = set(core), {}, []
    for plugin_id, plugin in sorted(plugins.items()):
        commands = list(plugin.cli_commands())
        if commands and not plugin.cli_enabled:
            problems.append(f'plugin {plugin_id}: CLI commands ignored (set "cli": true)')
            continue
        for cmd in commands:
            if (cmd.name in taken or cmd.name in found) and not cmd.override:
                problems.append(
                    f"plugin {plugin_id}: command '{cmd.name}' exists; set override to replace it"
                )
                continue
            found[cmd.name] = (plugin_id, cmd)
    return found, problems


def known_ids(custom_dirs: Iterable[Path] = ()) -> set[str]:
    """Every plugin id a config may name: built-ins, drop-ins and entry points."""
    return set(BUILTIN_PLUGINS) | set(dropin_manifests(custom_dirs, []))


def collect(
    core_slots: Iterable[SlotDefinition],
    core_backends: Iterable[Backend],
    plugins: dict[str, EnginePlugin],
) -> tuple[dict[str, SlotDefinition], dict[str, Backend], list[str]]:
    slots: dict[str, SlotDefinition] = {}
    backends: dict[str, Backend] = {}
    problems: list[str] = []
    sources = [("core", list(core_slots), list(core_backends))]
    sources += [(pid, p.slot_definitions(), p.backends()) for pid, p in plugins.items()]
    for owner, owned_slots, owned_backends in sources:
        for slot in owned_slots:
            if slot.slot_id in slots:
                problems.append(f"slot {slot.slot_id} from {owner} clashes; ignored")
                continue
            slots[slot.slot_id] = slot
        for backend in owned_backends:
            if backend.backend_id in backends:
                problems.append(f"backend {backend.backend_id} from {owner} clashes; ignored")
                continue
            backends[backend.backend_id] = backend
    return slots, backends, problems
