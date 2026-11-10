"""Boot sequence (doc 9.3, prototype subset) and the Runtime facade."""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from viwo import CONTRACT_VERSION
from viwo.contracts.errors import ViwoError
from viwo.contracts.os import OS
from viwo.contracts.plugin import EnginePlugin
from viwo.contracts.slots import Backend, SlotBinding, SlotDefinition
from viwo.os import select_os

from .. import thirdparty
from .binder import bind_all
from .ini import StartupConfig, load_ini
from .registry import collect, core_sources, load_enabled

# Frozen build (viwo.exe): startup.ini sits next to the executable; otherwise the repo root.
_HOME = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[3]
)
DEFAULT_INI = _HOME / "startup.ini"
DISABLED = re.compile(r"^plugin ([a-z][a-z0-9_-]*)")  # the registry's own wording, read here only


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
    disabled: dict[str, str] = field(default_factory=dict)  # plugin id -> why it did not load

    def owner_options(self, owner: str) -> dict:
        return dict(self.config.options.get(owner, {}))

    def dependency_report(self) -> list[dict]:
        """v1 /api/dependencies items plus slot/backend detail (doc 4.2): `uses` names what each
        tool serves, the slots it backs, else its backends' families (analysis, runtime…)."""
        items, uses = [], {}
        backs = {}
        for sid, slot in self.slots.items():
            for bid in (slot.default_main, slot.default_spare):
                backs.setdefault(bid, set()).add(sid)
        for backend in self.backends.values():
            for spec in backend.dependencies():
                served = backs.get(backend.backend_id) or set(backend.families)
                uses.setdefault(spec.dep_id, set()).update(served)
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
                        "onDemand": thirdparty.on_demand(spec.dep_id),
                    }
                )
        unique = {item["id"]: {**item, "uses": sorted(uses.get(item["id"], ()))} for item in items}
        return sorted(unique.values(), key=lambda i: (i["category"], i["id"]))

    def info(self) -> dict:
        return {
            "os": self.os.os_id,
            "osName": self.os.display_name,
            "ini": self.config.source,
            "contract": CONTRACT_VERSION,  # what this ViWo implements
            "iniContract": self.config.contract,
            "features": list(self.config.features),
            "sources": dict(self.config.sources),  # doc 9.1: provenance of every value
            "plugins": sorted(self.plugins),
            "slots": {sid: b.__dict__ for sid, b in sorted(self.bindings.items())},
            "problems": list(self.problems),
        }


def _apply_profile(config, profile: str) -> None:
    """`--profile` (doc 9.1 value source 4): that distro's plugin set over the ini's."""
    from .distros import enabled_for, profiles

    if profile not in (known := profiles()):
        raise ViwoError("invalid_request", f"unknown profile {profile!r}; one of {known}")
    config.profile, config.plugins = profile, {**config.plugins, **enabled_for(profile)}
    config.sources["startup.profile"] = "cli"


def boot(
    ini_path: Path | None = None,
    os_id: str | None = None,
    temp_root: Path | None = None,
    profile: str | None = None,
    features: tuple[str, ...] | None = None,
) -> Runtime:
    config = load_ini(ini_path if ini_path is not None else DEFAULT_INI)
    if profile:
        _apply_profile(config, profile)
    if features is not None:  # `--features` (doc 9.1 value source cli) over [startup] features
        config.features, config.sources["startup.features"] = tuple(features), "cli"
    home = thirdparty.home_of(config)
    thirdparty.activate(home)  # pinned Python packages installed under third_party/python
    tools = {**thirdparty.found_tools(home), **config.tools}  # the ini wins over third_party/
    layer = select_os(os_id or config.os_id, tools)
    if os_id:
        config.sources["startup.os"] = "cli"
    plugins, problems = load_enabled(config.plugins, config.custom_dirs, layer.os_id)
    for plugin_id, plugin in plugins.items():
        plugin.home = home
        try:
            plugin.configure(config.options.get(plugin_id, {}))
        except Exception as exc:  # a bad option disables only that plugin's extras
            problems.append(f"plugin {plugin_id}: options rejected: {exc}")
    slots, backends, clash = collect(*core_sources(), plugins)
    bindings, bind_problems = bind_all(slots, backends, config.slots, layer)
    for binding in bindings.values():
        problems += list(binding.reasons)
    root = temp_root or config.server.temp  # one answer for the CLI and the server
    root.mkdir(parents=True, exist_ok=True)
    all_problems = config.problems + problems + clash + bind_problems
    disabled = {m.group(1): p for p in problems if (m := DISABLED.match(p))}
    return Runtime(config, layer, plugins, slots, backends, bindings, root, all_problems, disabled)
