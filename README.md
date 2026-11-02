# RPy Extractor

RPy Extractor is a local-first desktop tool to extract, triage, and compose game media assets.

It runs as a Python app with a browser-based interface and is designed for creators, modders, and archivists who want a fast workflow from raw game files to curated outputs.

## Vidya Wormhole (ViWo): the new core

This app is being rebuilt as **ViWo**, a cross-platform game asset extraction and curation
framework (contract: [docs/contract/](docs/contract/README.md), status:
[docs/prototype-a/STATUS.md](docs/prototype-a/STATUS.md)). The web UI below still works;
extraction now runs through the ViWo core, which never modifies the game folder.

```bash
python -m viwo.cli info                                  # OS layer, plugins, slot bindings
python -m viwo.cli detect "/path/to/game"                # engine detection
python -m viwo.cli extract "/path/to/game" --workspace ./ws   # extract into a workspace
python -m viwo.cli serve                                 # web UI (same as python Start.py)
```

Supported in Prototype A: generic archives (zip, tar, 7z, rar), Ren'Py (safe RPA reader, unrpa
as spare), Unity (UnityPy, AssetStudioModCLI as spare), Godot (GDRE Tools, GodotPckTool as spare;
PCKs embedded in executables). Wiring is configured in `startup.ini`.

Tests: `python -m unittest discover -s tests -t .` (set `VIWO_L5=1` to include real-tool
tests); code size caps: `python tools/loc_count.py --report`.

## What You Can Do

- Extract archives and asset folders from supported game structures.
- Filter by extension types and keep only what matters.
- Review files quickly in a sorting window with preview + keyboard actions.
- Use trash/restore/undo flows during curation.
- Build merged videos from mixed media (images + videos) in the Media Merger panel.
- Navigate large candidate sets efficiently with paged candidate browsing.

## Typical Use Cases

- Triage large extracted asset sets and keep only production-ready files.
- Build quick media reels from texture/video dumps.
- Recover and organize media from RenPy and Unity projects.
- Prepare selected outputs for editing pipelines or dataset curation.

## Main Workflow

1. Extract archives from a game folder.
2. Scan extensions and keep selected types.
3. Continue in Workspace Panels:
- Sorting Window for manual keep/trash/rename.
- Media Merger for timeline builds with transitions, conflict ordering, and loop controls.

## Media Merger Highlights

- Merge mixed media in one output timeline (for example `.webm` + `.png`).
- Transition modes:
- `diapo` with delay
- `fade` with cross time
- Optional overlay soundtrack looped over native video audio.
- End controls:
- fadeout (`time`): fades video and audio at the timeline end.
- last image (`time`): freezes the final frame for the configured duration (works when the last item is an image or a video).
- Per-candidate controls:
- Loop entirety (`times`)
- Loop parts (indexes + times), with auto-add row and explicit `+` add-row button.
- Same-index mixed-media conflict ordering with Up/Down controls; ordering is applied automatically.
- Paged candidate list (Prev/Next) for responsive handling of large media folders.

## Dependency Status In App

The app surfaces dependency readiness directly in the UI, including:

- required: `unrpa`
- optional: `7zip`, `unrar`, `ffmpeg + ffprobe`, Unity tooling

This helps you immediately understand which features are fully available.

## Run

From repository root:

```powershell
python Start.py
```

## Configuration

Runtime config file:
- [RPy-extractor/config.json](RPy-extractor/config.json)

Important paths:
- `tempPath`: working temp directory
- `outputDir`: extracted asset output base
- `mergerDir`: merged media output directory
- `logDir`: runtime logs

## Documentation

- Product/use-case docs: [README.md](README.md)
- Technical architecture details: [ARCHITECTURE.md](ARCHITECTURE.md)

## Ownership

- Author: Weelson
- Initiative: C.O.R.E.
