"""RUNTIME isolation (doc 11.8, T4): the patcher tiers and their readiness, and the session. GET
lists the tiers (what each needs, whether it can run here). POST with no `action` is the one-shot
form (start `exePath` under a tier, apply `patchSet` live, close); with an `action`: `start` boots
a target behind a tier and leaves it running (the server owns the guest process); every other
action (status, pause, resume, snapshot, rollback, locate, dump, patch, undo, stop) rejoins the
session the workspace records. `patch` writes the same patch set `/api/patch` writes into a cold
copy into the guest (core.isolation.live)."""

from typing import Any, Callable

from viwo.contracts.errors import ViwoError

from .app import App, failure, path_param, safe

GUEST = {"memory": "memory_mb", "cpus": "cpus"}
FLAGS = ("network", "headless", "halted", "fresh", "efi", "gpu")


def isolation_tiers(app: App, q: dict) -> dict:
    """GET /api/runtime/isolation: every tier with its requirement and readiness wall."""
    from viwo.core.isolation import tiers

    return {
        "success": True,
        "tiers": tiers(app.rt),
        "enabled": "capture" in app.rt.config.features,
    }


def _guest(d: dict) -> dict:
    guest = {name: int(d[key]) for key, name in GUEST.items() if d.get(key)}
    guest.update({flag: True for flag in FLAGS if d.get(flag)})
    if d.get("accel"):
        guest["accel"] = str(d["accel"])
    if (share := path_param(d, "share")) is not None:
        guest["share"] = share
    if d.get("domain"):  # T3 attaches to a running domain (on KVM through its KVMi socket)
        guest["args"] = (str(d["domain"]), str(d.get("kvmiSocket") or ""))
    return guest


def run_isolation(app: App, d: dict) -> dict:
    """POST /api/runtime/isolation {action?, tier?, image?, exePath?, patchSet?, base?, name?,
    snapshot?, memory?, cpus?, network?, headless?, accel?, fresh?, efi?, gpu?, share?, domain?,
    kvmiSocket?, process?
    (locate: a program name or pid; none lists them), program? (dump: the located program),
    wait?, hold? (patch: seconds)}; `snapshot` on patch takes a whole-guest snapshot first."""
    from viwo.core.isolation import session as sessions

    from .handlers_capture import _ours

    action = str(d.get("action") or "run")  # no action: the one-shot start, patch, close
    try:
        _ours(app)  # .runtime/ lands under the workspace, never in a game folder
        base, pid, guest = int(str(d.get("base") or "0"), 0), int(d.get("pid") or 0), _guest(d)
    except (TypeError, ValueError):
        return failure(ViwoError("invalid_request", "pid, base, memory and cpus must be numbers"))
    except ViwoError as exc:
        return failure(exc)
    exe, image = path_param(d, "exePath"), path_param(d, "image")
    req = sessions.IsolateRequest(
        app.workspace, image, exe, str(d.get("tier", "")), pid, bool(d.get("snapshot")), guest
    )
    if action == "start":
        return safe(lambda: {"success": True, **sessions.start(app.rt, req, None)[0]})
    if action == "run":
        if exe is None or not exe.is_file():
            return failure(ViwoError("not_found", "Executable not found", hint="an absolute path"))
        patch = path_param(d, "patchSet")
        return safe(lambda: {"success": True, **sessions.drive(app.rt, req, patch, base)})
    opt = {"name": d.get("name"), "exe": exe, "patchset": path_param(d, "patchSet"), "base": base}
    opt.update(target=str(d.get("process") or ""), program=bool(d.get("program")))
    opt.update(snapshot=bool(d.get("snapshot")), wait=d.get("wait"), hold=d.get("hold"))
    return safe(lambda: {"success": True, **sessions.act(app.rt, app.workspace, action, **opt)})


ISOLATION_GET: dict[str, Callable[[App, dict], Any]] = {
    "/api/runtime/isolation": isolation_tiers,
}
ISOLATION_POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/runtime/isolation": run_isolation,
}
