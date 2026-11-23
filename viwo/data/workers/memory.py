"""ViWo worker for the isolation arm (doc 11.8): Volatility 3 over a guest RAM image. ViWo runs
it as its own process and never imports Volatility (Volatility Software License):
    python -I memory.py --lib <third_party/volatility3> --cache <folder> <volatility arguments>
It is Volatility's own command line, with its cache and symbol tables kept in <folder> (under
third_party/, nowhere else) and ViWo's plugin folder (volatility/: `viwo_guest.Guest`) added.
Windows symbol tables come from Microsoft's symbol server the first time a kernel is seen."""

from __future__ import annotations

import sys
from pathlib import Path

PLUGINS = Path(__file__).resolve().parent / "volatility"


def main(argv: list[str]) -> int:
    if len(argv) < 4 or argv[0] != "--lib" or argv[2] != "--cache":
        print("usage: memory.py --lib LIB --cache DIR <volatility arguments>", file=sys.stderr)
        return 2
    lib, cache, rest = argv[1], Path(argv[3]), argv[4:]
    sys.path.insert(0, lib)
    symbols = cache / "symbols"
    symbols.mkdir(parents=True, exist_ok=True)
    from volatility3.cli import main as volatility

    sys.argv = ["vol", "--cache-path", str(cache), "-s", str(symbols), "-p", str(PLUGINS), *rest]
    try:
        volatility()
    except SystemExit as exc:
        return int(exc.code or 0) if isinstance(exc.code, int) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
