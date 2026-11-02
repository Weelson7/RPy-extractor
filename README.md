# ViWo // Vidya Wormhole

**A local-first game reverse-engineering platform, oriented towards asset extraction.**

Point ViWo at a game folder. It recognizes the engine, routes every container to the best
available tool (with a spare when that tool is missing or fails), collects everything into one
curated workspace, and records where every file came from. Your game is never modified.

- **Engines:** Ren'Py, Unity, Godot, plus plain archives (zip, tar, 7z, rar) for anything else.
- **Never touches the game:** files are copied, never moved; a workspace or temp folder inside the
  game folder is refused; every run compares the game folder before and after.
- **Main + spare tools:** each job (unpack `.rpa`, export Unity assets, unpack a Godot PCK...) has a
  main backend and a spare; a missing tool disables only what needs it.
- **Curation built in:** extension groups, a keyboard-driven sorting view with previews, undo,
  and a media merger that turns frames and clips into one video.
- **Reproducible:** every run leaves a run record and a provenance map; `viwo replay` re-runs it.
- **Safe by default:** traversal-safe unpacking, Ren'Py archive indexes read with a pickle
  allow-list, a per-start API token for the local web UI, secrets never written to disk.

## Quick start

Requires Python 3.11+. Optional tools are detected automatically (see `viwo slots`).

```bash
python -m viwo.cli serve
```

Then open the printed address (default `http://127.0.0.1:8081/`). `python Start.py` does the same.

Command line:

```bash
python -m viwo.cli detect "/path/to/game"
```

```bash
python -m viwo.cli extract "/path/to/game" --workspace ./ws
```

```bash
python -m viwo.cli replay ./ws/.extraction_metadata/runs/<job>.json --workspace ./ws-again
```

`viwo info`, `viwo slots` and `viwo unpack <archive> --out DIR` are also available; add `--json`
for machine-readable output.

## Supported engines and tools

| Engine | Unpack / export | Main | Spare |
|--------|-----------------|------|-------|
| any | zip, tar | Python standard library | 7-Zip |
| any | 7z / rar | 7-Zip / unrar | py7zr / 7-Zip |
| Ren'Py | `.rpa` archives | built-in safe reader | unrpa |
| Unity | assets | UnityPy | AssetStudioModCLI |
| Godot | `.pck`, PCK embedded in the executable | GDRE Tools | GodotPckTool |
| media merger | video build | ffmpeg | — |

From a checkout, `pip install -e ".[unity,sevenzip,renpy]"` installs the `viwo` command and the
optional Python tools; other tools are found on PATH or set in the `[tools]` section of
`startup.ini`.

## Configuration

Everything lives in [`startup.ini`](startup.ini): enabled plugins, which tool is main or spare for
each job, tool locations, and the `[server]` section (host, port, default workspace, merger output,
logs, temp folders).

## Development

```bash
python -m unittest discover -s tests -t .
```

```bash
python tools/loc_count.py --report
```

Real-tool tests run with `VIWO_L5=1`; CI runs everything on Linux and Windows. Code size is capped
(non-blank, non-comment lines: 40 per function, 250 per file; budgets per package in
[`loc_caps.ini`](loc_caps.ini)).

## Documentation

- Architecture contract: [docs/contract/](docs/contract/README.md)
- Prototype A status and decisions log: [docs/prototype-a/STATUS.md](docs/prototype-a/STATUS.md)

## Legal

ViWo extracts files from games you have on your own machine. Respect the license and terms of the
games you work with; distributing extracted assets is a separate matter from extracting them.
MIT license; third-party tools keep their own licenses and GPL tools only run as separate processes.

Author: Weelson.
