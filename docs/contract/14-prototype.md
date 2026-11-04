# 14. Product scope and structural choices

## 14.1 The product in one paragraph

A local-first orchestrator for game reverse engineering. Point it at a game: it works out the
engine and the containers, sends each container to the best available tool (with a spare when
that tool is missing or fails), gathers everything into one curated workspace and records where
every file came from. From there the same plumbing analyses the game's code, captures and
instruments the running game, and writes changes into a patched copy. ViWo is not a format
library: its value is integration, safety, curation and provenance.

## 14.2 Structural choices

Numbered; code cites them as "doc 14.2 #n".

| # | Choice | Why |
|---|--------|-----|
| 1 | Unpacking is **identify, then extract**: a slot's identifier sees a file's head and tail and can report an embedded chunk the core carves out first | embedded Godot PCKs, data appended to executables |
| 2 | No catalog stage: SELECT, `viwo survey` and the per-game indexes say what a folder holds (D12) | one less pass over large games |
| 3 | **Wrapper re-detection:** after an outer wrapper (`.asar`, `package.nw`) is unpacked, detection runs once more on its content (`viwo/core/pipeline/export.py`) | TyranoScript, Construct, RPG Maker MV/MZ inside Electron/NW.js |
| 4 | Keys are plugin options of kind `secret` (user first), with a key finder that reads only the game's own files and verifies every candidate (D18) | Unreal AES, Godot encryption |
| 5 | Every backend declares its network use (`none`, `download`, `any`) | DataTool and BepInEx fetch; everything else is offline |
| 6 | GPL/AGPL backends are always separate processes | licenses (doc 13.5) |
| 7 | Untrusted input: game data is never unpickled freely in process; risky parsers declare it | Ren'Py pickles |
| 8 | The dynamic arm is a feature switch plus warnings and one confirmation, never a refusal (D22); agents run in a patched copy (D13) | philosophy; the game folder stays read-only |
| 9 | Heavy capability comes from pinned third-party tools driven as processes; first-party code is glue | small, reviewable core under the LoC caps (doc 15) |
| 10 | Every engine is a plugin with fixtures; no engine knowledge in core | adding an engine needs no core change |

## 14.3 Out of scope

- An installer or packaged desktop app beyond the portable Windows zip and the wheel.
- macOS and Wine adapters.
- First-party DRM defeat, key brute force, anti-cheat evasion (philosophy point 5).
- Content that exists only on a server.

## 14.6 Risks and their mitigations

| Risk | Mitigation |
|------|-----------|
| Third-party tools change or break (DataTool after game patches, Cpp2IL pre-releases) | pins with checksums; spares; backend self-tests (`viwo slots --check`); the L5 real-tool job |
| Wrong metrics give false confidence | honest metrics (doc 0.4); no completeness claim without an inventory |
| Legal and terms-of-service exposure | static first; warnings and one confirmation; offline defaults; the disclaimer; no evasion code |
| Scope creep | each engine is a plugin with fixtures; caps per package (doc 15) |
| Linux parity for Windows-only tools | prefer tools with native Linux builds (repak, retoc, GDRE, AssetStudioMod, Detect It Easy); Windows-only pins are listed (doc 13.6) |
