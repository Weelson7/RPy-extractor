"""Presentation frames: ViWo served with the repository's startup.ini (every installed tool) on
a fresh workspace, headless Edge or Chrome driven by `shots.mjs` through a walk over every view
on one game. Writes the PNGs and `steps.json` (caption, detail, hold, pdf per frame) for
`tech_pdf.py` and `video.py`. The game folder is only read.

Usage: python tools/presentation/frames.py <game folder> [--out viwo-data/presentation/frames]
       [--size 1600x900] [--features extraction,sorting,merger,analysis,capture] [--keep]
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from viwo.api import app as app_module  # noqa: E402
from viwo.api.server import make_server  # noqa: E402
from viwo.core.wiring.boot import boot  # noqa: E402

BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "microsoft-edge",
    "google-chrome",
    "chromium",
)
DEFAULT_OUT = ROOT / "viwo-data" / "presentation" / "frames"


def browser() -> str:
    found = next((b for b in BROWSERS if Path(b).is_file() or shutil.which(b)), None)
    if found is None:
        raise SystemExit("no Edge, Chrome or Chromium found for the frames")
    return found


def serve(work: Path, features: tuple[str, ...] | None = None):
    """The app on a free loopback port, on a fresh empty workspace; returns (server, url).
    `features` overrides the ini's switches for this run only (the ini is not written)."""
    ini = ROOT / "startup.ini"
    app = app_module.App(boot(ini, features=features), ini)
    (work / "workspace").mkdir(parents=True)
    app.set_workspace(work / "workspace")
    app_module.reset_app(app)
    httpd = make_server(app, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def capture(game: Path, out: Path, width: str, height: str, features=None) -> list[dict]:
    work = out / "_run"
    shutil.rmtree(work, ignore_errors=True)
    httpd, url = serve(work, features)
    port = free_port()
    flags = ["--headless=new", "--disable-gpu", "--no-first-run", f"--window-size={width},{height}"]
    flags += [f"--remote-debugging-port={port}", f"--user-data-dir={work / 'profile'}"]
    child = subprocess.Popen(
        [browser(), *flags, "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    try:
        script = Path(__file__).with_name("shots.mjs")
        node = shutil.which("node") or "node"
        run = subprocess.run(
            [node, str(script), url, str(port), str(out), width, height, str(game)],
            capture_output=True, text=True, encoding="utf-8", timeout=5 * 3600,
        )  # fmt: skip
        if run.returncode:
            print(run.stderr[-2000:], file=sys.stderr)
        return [json.loads(line) for line in run.stdout.splitlines() if line.startswith("{")]
    finally:
        if sys.platform == "win32":  # the browser's own children too
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(child.pid)], capture_output=True)
        else:
            child.kill()
        child.wait(30)
        stop_jobs(app_module.get_app())
        httpd.shutdown()


def stop_jobs(app) -> None:
    """A job still running is cancelled and waited for, so it removes its own temporary
    folders (an extraction's staging is tens of GB); exiting under it would leave them."""
    for job in app.jobs.list():
        if not job.done.is_set():
            job.cancel.cancel()
            if not job.done.wait(1800):
                print(f"job {job.job_id} did not stop: its temp folder may remain", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("game", type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--size", default="1600x900")
    ap.add_argument("--features", help="switches for this run, e.g. extraction,analysis,capture")
    ap.add_argument("--keep", action="store_true", help="keep the run's workspace (_run)")
    args = ap.parse_args(argv)
    width, height = args.size.split("x")
    features = tuple(f.strip() for f in args.features.split(",")) if args.features else None
    for old in args.out.glob("*.png"):
        old.unlink()
    args.out.mkdir(parents=True, exist_ok=True)
    steps = capture(args.game.resolve(), args.out.resolve(), width, height, features)
    (args.out / "steps.json").write_text(json.dumps(steps, indent=1), encoding="utf-8")
    if not args.keep:  # an extraction of a large game: tens of GB the frames no longer need
        shutil.rmtree(args.out / "_run", ignore_errors=True)
    print(f"{len(steps)} frames in {args.out}")
    return 0 if steps else 1


if __name__ == "__main__":
    sys.exit(main())
