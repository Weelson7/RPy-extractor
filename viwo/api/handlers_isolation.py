"""RUNTIME isolation (doc 11.8, T4): the patcher tiers and their readiness, and a live-patch
session. GET lists the tiers (what each needs, whether it can run here); POST starts a target
under a tier and applies a patch set live, then closes. The same patch set `/api/patch` writes
into a cold copy is written here into the running/guest target (core.isolation.live)."""

from typing import Any, Callable

from viwo.contracts.errors import ViwoError

from .app import App, existing, failure, path_param, safe


def isolation_tiers(app: App, q: dict) -> dict:
    """GET /api/runtime/isolation: every tier with its requirement and readiness wall."""
    from viwo.core.isolation import tiers

    return {
        "success": True,
        "tiers": tiers(app.rt),
        "enabled": "capture" in app.rt.config.features,
    }


def run_isolation(app: App, d: dict) -> dict:
    """POST /api/runtime/isolation {exePath, tier?, image?, pid?, patchSet?, base?, snapshot?}:
    start the session and apply the patch set live (no job: the session runs then closes)."""
    from viwo.core.isolation.live import IsolateRequest, drive

    from .handlers_capture import _ours

    if isinstance(exe := existing(d, "exePath", "Executable", False), dict):
        return exe
    try:
        _ours(app)  # the session's .runtime/ lands under the workspace, never in a game folder
        pid, base = int(d.get("pid") or 0), int(str(d.get("base") or "0"), 0)
    except (TypeError, ValueError):
        return failure(ViwoError("invalid_request", "pid and base must be numbers"))
    except ViwoError as exc:
        return failure(exc)
    req = IsolateRequest(
        exe, app.workspace, str(d.get("tier", "")), path_param(d, "image"), pid,
        path_param(d, "patchSet"), base, bool(d.get("snapshot")),
    )  # fmt: skip
    return safe(lambda: {"success": True, **drive(app.rt, req, None)})


ISOLATION_GET: dict[str, Callable[[App, dict], Any]] = {
    "/api/runtime/isolation": isolation_tiers,
}
ISOLATION_POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/runtime/isolation": run_isolation,
}
