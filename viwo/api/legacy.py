"""Bridge used by the v1 web server: extraction and dependency status go through ViWo.

The v1 server keeps its routes and payload shapes (doc 4.1); this module turns a
v1 /api/extract call into a ViWo extraction job and back (STATUS.md deviation X1).
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Callable

from viwo.contracts.pipeline import ExtractionRequest
from viwo.core.jobs import JobRunner
from viwo.core.pipeline.runner import extract
from viwo.core.wiring.boot import Runtime, boot

_LOCK = threading.Lock()
_STATE: dict[str, Runtime] = {}


def runtime(temp_root: Path | None = None) -> Runtime:
    with _LOCK:
        if "rt" not in _STATE:
            _STATE["rt"] = boot(temp_root=temp_root)
        return _STATE["rt"]


def extract_for_v1(
    payload: dict,
    workspace: Path,
    default_workspace: Path,
    temp_root: Path,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Run one extraction; return the v1 /api/extract response shape."""
    rt = runtime(temp_root)
    request = ExtractionRequest.from_payload(payload, str(workspace))
    sink = (lambda event: progress(event.legacy_line())) if progress else None
    job = JobRunner(sink).submit(
        "extract",
        lambda jid, s, c: extract(rt, request, jid, s, c, default_workspace),
        background=False,
    )
    if job.error:
        return {
            "success": False,
            "error": job.error["message"],
            "details": job.error["hint"],
            "code": job.error["code"],
            "needsDecision": job.error["code"] == "needs_decision",
            "options": ["new", "replace", "cancel"],
        }
    result = job.result.to_legacy_dict()
    return {
        "success": True,
        "result": result,
        "assetPath": job.result.workspace,
        "extractorType": result["extractorType"],
        "detection": result["detection"],
    }


def dependencies_for_v1() -> dict:
    """v1 /api/dependencies: backend dependencies plus ffmpeg for the legacy merger."""
    items = runtime().dependency_report()
    media = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
    items.append({"id": "ffmpeg", "label": "ffmpeg + ffprobe", "available": media,
                  "required": False, "category": "merger", "requirement": "optional",
                  "location": shutil.which("ffmpeg") or "", "hint": "needed by the media merger"})
    return {"success": True, "requiredOk": True, "dependencies": items,
            "problems": list(runtime().problems)}
