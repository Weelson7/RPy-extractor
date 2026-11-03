"""Handlers for plugin add-ons: which UI modules the web app has to load."""

from __future__ import annotations

from typing import Any, Callable

from .app import App
from .plugin_assets import ui_modules


def list_ui_modules(app: App, q: dict) -> dict:
    return {"success": True, "modules": ui_modules(app.rt)}


PLUGINS_GET: dict[str, Callable[[App, dict], Any]] = {"/api/ui-modules": list_ui_modules}
