# RPy Extractor

RPy Extractor is a local-first desktop tool to extract, triage, and compose game media assets.

It runs as a Python app with a browser-based interface and is designed for creators, modders, and archivists who want a fast workflow from raw game files to curated outputs.

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
- Media Merger for timeline builds with transitions, conflict resolution, and loop controls.
- Media Merger for timeline builds with transitions, conflict ordering, and loop controls.

## Media Merger Highlights

- Merge mixed media in one output timeline (for example `.webm` + `.png`).
- Transition modes:
- `diapo` with delay
- `fade` with cross time
- Optional overlay soundtrack looped over native video audio.
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
