"""Run-record context (doc 12.3): the effective ini, the slot bindings and each tool's version,
so that "same record + same tools" is checkable from the record alone. Cheap: no tool is run;
versions come from the pins (third_party/) or from the cached location."""

from __future__ import annotations

from viwo import __version__

from . import thirdparty


def record_context(rt) -> dict:
    """What a run record stores next to the request and the result."""
    home = thirdparty.home_of(rt.config)
    tools = {}
    for item in rt.dependency_report():
        if not item["available"]:
            continue
        pinned = thirdparty.installed_version(item["id"], home)
        tools[item["id"]] = {
            "version": pinned or item.get("version", "") or "",
            "location": item["location"],
            "kind": item["kind"],
        }
    sources = getattr(rt.config, "sources", None)
    return {
        "viwo": __version__,
        "ini": str(rt.config.source),
        "ini_values": dict(sources) if isinstance(sources, dict) else {},
        "bindings": {
            sid: {"main": b.main, "spare": b.spare, "promoted": b.promoted}
            for sid, b in sorted(rt.bindings.items())
        },
        "tools": tools,
    }
