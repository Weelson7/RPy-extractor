"""Boot sequence (doc 9.3, prototype subset) and the Runtime facade."""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from viwo.backends import CORE_SLOTS, core_backends
from viwo.contracts.os import OS
from viwo.contracts.plugin import EnginePlugin
from viwo.contracts.slots import Backend, SlotBinding, SlotDefinition
from viwo.os import select_os

from .. import thirdparty
from .binder import bind_all
from .ini import StartupConfig, load_ini
from .registry import collect, load_enabled

# Frozen build (viwo.exe): startup.ini sits next to the executable; otherwise the repo root.
_HOME = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[3]
)
DEFAULT_INI = _HOME / "startup.ini"


@dataclass
class Runtime:
    config: StartupConfig
    os: OS
    plugins: dict[str, EnginePlugin]
    slots: dict[str, SlotDefinition]
    backends: dict[str, Backend]
    bindings: dict[str, SlotBinding]
    temp_root: Path
    problems: list[str] = field(default_factory=list)

    def owner_options(self, owner: str) -> dict:
        return dict(self.config.options.get(owner, {}))

    def dependency_report(self) -> list[dict]:
        """v1 /api/dependencies items plus slot/backend detail (doc 4.2)."""
        items = []
        for backend in self.backends.values():
            for spec in backend.dependencies():
                found = self.os.tools.locate(spec)
                items.append(
                    {
                        "id": spec.dep_id,
                        "label": spec.label,
                        "kind": spec.kind,
                        "available": found is not None,
                        "required": False,
                        "category": backend.owner,
                        "requirement": spec.requirement.value,
                        "location": found.path if found else "",
                        "hint": spec.hint,
                        "installable": thirdparty.installable(spec.dep_id, spec.kind),
                    }
                )
        unique = {item["id"]: item for item in items}
        return sorted(unique.values(), key=lambda i: (i["category"], i["id"]))

    def info(self) -> dict:
        return {
            "os": self.os.os_id,
            "osName": self.os.display_name,
            "ini": self.config.source,
            "contract": self.config.contract,
            "sources": dict(self.config.sources),  # doc 9.1: provenance of every value
            "plugins": sorted(self.plugins),
            "slots": {sid: b.__dict__ for sid, b in sorted(self.bindings.items())},
            "problems": list(self.problems),
        }

    def self_checks(self) -> dict[str, tuple[bool, str]]:
        """`viwo slots --check` (doc 14.6): every bound backend's own self test."""
        wanted = {b.main for b in self.bindings.values()} | {
            b.spare for b in self.bindings.values()
        }
        return {
            bid: self.backends[bid].self_check(self.os)
            for bid in sorted(wanted)
            if bid in self.backends
        }


def boot(
    ini_path: Path | None = None,
    os_id: str | None = None,
    temp_root: Path | None = None,
) -> Runtime:
    config = load_ini(ini_path if ini_path is not None else DEFAULT_INI)
    home = thirdparty.home_of(config)
    thirdparty.activate(home)  # pinned Python packages installed under third_party/python
    tools = {**thirdparty.found_tools(home), **config.tools}  # the ini wins over third_party/
    scripts = home / "third_party" / "quickbms" / "scripts"
    if scripts.is_dir() and not config.options.get("quickbms", {}).get("scripts"):
        config.options.setdefault("quickbms", {})["scripts"] = str(scripts)
    layer = select_os(os_id or config.os_id, tools)
    if os_id:
        config.sources["startup.os"] = "cli"
    plugins, problems = load_enabled(config.plugins, config.custom_dirs, layer.os_id)
    for plugin_id, plugin in plugins.items():
        try:
            plugin.configure(config.options.get(plugin_id, {}))
        except Exception as exc:  # a bad option disables only that plugin's extras
            problems.append(f"plugin {plugin_id}: options rejected: {exc}")
    from viwo.core.capture import SLOTS as CAPTURE_SLOTS
    from viwo.core.capture import backends as capture_backends
    from viwo.core.decode import SLOTS as DECODE_SLOTS
    from viwo.core.decode import decoders

    slots, backends, clash = collect(
        CORE_SLOTS + DECODE_SLOTS + CAPTURE_SLOTS,
        core_backends() + decoders() + capture_backends(),
        plugins,
    )
    bindings, bind_problems = bind_all(slots, backends, config.slots, layer)
    for binding in bindings.values():
        problems += list(binding.reasons)
    root = temp_root or Path(tempfile.gettempdir()) / "viwo"
    root.mkdir(parents=True, exist_ok=True)
    all_problems = config.problems + problems + clash + bind_problems
    return Runtime(config, layer, plugins, slots, backends, bindings, root, all_problems)
