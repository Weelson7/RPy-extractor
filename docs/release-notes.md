## ViWo (Vidya Wormhole) 0.2.0: Prototype B

A local-first game reverse-engineering platform, oriented towards asset extraction.

**Downloads**
- `ViWo-0.2.0-windows-x64.zip`: portable Windows build. Unzip, run `viwo.exe serve` (opens
  your browser). No Python needed. Optional tools (7-Zip, ffmpeg, vgmstream, GDRE Tools,
  repak...) are listed in the README with where to get them; `viwo.exe slots` shows what is found.
- `viwo-0.2.0-py3-none-any.whl` / `.tar.gz`: for `pip install` (Python 3.11+).

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

Known limits are listed in `docs/prototype-b/STATUS.md`.
