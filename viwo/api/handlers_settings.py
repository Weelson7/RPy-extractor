"""SETTINGS: read the startup ini as a form and write it back; applied by reloading."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from viwo.contracts.errors import ViwoError
from viwo.core.preflight import feature_tools, install
from viwo.core.steps import tell
from viwo.core.wiring.boot import DEFAULT_INI
from viwo.core.wiring.registry import BUILTIN_PLUGINS, load_plugin
from viwo.core.wiring.settings import read_settings, write_settings

from .app import App


def ini_path(app: App) -> Path:
    return app.rt.config.path or DEFAULT_INI


def _plugin_info(app: App) -> dict[str, dict]:
    """Every known plugin (built-in or drop-in, loaded or not): name, engine type, TOS flag,
    non-secret options; a broken one is listed with its problem, never hidden."""
    out: dict[str, dict] = {}
    for plugin_id in sorted(set(BUILTIN_PLUGINS) | set(app.rt.plugins)):
        try:
            plugin = app.rt.plugins.get(plugin_id) or load_plugin(BUILTIN_PLUGINS[plugin_id])
            m = plugin.manifest
        except Exception as exc:  # noqa: BLE001
            out[plugin_id] = {"name": plugin_id, "problem": str(exc), "options": []}
            continue
        out[plugin_id] = {
            "name": m.name,
            "engineType": m.engine_type,
            "engine": m.engine,  # a game plugin: the engine plugin it belongs to (doc 2.10)
            "tosSensitive": m.tos_sensitive,
            "options": [o.__dict__ for o in m.options if o.kind != "secret"],
            "custom": plugin_id not in BUILTIN_PLUGINS,
        }
    return out


def get_settings(app: App, q: dict) -> dict:
    path = ini_path(app)
    try:
        dep_ids = [item["id"] for item in app.rt.dependency_report()]
        data = read_settings(path, sorted(BUILTIN_PLUGINS), dep_ids)
    except ViwoError as exc:
        return {"success": False, "error": exc.message, "code": exc.code, "hint": exc.hint}
    return {"success": True, **data, "pluginInfo": _plugin_info(app), "effective": app.rt.info()}


def save_settings(app: App, d: dict) -> dict:
    """Write the given keys, reload the runtime, report the new state and every problem."""
    path, before = ini_path(app), set(app.rt.config.features)
    try:
        problems = write_settings(path, d)
    except ViwoError as exc:
        return {"success": False, "error": exc.message, "code": exc.code, "hint": exc.hint}
    app.reload()
    app.log(f"[SETTINGS] {path} updated: {', '.join(sorted(k for k in d if d[k])) or 'nothing'}")
    turned_on = sorted(set(app.rt.config.features) - before)
    tools = [t for f in turned_on for t in feature_tools(app.rt, f)]
    job = _install_job(app, list(dict.fromkeys(tools))) if tools else None
    return {"success": True, "ini": str(path), "problems": problems, "effective": app.rt.info(),
            "installing": tools, "installJob": job}  # fmt: skip


def _install_job(app: App, tools: list[str]) -> str:
    """A feature just turned on: its tools install by themselves as one visible job."""

    def run(jid, sink, cancel) -> dict:
        done, failed = [], []
        for dep in tools:
            try:
                done.append(install(app.rt, dep, sink, cancel)["installed"])
            except ViwoError as exc:  # said in the log and the job, never a green job
                failed.append(f"{dep}: {exc.message}")
                tell(sink, f"Could not install {dep}: {exc.message}", "install", "warn")
        app.reload()
        if failed:
            installed = f"; installed: {', '.join(done)}" if done else ""
            raise ViwoError("failed", f"not installed: {'; '.join(failed)}{installed}")
        return {"success": True, "installed": done, "failed": []}

    listener = lambda e: app.log(e.legacy_line())  # noqa: E731
    return app.jobs.submit_with_listener(listener, "install", run, background=True).job_id


SETTINGS_GET: dict[str, Callable[[App, dict], Any]] = {"/api/settings": get_settings}
SETTINGS_POST: dict[str, Callable[[App, dict], Any]] = {"/api/settings": save_settings}
