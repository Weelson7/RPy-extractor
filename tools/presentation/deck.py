"""The technical deck (PowerPoint): what ViWo is, how it is built, what it does on a real game
(the frames of `frames.py`) and how far each claim is proven (the CTF results of `ctf.py`).
The numbers are counted from the code when the deck is built; the prose and the layout are
`deck.js`. pptxgenjs is pinned in `viwo/data/tools.json` (one file) and installed into
third_party/ by itself; Node runs it. The data stays next to the deck as JSON.

Usage: python tools/presentation/deck.py [--frames viwo-data/presentation/frames]
       [--out viwo-data/presentation/ViWo-technical-<version>.pptx]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import ctf  # noqa: E402
import tech_pdf  # noqa: E402

from viwo import __version__  # noqa: E402
from viwo.core import thirdparty  # noqa: E402
from viwo.core.wiring.boot import boot  # noqa: E402
from viwo.os import select_os  # noqa: E402

BASE = ROOT / "viwo-data" / "presentation"


def bundle() -> Path:
    """The pinned pptxgenjs bundle, installed by itself when it is not there."""
    if thirdparty.tool_argv("pptxgenjs", ROOT) is None:
        thirdparty.install_tool("pptxgenjs", ROOT, select_os().process, print)
    found = sorted((ROOT / "third_party" / "pptxgenjs").rglob("pptxgen.bundle.js"))
    if not found:
        raise SystemExit("pptxgenjs could not be installed")
    return found[0]


def data(rt, store: Path) -> dict:
    """What the deck shows that is not prose: the counts, the games pass, the challenges."""
    engines = sorted(p.manifest.name for p in rt.plugins.values() if not p.manifest.engine)
    return {
        "kpis": tech_pdf.kpis(rt),
        "games": ctf.flags(store),
        "challenges": ctf.load(store / "ctf" / "results.json") or [],
        "engines": engines,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--frames", type=Path, default=BASE / "frames")
    ap.add_argument("--out", type=Path, default=BASE / f"ViWo-technical-{__version__}.pptx")
    args = ap.parse_args(argv)
    if (node := shutil.which("node")) is None:
        raise SystemExit("the deck needs Node.js on PATH (the frames need it too)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    source = args.out.with_suffix(".json")
    values = data(boot(ROOT / "startup.ini"), ROOT / "viwo-data")
    source.write_text(json.dumps(values, indent=1), encoding="utf-8")
    script = Path(__file__).with_name("deck.js")
    paths = [source, args.frames, args.out, bundle()]
    done = subprocess.run(
        [node, str(script), *(str(p.resolve()) for p in paths)],
        timeout=300, capture_output=True, text=True,
    )  # fmt: skip
    if done.returncode or not args.out.is_file():
        raise SystemExit(f"no deck written: {(done.stderr or done.stdout).strip()[-600:]}")
    print(f"deck written: {args.out} ({len(values['games'])} game(s) of the pass)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
