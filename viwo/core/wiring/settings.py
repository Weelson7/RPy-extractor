"""Settings for the GUI (doc 9.6): the startup ini as a form, written back key by key.

`read_settings` turns the ini into plain values; `write_settings` rewrites ONLY the keys given,
in place, keeping comments and lines it does not know, then validates the result with `load_ini`
before replacing the file. Changes apply by reloading the runtime (App.reload), never a restart.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from viwo.contracts.errors import ViwoError

from .ini import FORM_KEYS, SECRET_WORDS, load_ini

KEY_LINE = re.compile(r"^(\s*)([^;#=\s\[][^=]*?)\s*=\s*(.*?)(\s*[;#].*)?$")
SAFE_KEY = re.compile(r"^[a-z0-9_.-]+$")
Values = dict[str, "str | None"]  # None removes the key


def read_settings(ini_path: Path, plugin_ids, dep_ids) -> dict:
    """The effective ini as form values (plugins default to on, tools to auto = "")."""
    cfg = load_ini(ini_path)
    return {
        "ini": str(ini_path),
        "startup": {
            "os": cfg.os_id,
            "profile": cfg.profile,
            "features": list(cfg.features),
            "auto_install": cfg.auto_install,
            "strict_preflight": cfg.strict_preflight,
            "av_exclusions": cfg.av_exclusions,
        },
        "plugins": {pid: cfg.plugins.get(pid, True) for pid in plugin_ids},
        "tools": {dep: cfg.tools.get(dep, "") for dep in dep_ids},
        "options": {owner: dict(opts) for owner, opts in cfg.options.items()},
        "slots": {sid: list(pair) for sid, pair in cfg.slots.items()},
        "problems": list(cfg.problems),
    }


def _render(value) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def _flatten(changes: dict) -> tuple[dict[str, Values], list[str]]:
    """Form changes -> {section: {key: value | None}}; secret-looking option keys are refused."""
    out: dict[str, Values] = {}
    problems: list[str] = []
    for key, value in (changes.get("startup") or {}).items():
        if key in FORM_KEYS:
            out.setdefault("startup", {})[key] = _render(value)
    for pid, on in (changes.get("plugins") or {}).items():
        out.setdefault("plugins", {})[str(pid).lower()] = "on" if on else "off"
    for dep, path in (changes.get("tools") or {}).items():
        out.setdefault("tools", {})[str(dep).lower()] = _render(path) or None
    for owner, opts in (changes.get("options") or {}).items():
        for key, value in (opts or {}).items():
            if any(word in str(key).lower() for word in SECRET_WORDS):
                problems.append(f"[options.{owner}] {key}: secrets are not allowed in the ini")
                continue
            out.setdefault(f"options.{owner}", {})[str(key)] = _render(value) or None
    for section, values in out.items():
        for key in values:
            if not SAFE_KEY.match(key) or not SAFE_KEY.match(section):
                problems.append(f"[{section}] {key}: not a valid ini key")
    return out, problems


def _pending(values: Values, done: set[str]) -> list[str]:
    return [f"{k} = {v}" for k, v in values.items() if k not in done and v is not None]


def _apply(lines: list[str], section: str, values: Values) -> list[str]:
    """Replace the keys inside [section] in place (comments kept), add the rest, or the section."""
    out: list[str] = []
    current, done, seen = "", set(), False
    for line in lines:
        head = line.strip()
        if head.startswith("[") and head.endswith("]"):
            if current == section:
                out += _pending(values, done)
            current = head[1:-1].strip()
            seen = seen or current == section
            out.append(line)
            continue
        match = KEY_LINE.match(line) if current == section else None
        key = match.group(2).strip().lower() if match else ""
        if match and key in values and key not in done:
            done.add(key)
            if values[key] is not None:
                out.append(f"{match.group(1)}{key} = {values[key]}{match.group(4) or ''}")
            continue
        out.append(line)
    if current == section:
        out += _pending(values, done)
    if not seen:
        out += ["", f"[{section}]", *_pending(values, done)]
    return out


def write_settings(ini_path: Path, changes: dict) -> list[str]:
    """Rewrite only the given keys; validate on a temp copy first. Returns problems (soft)."""
    sections, problems = _flatten(changes)
    if problems:
        raise ViwoError("invalid_request", "settings refused", hint="; ".join(problems))
    text = ini_path.read_text(encoding="utf-8-sig") if ini_path.exists() else ""
    lines = text.splitlines()
    for section, values in sections.items():
        lines = _apply(lines, section, values)
    draft = ini_path.with_name(ini_path.name + ".draft")
    draft.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    try:
        checked = load_ini(draft)  # same folder: relative paths resolve as they will for real
    except ViwoError:
        draft.unlink(missing_ok=True)
        raise
    os.replace(draft, ini_path)
    return list(checked.problems)
