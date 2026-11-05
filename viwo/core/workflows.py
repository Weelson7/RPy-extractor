"""Workflows (doc 19.3): what makes a recorded runbook replayable. A recorded action's
parameters become portable (the game and the workspace as `{game}` and `{workspace}`, an id an
earlier step answered as `{step<N>_<key>}`, secret plugin options as secret inputs that are
never written, a process id as an input), and its answer an expectation (a digest, and the
facts that name what changed) that a replay compares with."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

_DROPPED = {  # differ on every run of the same action, or are free text with timings in it
    *("success", "jobId", "step", "when", "started", "finished", "created", "events", "pid"),
    *("reportPath", "runRecord", "logs", "made", "context", "viwo"),
}
_VOLATILE = re.compile(
    r"(^|_)(time|timestamp|stamp|elapsed|duration|seconds)$|(Time|Stamp|Elapsed|Duration|Seconds)$"
)
_HEX = re.compile(r"[0-9a-f]{64}")
_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
CARRIED = re.compile(r"step\d+_[a-z0-9_]+")  # the `{name}` of a value an earlier step answered
UNEXPECTED = {"capture", "dump", "trace", "profile", "agent", "record"}  # a running game's kinds
MAX_FACTS = 60


def _volatile(key: str) -> bool:
    """Ids, tokens, times, stamps, durations: different on every run of the same action."""
    return (
        key in _DROPPED
        or key.endswith(("Id", "_id", "Ids", "Token"))
        or bool(_VOLATILE.search(key))
    )


def path_pairs(values: dict[str, str]) -> list[tuple[re.Pattern, str]]:
    """(spelling, `{name}`) for the game and workspace paths, every spelling, longest first
    (a workspace beside the game, `Foo-ws`, is never read as `{game}-ws`), each matched only
    where a path ends (`Foobar` is not `{game}bar`)."""
    found: dict[str, str] = {}
    for name in ("game", "workspace"):
        raw = values.get(name, "")
        if raw:
            path, real = Path(raw), Path(raw).resolve()
            for spelling in (raw, str(path), path.as_posix(), str(real), real.as_posix()):
                if len(spelling) > 3:
                    found.setdefault(spelling, "{" + name + "}")
    ordered = sorted(found.items(), key=lambda p: -len(p[0]))
    return [(re.compile(re.escape(s) + r"(?=$|[\\/\s\"',;)\]}])"), n) for s, n in ordered]


def portable(value, pairs: list[tuple[re.Pattern, str]]):
    """The tree with each spelling of the game and workspace replaced by its `{name}`."""
    if isinstance(value, dict):
        return {k: portable(v, pairs) for k, v in value.items()}
    if isinstance(value, list):
        return [portable(v, pairs) for v in value]
    if isinstance(value, str):
        for spelling, name in pairs:
            value = spelling.sub(lambda _m, n=name: n, value)
    return value


def normalize(answer, pairs):
    """The answer without its volatile parts, its paths portable: what two runs share."""
    if isinstance(answer, dict):
        return {k: normalize(v, pairs) for k, v in answer.items() if not _volatile(str(k))}
    if isinstance(answer, list):
        return [normalize(v, pairs) for v in answer]
    return portable(answer, pairs)


def facts(tree, prefix: str = "", depth: int = 0, out: dict | None = None) -> dict:
    """Scalar values by dotted key (three levels; a list as its length), at most MAX_FACTS."""
    out = {} if out is None else out
    for key, value in sorted(tree.items()) if isinstance(tree, dict) else ():
        name = f"{prefix}{key}"
        if len(out) >= MAX_FACTS:
            break
        if isinstance(value, dict) and depth < 2:
            facts(value, f"{name}.", depth + 1, out)
        elif isinstance(value, list):
            out[f"{name}[]"] = len(value)
        elif value is None or isinstance(value, (str, int, float, bool)):
            out[name] = value[:120] if isinstance(value, str) else value
    return out


def expectation(answer: dict, values: dict[str, str]) -> dict:
    norm = normalize(answer, path_pairs(values))
    text = json.dumps(norm, sort_keys=True, default=str)
    return {"digest": hashlib.sha256(text.encode("utf-8")).hexdigest(), "facts": facts(norm)}


def valid_expect(raw) -> bool:
    return (
        isinstance(raw, dict)
        and isinstance(raw.get("digest"), str)
        and bool(_HEX.fullmatch(raw["digest"]))
        and isinstance(raw.get("facts", {}), dict)
    )


def compare(expect: dict, answer: dict, values: dict[str, str]) -> list[str]:
    """What changed against the recording: empty when the answer is the same."""
    now = expectation(answer, values)
    if now["digest"] == expect["digest"]:
        return []
    was, new = expect.get("facts", {}), now["facts"]
    changed = [
        f"{key}: {was.get(key, '(none)')!r} -> {new.get(key, '(none)')!r}"
        for key in sorted(set(was) | set(new))
        if was.get(key, "(none)") != new.get(key, "(none)")
    ]
    return changed[:12] or ["the answer differs deeper than its facts show (see JOBS)"]


def carried(index: int, answer: dict) -> dict[str, str]:
    """The values an action answered (step `index`, from 0) that later steps may name."""
    return {
        f"step{index + 1}_{key.lower()}": str(value)
        for key, value in answer.items()
        if _KEY.fullmatch(key) and isinstance(value, (str, int)) and not isinstance(value, bool)
    }


def _chain(params: dict, earlier: list[dict | None]) -> dict:
    """A parameter that is an id or token an earlier step answered (a cleanup plan's planId,
    an apply's undoToken) names that step's answer, so a replay sends the replay's own."""
    for key, value in params.items():
        if not isinstance(value, str) or len(value) < 6:
            continue
        for index in range(len(earlier) - 1, -1, -1):
            hit = next(
                (k for k, v in (earlier[index] or {}).items() if v == value and _volatile(k)), ""
            )
            if hit and _KEY.fullmatch(hit):
                params[key] = "{" + f"step{index + 1}_{hit.lower()}" + "}"
                break
    return params


def _secrets_out(rt, params: dict, inputs: list[dict]) -> dict:
    """Secret plugin options (doc 3: as run records mask them) become secret inputs; every
    option of an owner this runtime does not know (off, misspelled) is taken as secret."""
    given = params.get("pluginOptions")
    plugins = {pid.lower(): plugin for pid, plugin in rt.plugins.items()}
    for owner, options in given.items() if isinstance(given, dict) else ():
        plugin = plugins.get(str(owner).lower())
        names = set(options) if isinstance(options, dict) else set()
        secret = {o.key for o in plugin.manifest.options if o.kind == "secret"} if plugin else names
        for key in sorted(secret & names):
            name = f"secret_{len(inputs) + 1}"
            label = f"{owner}.{key} (secret: given at each run, never saved)"
            inputs.append({"name": name, "label": label, "secret": True})
            options[key] = "{" + name + "}"
    return params


def _no_pid(params: dict, inputs: list[dict]) -> dict:
    """A process id is this run's only: the image name stays, else it is asked at each run."""
    if "pid" in params:
        params.pop("pid")
        if not params.get("name"):
            params["pid"] = "{pid}"
            if not any(i["name"] == "pid" for i in inputs):
                label = "process id of the running game (asked at each run)"
                inputs.append({"name": "pid", "label": label, "secret": False})
    return params


def record_step(rt, kind: str, params: dict, answer: dict, values: dict, rec) -> dict:
    """A recorded action as a runbook step: its parameters portable, its answer expected
    (none for a running game's kinds: what it does differs on every run)."""
    clean = _no_pid(_secrets_out(rt, copy.deepcopy(params), rec.inputs), rec.inputs)
    clean = portable(_chain(clean, rec.answers), path_pairs(values))
    if kind == "extract" and clean.get("onExisting", "ask") in ("ask", "", None):
        clean["onExisting"] = "new"  # a replay extracts beside a used workspace, never asks
    how = next((f" ({clean[k]})" for k in ("op", "action") if isinstance(clean.get(k), str)), "")
    title = kind.capitalize() + (how or (" (plan)" if clean.get("plan") else ""))
    step = {"title": title, "do": kind, "with": clean}
    return step if kind in UNEXPECTED else {**step, "expect": expectation(answer, values)}
