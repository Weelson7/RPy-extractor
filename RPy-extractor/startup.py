"""Startup checks for the v1 server, now backed by the ViWo core (no unpinned installs)."""
from logging_utils import emit_log


def tlog(message: str) -> None:
    """Log with timestamp."""
    emit_log(message)


def startup_dependency_preflight() -> dict[str, object]:
    """Boot the ViWo runtime and report problems; missing tools disable slots, not the app."""
    from viwo.api.legacy import runtime

    rt = runtime()
    report = [f"[PREFLIGHT] OS layer: {rt.os.os_id}; plugins: {', '.join(sorted(rt.plugins))}"]
    for slot_id, binding in sorted(rt.bindings.items()):
        state = binding.main or "unbound"
        spare = f", spare {binding.spare}" if binding.spare else ""
        report.append(f"[PREFLIGHT] {slot_id}: {state}{spare}")
    report += [f"[PREFLIGHT] note: {problem}" for problem in rt.problems]
    return {"ok": not (rt.config.strict_preflight and rt.problems), "report": report}


def dependency_status_snapshot() -> dict[str, object]:
    """Dependency status for /api/dependencies (no install side effects)."""
    from viwo.api.legacy import dependencies_for_v1

    return dependencies_for_v1()
