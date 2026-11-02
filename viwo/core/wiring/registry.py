"""Built-in plugin registry and slot/backend collection (doc 8)."""

from __future__ import annotations

import importlib
from typing import Iterable

from viwo.contracts.plugin import EnginePlugin
from viwo.contracts.slots import Backend, SlotDefinition

BUILTIN_PLUGINS = {
    "generic": "viwo.plugins.generic:GenericPlugin",
    "renpy": "viwo.plugins.renpy:RenPyPlugin",
    "unity": "viwo.plugins.unity:UnityPlugin",
    "godot": "viwo.plugins.godot:GodotPlugin",
    "doom": "viwo.plugins.doom:DoomPlugin",
    "unreal": "viwo.plugins.unreal:UnrealPlugin",
    "rpgmaker": "viwo.plugins.rpgmaker:RpgMakerPlugin",
}


def load_plugin(entry: str) -> EnginePlugin:
    module_name, class_name = entry.split(":", 1)
    plugin = getattr(importlib.import_module(module_name), class_name)()
    if not isinstance(plugin, EnginePlugin):
        raise TypeError(f"{entry} is not an EnginePlugin")
    return plugin


def load_enabled(enabled: dict[str, bool]) -> tuple[dict[str, EnginePlugin], list[str]]:
    """Instantiate enabled built-ins; `generic` is always on. Errors disable a plugin."""
    plugins: dict[str, EnginePlugin] = {}
    problems: list[str] = []
    for plugin_id, entry in BUILTIN_PLUGINS.items():
        if plugin_id != "generic" and not enabled.get(plugin_id, True):
            continue
        try:
            plugins[plugin_id] = load_plugin(entry)
        except Exception as exc:  # a broken plugin must not stop the app (D2)
            problems.append(f"plugin {plugin_id} disabled: {exc}")
    for plugin_id in enabled:
        if plugin_id not in BUILTIN_PLUGINS:
            problems.append(f"unknown plugin '{plugin_id}' in [plugins] ignored")
    return plugins, problems


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
