"""loc_caps.ini reader for the LoC counter (contract doc 15.5): schema validation, the
`[exceptions]` section (`path = cap | reason | expires at vX.Y or <milestone>`, at most three
active, expired ones fail) and the budgets. Kept apart from the counter so each stays small.
"""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass, field
from pathlib import Path

CAP_KEYS = {
    "function",
    "class",
    "file",
    "contracts_file",
    "params",
    "line_length",
    "test_file",
    "test_function",
}
SECTIONS = {"caps", "budgets", "exceptions", "web"}
MAX_EXCEPTIONS = 3
VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")


@dataclass
class Exception_:
    path: str
    cap: int
    reason: str
    expires: str


@dataclass
class Caps:
    caps: dict[str, int]
    budgets: dict[str, int]
    web: dict[str, int]
    exceptions: list[Exception_] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def file_cap(self, rel: str, default: int) -> int:
        """The per-file cap, raised by an active exception for that exact path."""
        return next((e.cap for e in self.exceptions if e.path == rel), default)


def _version(text: str) -> tuple[int, int, int] | None:
    match = VERSION.match(text.strip())
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def expired(expires: str, current: str) -> bool:
    """True when `expires` names a version the current version has reached. Milestone names
    (M10, 1.2 roadmap items) never expire by themselves: they are reviewed at the milestone."""
    due, now = _version(expires), _version(current)
    return due is not None and now is not None and now >= due


def _ints(section, name: str, problems: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, value in section.items():
        try:
            out[key] = int(value)
        except ValueError:
            problems.append(f"loc_caps.ini [{name}] {key}: not an integer ({value!r})")
    return out


def _exception(key: str, value: str, problems: list[str]) -> Exception_ | None:
    parts = [p.strip() for p in value.split("|")]
    if len(parts) != 3 or not parts[0].isdigit() or not parts[1] or not parts[2]:
        problems.append(f"loc_caps.ini [exceptions] {key}: use `cap | reason | expires at`")
        return None
    return Exception_(key, int(parts[0]), parts[1], parts[2].removeprefix("expires at").strip())


def load(path: Path, current_version: str) -> Caps:
    """Read and validate the caps file; every schema problem is a CAP failure."""
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cfg.optionxform = str  # type: ignore[assignment,method-assign]  # keep path case
    cfg.read(path, encoding="utf-8")
    problems: list[str] = []
    for section in cfg.sections():
        if section not in SECTIONS:
            problems.append(f"loc_caps.ini: unknown section [{section}]")
    for section in ("caps", "budgets", "web"):
        if not cfg.has_section(section):
            problems.append(f"loc_caps.ini: missing section [{section}]")
    caps = _ints(cfg["caps"], "caps", problems) if cfg.has_section("caps") else {}
    for key in CAP_KEYS - set(caps):
        problems.append(f"loc_caps.ini [caps]: missing {key}")
    for key in set(caps) - CAP_KEYS:
        problems.append(f"loc_caps.ini [caps]: unknown key {key}")
    budgets = _ints(cfg["budgets"], "budgets", problems) if cfg.has_section("budgets") else {}
    web = _ints(cfg["web"], "web", problems) if cfg.has_section("web") else {}
    if "js_file" not in web:
        problems.append("loc_caps.ini [web]: missing js_file")
    exceptions = []
    if cfg.has_section("exceptions"):
        for key, value in cfg["exceptions"].items():
            item = _exception(key, value, problems)
            if item is not None:
                exceptions.append(item)
    if len(exceptions) > MAX_EXCEPTIONS:
        problems.append(f"loc_caps.ini: {len(exceptions)} exceptions > {MAX_EXCEPTIONS} active")
    for item in exceptions:
        if expired(item.expires, current_version):
            problems.append(f"loc_caps.ini exception {item.path} expired at {item.expires}")
    return Caps(caps, budgets, web, exceptions, problems)
