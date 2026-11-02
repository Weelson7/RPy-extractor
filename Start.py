"""Launch the ViWo web UI (same as `python -m viwo.cli serve`)."""

import sys

from viwo.cli import main

if __name__ == "__main__":
    sys.exit(main(["serve", *sys.argv[1:]]))
