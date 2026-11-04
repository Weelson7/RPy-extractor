"""SETTINGS: read the startup ini as a form and write it back; applied by reloading."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from viwo.contracts.errors import ViwoError
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
    path = ini_path(app)
    try:
        problems = write_settings(path, d)
    except ViwoError as exc:
        return {"success": False, "error": exc.message, "code": exc.code, "hint": exc.hint}
    app.reload()
    app.log(f"[SETTINGS] {path} updated: {', '.join(sorted(k for k in d if d[k])) or 'nothing'}")
    return {"success": True, "ini": str(path), "problems": problems, "effective": app.rt.info()}


SETTINGS_GET: dict[str, Callable[[App, dict], Any]] = {"/api/settings": get_settings}
SETTINGS_POST: dict[str, Callable[[App, dict], Any]] = {"/api/settings": save_settings}
