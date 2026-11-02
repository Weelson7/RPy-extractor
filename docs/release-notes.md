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
- Web UI: extract, workspace, sort, jobs, system, merger, survey, cleanup, patched copy.

**Never**: writes to your game folder, circumvents DRM or anti-cheat, or guesses keys.

Known limits are listed in `docs/prototype-b/STATUS.md`.
