"""The technical PDF's reference tables, generated from the code so they never drift: engine
plugins and their slots by arm, every slot with its bound backends, the pinned third-party
tools, the CLI commands, the HTTP routes and the conformance summary."""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ARMS = {  # slot family -> the arm it serves
    "unarchive": "static", "export": "static", "decode": "static", "carve": "static",
    "probe": "static", "analysis": "static", "handoff": "static", "media.encode": "static",
    "capture": "dynamic", "runtime": "dynamic", "attach": "dynamic", "pack": "patching",
    "patch": "patching",
}  # fmt: skip


def esc(text) -> str:
    return html.escape(str(text))


def table(head: tuple[str, ...], rows: list[tuple]) -> str:
    """An HTML table; cells are escaped, a cell wrapped in a 1-tuple is code."""

    def cell(value) -> str:
        return f"<code>{esc(value[0])}</code>" if isinstance(value, tuple) else esc(value)

    top = "".join(f"<th>{esc(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{cell(v)}</td>" for v in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{top}</tr></thead><tbody>{body}</tbody></table>"


def plugins() -> list[tuple]:
    from viwo.core.wiring.registry import BUILTIN_PLUGINS, load_plugin

    rows = []
    for pid, entry in sorted(BUILTIN_PLUGINS.items()):
        plugin = load_plugin(entry)
        by_arm: dict[str, list[str]] = {"static": [], "dynamic": [], "patching": []}
        for slot in plugin.slot_definitions():
            by_arm[ARMS.get(slot.family, "static")].append(slot.slot_id)
        cells = [", ".join(v) or "-" for v in by_arm.values()]
        note = " (ToS reminder on every run)" if plugin.manifest.tos_sensitive else ""
        rows.append(((pid,), plugin.manifest.name + note, *cells))
    return rows


def slots(rt) -> list[tuple]:
    rows = []
    for slot_id, slot in sorted(rt.slots.items()):
        bound = rt.bindings.get(slot_id)
        main, spare = (bound.main or "-", bound.spare or "-") if bound else ("-", "-")
        what = " ".join(slot.suffixes[:6]) + (" ..." if len(slot.suffixes) > 6 else "")
        rows.append(((slot_id,), ARMS.get(slot.family, "static"), slot.owner, main, spare, what))
    return rows


def tools() -> list[tuple]:
    from viwo.core import thirdparty

    rows = []
    for dep_id, entry in sorted(thirdparty.manifest().get("tools", {}).items()):
        if dep_id.startswith("_") or not isinstance(entry, dict):
            continue
        spec = thirdparty.spec_of(dep_id) or {}
        size = f"{spec['size'] / 1e6:.1f} MB" if spec.get("size") else "-"
        when = "when asked" if entry.get("on_demand") else "first start"
        rows.append(((dep_id,), entry.get("version", "-"), entry.get("license", "-"), size, when))
    return rows


def commands(rt) -> list[tuple]:
    from viwo.cli import _parser

    rows, seen = [], set()
    ap = _parser(rt)
    for action in ap._subparsers._group_actions:  # argparse keeps sub-commands here
        for choice in action._choices_actions:
            if choice.dest not in seen:
                seen.add(choice.dest)
                rows.append(((f"viwo {choice.dest}",), choice.help or ""))
    return rows


def routes() -> list[tuple]:
    from viwo.api.handlers import GET, POST

    names = [(r, "GET") for r in GET] + [(r, "POST") for r in POST]
    return [((route,), method) for route, method in sorted(names)]


def conformance() -> dict[str, int]:
    """Rows per state in CONFORMANCE.md (the summary table itself not counted)."""
    text = (ROOT / "docs" / "contract" / "CONFORMANCE.md").read_text(encoding="utf-8")
    body = text.split("## Summary", 1)[1].split("\n## ", 1)[1]
    found = re.findall(r"^\|[^|\n]+\| (implemented|partial|open)\b", body, re.M)
    return {state: found.count(state) for state in ("implemented", "partial", "open")}


def all_tables(rt) -> dict[str, str]:
    return {
        "plugins_table": table(("Plugin", "Engine", "Static", "Dynamic", "Patching"), plugins()),
        "slots_table": table(("Slot", "Arm", "Owner", "Main", "Spare", "Handles"), slots(rt)),
        "tools_table": table(("Tool", "Version", "License", "Download", "Installed"), tools()),
        "cli_table": table(("Command", "What it does"), commands(rt)),
        "routes_table": table(("Route", "Method"), routes()),
    }
