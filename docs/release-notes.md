## ViWo (Vidya Wormhole) 1.0.0: first product release

A community-owned, local-first orchestrator for game reverse engineering, oriented towards asset
extraction. For reverse engineers, modders, artists and anyone who wants to look inside a game.

**Downloads**
- `ViWo-1.0.0-windows-x64.zip`: portable Windows build. Unzip, run `viwo.exe serve` (opens
  your browser). No Python needed. Every optional tool (7-Zip, unrar, ffmpeg, vgmstream, GDRE
  Tools, GodotPckTool, AssetStudioModCLI, repak, retoc, QuickBMS, DataTool, RenderDoc, unrpyc,
  a .NET runtime) installs itself into `third_party/` next to `viwo.exe` on first start: pinned
  versions, HTTPS, checksums verified. `viwo.exe slots` shows what is bound.
- `viwo-1.0.0-py3-none-any.whl` / `.tar.gz`: for `pip install` (Python 3.11+); run
  `viwo install --all` once for the tools.

**What is in it**
- Engines: Ren'Py, Unity, Godot, Unreal (pak + IoStore, AES keys verified from the game's own
  files), Doom engine, RPG Maker, KiriKiri, Electron/NW.js, Source, Bethesda, Overwatch (chosen
  explicitly), plus QuickBMS scripts for any other format.
- Anything else: a carver that finds standard images, audio, video and archives inside unknown
  files, zlib/gzip stream inflation, and decoders (game audio to WAV, DDS to PNG).
- `survey` a whole library, `sanitize` a workspace (with undo), `repack` your edits into a
  verified patched copy of the game, and a runtime-capture pilot (RenderDoc, off by default).
- Web UI: a landing screen that installs the missing tools, then extract, workspace, sort, jobs,
  system (install buttons, updates, diagnostics), merger, survey, cleanup, patched copy, capture,
  settings.

**Philosophy** (README): a community tool, MIT, forkable. For everyone who wants to look inside a
game, with no judgement of user or purpose. No boundaries and no safeguards in the code: nothing
is refused because of what a game is; anti-cheat and online detection are warnings plus one
opt-in. A disclaimer replaces safeguards: ViWo and the third-party tools and scripts it ships
could be misused; the project neither condones nor suggests it and the responsibility is the
user's. Borderline code is never first-party. The game folder is never written to.

**New in 1.0 (since the Prototype B handoff):** automatic tool installer and landing screen,
10 CAPTURE and 11 SETTINGS views, per-game indexes (`indexes/`, `viwo install --game`,
`viwo indexes update`), drop-in plugins with manifests, Ren'Py script decompilation, Unity mesh
export, diagnostics bundle (`viwo diag`), update checks, a manual check suite (`sqc/`), and the
philosophy change: no policy boundaries in code, a disclaimer instead.

Known limits and what is not yet verified on real games: `docs/prototype-b/STATUS.md`.
