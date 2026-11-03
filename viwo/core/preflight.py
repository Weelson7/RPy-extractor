"""Startup preflight (doc 9): check every dependency, then install the missing ones
automatically into third_party/ (pinned versions, checksums verified). Fully automated: no
manual step. Every check and install is an event, so the landing screen shows real progress.
"""

from __future__ import annotations

import importlib.metadata

from viwo.contracts.errors import ViwoError
from viwo.contracts.types import ProgressEvent

from . import thirdparty
from .steps import teller

NO_RUN = {"rdpython", "datatool"}  # a GUI host or a slow start: never run just for a version


def _version_args(rt) -> dict[str, tuple[str, ...]]:
    """dep id -> how its backend pokes the tool (`Backend.self_check_args`, doc 8.6)."""
    return {
        spec.dep_id: backend.self_check_args
        for backend in rt.backends.values()
        for spec in backend.dependencies()
    }


def _version(rt, item: dict) -> str:
    if not item["available"]:
        return ""
    if item["kind"] == "python":
        name = thirdparty.manifest()["python"].get(item["id"], item["id"]).split("==")[0]
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return ""
    pinned = thirdparty.installed_version(item["id"], thirdparty.home_of(rt.config))
    if pinned or item["id"] in NO_RUN:
        return pinned
    args = _version_args(rt).get(item["id"], ("--version",))
    result = rt.os.process.run([item["location"], *args], timeout=4)
    text = (result.stdout or result.stderr or "").strip().splitlines()
    return text[0][:80] if text else ""


def check(rt, say) -> list[dict]:
    items = rt.dependency_report()
    for index, item in enumerate(items, 1):
        item["version"] = _version(rt, item)
        state = f"found {item['version']}".strip() if item["available"] else "missing"
        say(
            ProgressEvent(
                f"Checking {item['label']} ({index}/{len(items)}): {state}", "info", "core", "check"
            )
        )
    return items


def install(rt, dep_id: str, sink=None, cancel=None) -> dict:
    """Install one dependency into third_party/ (automated; nothing is asked of the user)."""
    say = teller(sink, "install")
    item = next((i for i in rt.dependency_report() if i["id"] == dep_id), None)
    if item is None or not thirdparty.installable(dep_id, item["kind"]):
        raise ViwoError("unavailable", f"{dep_id} has no automatic install on this platform")
    home = thirdparty.home_of(rt.config)
    if say:
        say(f"Installing {item['label']} into {home / 'third_party'}")
    if item["kind"] == "python":
        done = thirdparty.install_python(dep_id, home, rt.os.process)
    else:
        done = thirdparty.install_tool(dep_id, home, rt.os.process, say, cancel)
    if say:
        say(f"Installed {item['label']}")
    return {"installed": dep_id, "where": done}


def _event(message: str, stage: str, level: str = "info") -> ProgressEvent:
    return ProgressEvent(message, level, "core", stage)


def _install_missing(rt, todo: list[dict], sink, cancel) -> tuple[list[str], list[str]]:
    say, installed, failed = sink or (lambda e: None), [], []
    for index, item in enumerate(todo, 1):
        say(_event(f"Installing missing tools ({index}/{len(todo)}): {item['label']}", "install"))
        try:
            install(rt, item["id"], sink, cancel)
            installed.append(item["id"])
        except ViwoError as exc:
            failed.append(f"{item['label']}: {exc.message}")
            say(_event(f"Could not install {item['label']}: {exc.message}", "install", "warn"))
    return installed, failed


def preflight(rt, sink=None, cancel=None) -> dict:
    """Checks, then (auto_install = on, the default) installs everything missing that can be."""
    say = sink or (lambda e: None)
    say(_event(f"Loaded {len(rt.plugins)} engine plugins, {len(rt.slots)} formats", "boot"))
    items = check(rt, say)
    missing = [i for i in items if not i["available"] and i["installable"] and not i["onDemand"]]
    todo = missing if rt.config.auto_install else []
    installed, failed = _install_missing(rt, todo, sink, cancel)
    ready = sum(1 for i in items if i["available"]) + len(installed)
    say(_event(f"Ready: {ready}/{len(items)} tools available", "ready"))
    result = {"dependencies": items, "installed": installed, "failed": failed, "ready": ready}
    return {**result, "total": len(items), "problems": list(rt.problems)}


def strict_problems(rt) -> list[str]:
    """strict_preflight = on (doc 9.3 step 9): every enabled plugin's slots need a main backend."""
    problems = []
    for plugin_id, plugin in sorted(rt.plugins.items()):
        for slot in plugin.slot_definitions():
            binding = rt.bindings.get(slot.slot_id)
            if binding is not None and not binding.bound:
                problems.append(f"plugin {plugin_id}: {slot.slot_id} has no backend (tool missing)")
    return problems
