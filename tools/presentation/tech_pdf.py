"""The technical PDF: what ViWo is, how it is built (mermaid charts), every view of the UI on a
real game (the frames of `frames.py`), reference tables generated from the code (plugins,
slots, pinned tools, CLI, HTTP routes, conformance) and, last, the CTF results (`ctf.py`).
The prose is `tech_template.html`; mermaid is pinned in `viwo/data/tools.json` and installed
into third_party/ by itself; Edge or Chrome headless prints the page. The HTML stays next to
the PDF.

Usage: python tools/presentation/tech_pdf.py [--frames viwo-data/presentation/frames]
       [--out viwo-data/presentation/ViWo-technical-<version>.pdf]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import ctf  # noqa: E402
import reference  # noqa: E402
from frames import browser  # noqa: E402
from reference import esc  # noqa: E402

from viwo import CONTRACT_VERSION, __version__  # noqa: E402
from viwo.core import thirdparty  # noqa: E402
from viwo.core.wiring.boot import boot  # noqa: E402
from viwo.os import select_os  # noqa: E402

TEMPLATE = Path(__file__).with_name("tech_template.html")
BASE = ROOT / "viwo-data" / "presentation"


def mermaid() -> Path:
    """The pinned mermaid.min.js, installed by itself when it is not there."""
    if thirdparty.tool_argv("mermaid", ROOT) is None:
        thirdparty.install_tool("mermaid", ROOT, select_os().process, print)
    found = sorted((ROOT / "third_party" / "mermaid").rglob("mermaid.min.js"))
    if not found:
        raise SystemExit("mermaid could not be installed")
    return found[0]


def tour(frames: Path) -> str:
    """One figure per frame marked for the PDF: the screenshot, its caption and what it does."""
    steps_file = frames / "steps.json"
    steps = json.loads(steps_file.read_text(encoding="utf-8")) if steps_file.is_file() else []
    figures = [
        f"<figure><img src='{(frames / (s['file'] + '.png')).resolve().as_uri()}' alt=''>"
        f"<figcaption><b>{esc(s['caption'])}</b> {esc(s.get('detail', ''))}</figcaption></figure>"
        for s in steps
        if s.get("pdf", True)
    ]
    if not figures:
        return "<p class='sub'>No frames: run <code>tools/presentation/frames.py</code>.</p>"
    return "\n".join(figures)


def kpis(rt) -> dict[str, str]:

    states = reference.conformance()
    tests = sum(
        p.read_text(encoding="utf-8").count("    def test_")
        for p in (ROOT / "tests").glob("test_*.py")
    )
    return {
        "version": __version__,
        "contract": CONTRACT_VERSION,
        "date": date.today().isoformat(),
        "plugin_count": str(sum(1 for p in rt.plugins.values() if not p.manifest.engine)),
        "game_count": str(sum(1 for p in rt.plugins.values() if p.manifest.engine)),
        "slot_count": str(len(rt.slots)),
        "tool_count": str(len(reference.tools())),
        "test_count": str(tests),
        "conf_implemented": str(states["implemented"]),
        "conf_partial": str(states["partial"]),
        "conf_open": str(states["open"]),
    }


def page(frames: Path) -> str:
    rt = boot(ROOT / "startup.ini")
    values = {**kpis(rt), **reference.all_tables(rt), "tour": tour(frames)}
    values["ctf"] = ctf.section(ROOT / "viwo-data")  # the CTF results, last
    values["mermaid"] = mermaid().resolve().as_uri()
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return re.sub(  # a chart's source is text, not markup: its <br/> must reach mermaid
        r'(<pre class="mermaid">)(.*?)(</pre>)',
        lambda m: m.group(1) + html.escape(m.group(2), quote=False) + m.group(3),
        text,
        flags=re.S,
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--frames", type=Path, default=BASE / "frames")
    ap.add_argument("--out", type=Path, default=BASE / f"ViWo-technical-{__version__}.pdf")
    args = ap.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    source = args.out.with_suffix(".html")
    source.write_text(page(args.frames), encoding="utf-8")
    flags = ["--headless=new", "--disable-gpu", "--no-pdf-header-footer"]
    flags += ["--virtual-time-budget=60000", "--allow-file-access-from-files"]
    subprocess.run(
        [browser(), *flags, f"--print-to-pdf={args.out.resolve()}", source.resolve().as_uri()],
        timeout=300, capture_output=True,
    )  # fmt: skip
    if not args.out.is_file():
        raise SystemExit(f"the browser printed no PDF; the HTML is {source}")
    print(f"PDF written: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
