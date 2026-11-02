"""Entry point of the frozen Windows build (viwo.exe).

viwo.exe also answers `viwo.exe -m <module> ...` like a Python interpreter, so tools that ViWo
runs as `python -m <module>` (unrpa) keep working when sys.executable is viwo.exe.
"""

import multiprocessing
import runpy
import sys

from viwo.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 2 and sys.argv[1] == "-m":
        module = sys.argv[2]
        sys.argv = [module, *sys.argv[3:]]
        runpy.run_module(module, run_name="__main__", alter_sys=True)
        sys.exit(0)
    sys.exit(main())
