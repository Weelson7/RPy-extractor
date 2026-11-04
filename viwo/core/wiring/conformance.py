"""Plugin manifest and slot conformance checks run at load (doc 2.9, 3.4): id slug,
contract major, engine type, option keys and kinds, OS layers, detect() purity on an
empty probe, dependency ids, capabilities, suffix clashes."""

from __future__ import annotations

import re
from pathlib import Path

from viwo import CONTRACT_VERSION
from viwo.contracts.plugin import OPTION_KINDS, EnginePlugin
from viwo.contracts.slots import SlotDefinition

RESERVED = {"mixed", "auto", "core", "none"}
SLUG = re.compile(r"[a-z][a-z0-9_-]{1,31}")
OS_LAYERS = {"windows", "linux"}
# doc 2.1; a manifest that declares none gets them derived
CAPABILITIES = tuple("detect unpack export pack decode inventory verify sanitize analyze".split())


class EmptyProbe:
    """Doc 2.8: the probe every plugin must survive at load (an empty game folder)."""

    root = Path(".")

    def has_name(self, *names: str) -> bool:
        return False

    def find(self, pattern: str, limit: int = 100) -> list[Path]:
        return []

    def with_suffix(self, *suffixes: str) -> list[Path]:
        return []

    def head(self, path: Path, size: int = 64) -> bytes:
        return b""

    def tail(self, path: Path, size: int = 64) -> bytes:
        return b""


def validate_plugin(plugin: EnginePlugin, os_id: str = "") -> list[str]:
    """Doc 2.9 checks that run at load for built-ins and drop-ins alike. A non-empty result
    disables the plugin; every message names what to fix."""
    m, problems = plugin.manifest, []
    if not SLUG.fullmatch(m.plugin_id) or m.plugin_id in RESERVED:
        problems.append(f"id '{m.plugin_id}' is not a valid slug")
    if str(m.contract).split(".")[0] != CONTRACT_VERSION.split(".")[0]:
        problems.append(f"contract {m.contract} does not match {CONTRACT_VERSION}")
    if not m.engine_type or not isinstance(m.engine_type, str):
        problems.append("engine_type is empty")
    keys = [o.key for o in m.options]
    if len(set(keys)) != len(keys):
        problems.append("option keys are not unique")
    problems += [
        f"option {o.key}: unknown kind {o.kind}" for o in m.options if o.kind not in OPTION_KINDS
    ]
    if os_id and m.os_layers and os_id not in m.os_layers:
        problems.append(f"not for this OS layer ({os_id}); declares {', '.join(m.os_layers)}")
    if any(layer not in OS_LAYERS for layer in m.os_layers):
        problems.append(f"unknown os_layers {m.os_layers}")
    try:
        first, second = plugin.detect(EmptyProbe()), plugin.detect(EmptyProbe())
        if first != second or (first.plugin_id and first.plugin_id != m.plugin_id):
            problems.append("detect() on an empty probe is not pure or names another plugin")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"detect() raised on an empty probe: {exc}")
    return problems + _dependency_problems(plugin) + _capability_problems(plugin)


def _capability_problems(plugin: EnginePlugin) -> list[str]:
    """Doc 2.9: declared capabilities are known, include detect, and unpack when the plugin
    ships `unarchive.*` slots. An empty declaration is derived (capabilities_of)."""
    caps = set(plugin.manifest.capabilities)
    problems = [f"unknown capability {c}" for c in sorted(caps - set(CAPABILITIES))]
    if caps and "detect" not in caps:
        problems.append("capabilities do not include detect")
    unpacks = any(s.family == "unarchive" for s in plugin.slot_definitions())
    if caps and unpacks and "unpack" not in caps:
        problems.append("unarchive slots need the unpack capability")
    return problems


def capabilities_of(plugin: EnginePlugin) -> tuple[str, ...]:
    """Declared capabilities, else derived from the hooks and slots the plugin ships."""
    declared = tuple(plugin.manifest.capabilities)
    if declared:
        return declared
    families = {s.family for s in plugin.slot_definitions()}
    caps = ["detect"]
    caps += ["unpack"] if "unarchive" in families else []
    caps += ["export"] if plugin.export_slot() else []
    caps += ["pack"] if "pack" in families else []
    caps += ["decode"] if "decode" in families else []
    caps += ["sanitize"] if plugin.sanitizer_rules() else []
    return tuple(caps)


def _dependency_problems(plugin: EnginePlugin) -> list[str]:
    """Dependency ids are unique per plugin: one id, one label (doc 2.9)."""
    seen: dict[str, str] = {}
    problems = []
    for backend in plugin.backends():
        for spec in backend.dependencies():
            if seen.setdefault(spec.dep_id, spec.label) != spec.label:
                problems.append(f"dependency {spec.dep_id} declared twice with different labels")
    return problems


def suffix_clashes(slots: dict[str, SlotDefinition]) -> list[str]:
    """Doc 3.4: two enabled plugins claiming one suffix is a boot problem naming the winner
    (the longest suffix, then registration order; magic bytes never break the tie)."""
    claims: dict[str, SlotDefinition] = {}
    problems = []
    for slot in slots.values():
        for suffix in slot.suffixes if slot.family == "unarchive" else ():
            first = claims.setdefault(suffix, slot)
            if first is not slot and first.owner != slot.owner:
                problems.append(
                    f"suffix {suffix}: {first.slot_id} ({first.owner}) and {slot.slot_id} "
                    f"({slot.owner}) both claim it; {first.slot_id} wins"
                )
    return problems
