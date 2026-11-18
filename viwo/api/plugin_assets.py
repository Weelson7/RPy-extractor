"""Plugin UI add-ons: ES modules served from each plugin's own folder (docs/plugins.md).

`/plugins/<id>/ui.js` is the module a plugin declares (`EnginePlugin.ui_module()`); any other
file comes only from the `ui/` folder next to that module. Static code like the app's own JS:
no token, but strict path containment (`safe_member` + `inside`).
"""

import threading
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.workspace import inside, safe_member
from viwo.core import thirdparty

PREFIX = "/plugins/"
VENDOR = {"/vendor/model-viewer.min.js": "model-viewer"}  # pinned scripts the page may load
_INSTALL = threading.Lock()  # one install at a time, whatever the page asks for at once


def ui_modules(rt) -> list[dict]:
    """[{plugin, url}] for every loaded plugin that ships a UI module."""
    return [
        {"plugin": plugin_id, "url": f"{PREFIX}{plugin_id}/ui.js"}
        for plugin_id, plugin in sorted(rt.plugins.items())
        if plugin.ui_module() is not None
    ]


def resolve(rt, path: str) -> Path | None:
    """The file behind /plugins/<id>/<rel>, or None: unknown plugin, no module, outside ui/."""
    if not path.startswith(PREFIX):
        return None
    plugin_id, _, rel = path[len(PREFIX) :].partition("/")
    plugin = rt.plugins.get(plugin_id)
    module = plugin.ui_module() if plugin is not None else None
    member = safe_member(rel) if rel else None
    if module is None or member is None:
        return None
    if str(member) == "ui.js":
        return module
    if member.parts[0] != "ui" or len(member.parts) < 2:
        return None
    folder = module.parent / "ui"
    target = folder.joinpath(*member.parts[1:])
    ok = folder.is_dir() and inside(folder, target) and target.is_file()
    return target if ok else None


def vendor(rt, path: str) -> Path | None:
    """The pinned script behind /vendor/<name>, under third_party/. Not there yet: installed
    now, off screen (minimal prompts; `auto_install` off leaves it out), else None."""
    home, tool = thirdparty.home_of(rt.config), VENDOR[path]
    target = home / "third_party" / tool / path.rsplit("/", 1)[-1]
    with _INSTALL:
        if not target.is_file() and rt.config.auto_install:
            try:
                thirdparty.install_tool(tool, home, rt.os.process)
            except (ViwoError, OSError):
                return None  # the page says the viewer is missing and why that can be
    return target if target.is_file() else None


def serve(handler, path: str) -> bool:
    """Answer a GET for a plugin asset or a pinned script; False when the path is neither."""
    if not path.startswith(PREFIX) and path not in VENDOR:
        return False
    rt = handler.app.rt
    target = vendor(rt, path) if path in VENDOR else resolve(rt, path)
    if target is None:
        handler.send_error(404)
    else:
        handler.send_file(target)
    return True
