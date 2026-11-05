"""Diagnostics bundle (`viwo diag`, POST /api/diag) and update checks (GET /api/updates, only
when the user asks; ViWo never calls the network on its own).

The bundle holds what a bug report needs: recent logs, the run records of the active workspace,
the effective wiring, tool status and pins, OS and Python versions. Secrets are stripped.
"""

import json
import platform
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from viwo import __version__
from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

from . import thirdparty

REPO = "Weelson7/RPy-extractor"
INDEXES_REPO = "Weelson7/vidya_wormhole_indexes"
API = "https://api.github.com/repos/{repo}/releases"
SECRET = re.compile(r"(?i)(key|secret|password|token)(\s*[=:]\s*)\S+")
QUOTED = re.compile(r'(?i)("[^"]*(?:key|secret|password|token)[^"]*"\s*:\s*)"[^"]*"')
LOG_DAYS = 3


def scrub(text: str) -> str:
    """Hide anything that looks like a credential: `aes_key = ...`, `token: ...`."""
    return SECRET.sub(r"\1\2<secret>", QUOTED.sub(r'\1"<secret>"', text))


def _recent_logs(folder: Path, days: int = LOG_DAYS) -> list[Path]:
    cutoff = time.time() - days * 86400
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.log") if p.stat().st_mtime >= cutoff)


def _about(rt) -> dict:
    return {
        "viwo": __version__,
        "python": sys.version,
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "os_layer": rt.os.os_id,
        "ini": str(rt.config.source),
        "frozen": thirdparty.FROZEN,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def bundle(rt, workspace: Path, out: Path | None = None) -> Path:
    """Write the diagnostics zip and return its path (default: the logs folder)."""
    from .preflight import check

    logs = rt.config.server.logs
    out = out or logs / f"viwo-diag-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    dump = lambda data: json.dumps(data, indent=2, default=str, sort_keys=True)  # noqa: E731
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("about.json", dump(_about(rt)))
        z.writestr("info.json", dump(rt.info()))
        tools = check(rt, lambda e: None)
        z.writestr("slots.json", dump({"bindings": rt.info()["slots"], "dependencies": tools}))
        z.writestr("tools.json", thirdparty.MANIFEST.read_text(encoding="utf-8"))
        for log in _recent_logs(logs):
            z.writestr(f"logs/{log.name}", scrub(log.read_text(encoding="utf-8", errors="replace")))
        for record in sorted((workspace / ws.RUNS_DIR).glob("*.json")):
            text = record.read_text(encoding="utf-8", errors="replace")
            z.writestr(f"runs/{record.name}", scrub(text))
    return out


def github_json(url: str, timeout: float = 10.0):
    """One GitHub API call; any network problem becomes an `offline` error, never a crash."""
    if not url.startswith("https://"):
        raise ViwoError("refused", "update checks use https only")
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"viwo/{__version__}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise ViwoError("offline", f"GitHub answered {exc.code} for {url}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ViwoError("offline", f"cannot reach GitHub: {exc}", hint="check the connection")


def latest_release(repo: str, fetch=github_json) -> dict:
    """{tag, version, url} of the latest release, or empty strings when there is none."""
    data = fetch(API.format(repo=repo) + "/latest")
    if not data:
        return {"tag": "", "version": "", "url": f"https://github.com/{repo}/releases"}
    tag = str(data.get("tag_name", ""))
    return {"tag": tag, "version": tag.lstrip("v"), "url": str(data.get("html_url", ""))}


def indexes_version(home: Path) -> str:
    file = home / "indexes" / "VERSION"
    return file.read_text(encoding="utf-8").strip() if file.is_file() else "none"


def check_updates(home: Path, fetch=github_json) -> dict:
    """Latest app and indexes releases next to what is installed (on click only)."""
    app, idx = latest_release(REPO, fetch), latest_release(INDEXES_REPO, fetch)
    current = indexes_version(home)
    return {
        "app": {"current": __version__, "latest": app["version"], "url": app["url"]},
        "indexes": {"current": current, "latest": idx["tag"], "url": idx["url"]},
    }
