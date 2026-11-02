"""New HTTP routes (doc 4.1, 12.5), served through the v1 server's hook.

Every response is the doc 12.3b envelope with an HTTP status from the error code.
"""

from __future__ import annotations

from pathlib import Path

from viwo import CONTRACT_VERSION
from viwo.contracts.errors import Envelope, ViwoError
from viwo.contracts.pipeline import ExtractionRequest
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import detect_all
from viwo.core.pipeline.select import select_plugins

from .app import get_app

STATUS = {
    "invalid_request": 400,
    "refused": 403,
    "not_found": 404,
    "busy": 409,
    "offline": 503,
    "internal": 500,
}


def _distro() -> dict:
    rt = get_app().rt
    return {**rt.info(), "contract": CONTRACT_VERSION, "features": list(rt.config.features)}


def _plugins() -> list[dict]:
    rt = get_app().rt
    out = []
    for plugin_id, plugin in sorted(rt.plugins.items()):
        m = plugin.manifest
        out.append(
            {
                "id": plugin_id,
                "name": m.name,
                "version": m.version,
                "engineType": m.engine_type,
                "builtin": m.builtin,
                "tosSensitive": m.tos_sensitive,
                "options": [o.__dict__ for o in m.options],
                "slots": [s.slot_id for s in plugin.slot_definitions()],
            }
        )
    return out


def _detect(data: dict) -> dict:
    game = Path(str(data.get("gamePath", "")))
    if not game.is_dir():
        raise ViwoError("invalid_request", f"game folder not found: {game}")
    rt = get_app().rt
    found = detect_all(rt, FolderProbe(game))
    priorities = {pid: p.manifest.priority for pid, p in rt.plugins.items()}
    chosen = select_plugins(ExtractionRequest(str(game)), list(found.values()), priorities)
    return {"detections": {k: v.to_legacy_dict() for k, v in found.items()}, "auto": list(chosen)}


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
