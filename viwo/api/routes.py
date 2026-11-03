"""New HTTP routes (doc 4.1, 12.5), served through the v1 server's hook.

Every response is the doc 12.3b envelope with an HTTP status from the error code.
"""

from __future__ import annotations

import re
from pathlib import Path

from viwo.contracts.errors import Envelope, ViwoError
from viwo.contracts.pipeline import ExtractionMode, ExtractionRequest, MixedPolicy
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import detect_all
from viwo.core.pipeline.select import select_plugins
from viwo.core.wiring.conformance import capabilities_of

from .app import get_app

PLUGIN_PROBLEM = re.compile(r"^plugin ([a-z][a-z0-9_-]*)\b")

STATUS = {
    "invalid_request": 400,
    "refused": 403,
    "not_found": 404,
    "busy": 409,
    "offline": 503,
    "internal": 500,
}


def _distro() -> dict:
    return get_app().rt.info()


def _plugin_entry(plugin_id: str, plugin, deps: list[dict], error: str) -> dict:
    """Doc 4.1: manifest, options schema, capabilities, load error, dependency status."""
    m = plugin.manifest
    return {
        "id": plugin_id,
        "name": m.name,
        "version": m.version,
        "engineType": m.engine_type,
        "builtin": m.builtin,
        "tosSensitive": m.tos_sensitive,
        "description": m.description,
        "capabilities": list(capabilities_of(plugin)),
        "options": [o.__dict__ for o in m.options],
        "slots": [s.slot_id for s in plugin.slot_definitions()],
        "dependencies": {d["id"]: d["available"] for d in deps if d["category"] == plugin_id},
        "error": error,
        "loaded": True,
    }


def _plugins() -> list[dict]:
    rt = get_app().rt
    errors: dict[str, str] = {}
    for problem in rt.problems:  # "plugin <id> disabled: ..." / "plugin <id>: options rejected"
        hit = PLUGIN_PROBLEM.match(problem)
        if hit:
            errors.setdefault(hit.group(1), problem)
    deps = rt.dependency_report()
    out = [
        _plugin_entry(pid, p, deps, errors.get(pid, "")) for pid, p in sorted(rt.plugins.items())
    ]
    for pid in sorted(set(errors) - set(rt.plugins)):  # disabled at load: shown with the reason
        out.append({"id": pid, "error": errors[pid], "loaded": False})
    return out


def _detect(data: dict) -> dict:
    """Dry run (doc 4.1): every plugin's detection plus the selection for each mode."""
    game = Path(str(data.get("gamePath", "")))
    if not game.is_dir():
        raise ViwoError("invalid_request", f"game folder not found: {game}")
    rt = get_app().rt
    found = detect_all(rt, FolderProbe(game))
    priorities = {pid: p.manifest.priority for pid, p in rt.plugins.items()}
    ranked = list(found.values())

    def pick(mode: ExtractionMode, policy: MixedPolicy = MixedPolicy.DETECTED) -> list[str]:
        req = ExtractionRequest(str(game), mode=mode, mixed_policy=policy)
        return list(select_plugins(req, ranked, priorities))

    candidates = sorted(
        (d for d in ranked if d.confidence > 0),
        key=lambda d: (-d.confidence, -priorities.get(d.plugin_id, 0), d.plugin_id),
    )
    modes = {
        "auto": pick(ExtractionMode.AUTO),
        "single": [d.plugin_id for d in candidates],
        "mixed": {
            "detected": pick(ExtractionMode.MIXED, MixedPolicy.DETECTED),
            "all": pick(ExtractionMode.MIXED, MixedPolicy.ALL),
            "selected": [d.plugin_id for d in candidates],
        },
    }
    detections = {k: v.to_legacy_dict() for k, v in found.items()}
    return {"detections": detections, "auto": modes["auto"], "modes": modes}


def _job(job_id: str, query: dict) -> dict:
    job = get_app().jobs.get(job_id)
    result = job.result.to_legacy_dict() if hasattr(job.result, "to_legacy_dict") else job.result
    return {**job.summary(), "result": result}


def _events(job_id: str, query: dict) -> dict:
    start = int((query.get("from") or ["0"])[0])
    events = get_app().jobs.get(job_id).events[start:]
    return {
        "from": start,
        "next": start + len(events),
        "events": [{**e.__dict__, "line": e.legacy_line()} for e in events],
    }


def _cancel(job_id: str, data: dict) -> dict:
    job = get_app().jobs.get(job_id)
    job.cancel.cancel()
    return job.summary()


def _respond(fn, *args) -> tuple[dict, int]:
    try:
        return Envelope.success(fn(*args)).to_dict(), 200
    except ViwoError as exc:
        return Envelope.failure(exc).to_dict(), STATUS.get(exc.code, 200)
    except (ValueError, TypeError) as exc:
        return Envelope.failure(ViwoError("invalid_request", str(exc))).to_dict(), 400


def handle_get(path: str, query: dict) -> tuple[dict, int] | None:
    static = {
        "/api/distro": _distro,
        "/api/plugins": _plugins,
        "/api/jobs": lambda: [j.summary() for j in get_app().jobs.list()],
    }
    if path in static:
        return _respond(static[path])
    parts = path.strip("/").split("/")
    if parts[:2] == ["api", "jobs"] and len(parts) == 3:
        return _respond(_job, parts[2], query)
    if parts[:2] == ["api", "jobs"] and len(parts) == 4 and parts[3] == "events":
        return _respond(_events, parts[2], query)
    return None


def handle_post(path: str, data: dict) -> tuple[dict, int] | None:
    if path == "/api/detect":
        return _respond(_detect, data)
    parts = path.strip("/").split("/")
    if parts[:2] == ["api", "jobs"] and len(parts) == 4 and parts[3] == "cancel":
        return _respond(_cancel, parts[2], data)
    return None
