# Prototype B: status

Branch `makeover`. Decisions D16–D21 (`docs/contract/README.md`). Roadmap: doc 16.
This file records what Prototype B delivered, what is verified and how, and what is still open.

## Milestones

| M | Scope | State |
|---|-------|-------|
| M7 | Unreal: `.pak` (repak), IoStore `.utoc/.ucas` (retoc to legacy, raw as spare); AES per D18 (user key, else key from the game's executables, verified on the pak index) | done |
| M8 | custom-engine showcase: Doom WAD (Freedoom on CI); Overwatch via DataTool (tos-sensitive, operator-tested); QuickBMS bridge for any scripted format | done |
| M9 | round trip into a verified patched copy: loose override, Ren'Py RPA rebuild, Godot PCK, Unreal `_P.pak`, zip, Unity (TextAsset / Texture2D), RPG Maker MV/MZ | done |
| M10 | mixed mode over every plugin pair; sanitizer phase 1 (plan / apply safe / undo) | done |
| M11 | runtime capture pilot: warnings policy (no refusals), journaled overlay, RenderDoc capture + harvest, diff vs static | done (RenderDoc itself not run, see below) |
| D21 | coverage ladder: carver, zlib/gzip streams, decoders, survey, more engines | done |

Engines added in B: Unreal, Doom engine, RPG Maker (XP/VX/VX Ace archives, MV/MZ media), KiriKiri
XP3, Electron asar, Source VPK, Bethesda BSA/BA2, Overwatch, plus QuickBMS scripts for anything else.

## Evidence

CI (GitHub Actions, Linux and Windows, Python 3.11 and 3.13, plus real-tool jobs). Run
41426550274 (`workflow_dispatch`, commit 3c0c29d) passed all six jobs, and the Linux real-tool job
ran, not skipped:

- **Unreal:** repak builds a pak that the pipeline extracts. The round trip writes `_P.pak` with real repak and verifies it by re-extraction.
- **Godot:** GDRE Tools and GodotPckTool extract standalone and embedded PCKs. The round trip rebuilds a PCK with real GodotPckTool and verifies it.
- **Audio:** vgmstream r2168 decodes a Wwise PCM `.wem` to WAV.
- **Doom:** Freedoom 0.13.0 extracts to more than 2,500 PNG, more than 80 WAV and more than 30 music files, with the game folder unchanged.
- **Earlier tools:** 7-Zip, unrar, unrpa, UnityPy and AssetStudioModCLI, still green.

Synthetic tests cover every format plugin, the carver (every format at a known offset, no hits on
noise), streams, survey, sanitizer, round trip, capture policy, the journal with crash recovery, and
91 mixed-mode extractions.

## 1.0 evidence (local, Windows 11, 2026-11-02)

- **Startup installer:** `viwo install <every id>` installed all 17 pinned dependencies into
  `third_party/` from the real pinned URLs with checksums verified: repak, retoc, vgmstream, GDRE
  Tools, GodotPckTool, AssetStudioModCLI (on the pinned .NET 10 runtime under `third_party/dotnet`),
  7-Zip (MSI administrative unpack), ffmpeg, ffprobe, unrar (self-extractor opened by 7-Zip),
  QuickBMS, DataTool, RenderDoc (`renderdoccmd` and `qrenderdoc --py` as the harvest Python),
  unrpyc, plus UnityPy, py7zr, unrpa and lz4 into `third_party/python`. `viwo slots` binds every
  slot afterwards, including `capture.gpu` and `export.overwatch`. Two defects found and fixed on
  the way: msiexec needs its quotes verbatim (paths with spaces), and a slow link can end a
  download early (now retried with a size check).
- **Preflight API:** `POST /api/preflight` as a job with one event per check and install; the
  landing screen and 05 SYSTEM INSTALL buttons drive it.
- **Web UI in a real browser (headless Edge, 1440x900):** the landing ran the real preflight
  ("All 19 tools ready"), then 01 EXTRACT, 05 SYSTEM (19/19 tools, 33/33 formats), 10 CAPTURE and
  11 SETTINGS rendered with zero JavaScript console errors. Interaction flows (install buttons,
  settings apply, capture run) were exercised through the HTTP API and unit tests, not by clicks.
- **Portable bundle (Windows):** `packaging/build_portable.py` builds `dist/viwo/viwo.exe`, the
  smoke test passes, and `viwo.exe install repak` downloads over HTTPS into `third_party/` next to
  the exe and binds the slot. Two bundle defects fixed: no `ssl` module collected, and a foreign
  OpenSSL DLL picked up from PATH (the interpreter's own copies now ship).
- **Linux installer (WSL Ubuntu, Python 3.12):** `viwo install --all` into a Linux-only home
  installed all 18 Linux pins (DataTool is Windows-only by design) and every slot bound; the
  archive modes are applied on unpack, so the binaries run without a manual chmod.
- **Windows Defender false positive:** the GodotPckTool v2.3 Windows binary is flagged by
  Defender's ML heuristic (Trojan:Win32/Wacatac.B!ml) and quarantined right after download; the
  installer reports it as a failed install with the antivirus hint. GDRE Tools (main) keeps `.pck`
  extraction working; Godot patched copies (`pack.pck`) need the user to allow the
  `third_party/godotpcktool` folder in Defender, or a newer upstream build. No newer release exists.
- **Merger on ffmpeg 7:** xfade needs a constant frame rate after setpts (fixed, test green with
  ffmpeg 7.1.1 on Windows).

## Not verified yet (honest list)

| Item | Why | How it gets verified |
|------|-----|----------------------|
| Unity round trip on a real Unity file | no redistributable Unity fixture; tested with a stateful fake UnityPy | real-game check (D20) |
| RenderDoc capture / harvest | no GPU on CI; tested with fake `renderdoccmd` and fake RenderDoc Python | operator run on a desktop |
| QuickBMS flags (`-o -Y script input output`) | binary host not reachable from this environment | first real use / CI if a mirror is allowed |
| DataTool modes on a real install | Overwatch is tos-sensitive | independent operator (doc 17.4b) |
| Ghidra GUI handoff on a real project | the headless run is verified (below); the GUI launch is tested with a fake `ghidraRun` | 12 ANALYSIS > CONTINUE IN GHIDRA on a desktop (sqc 16) |
| Real commercial games end to end | D20: after Prototype B; eleven free titles verified on 2026-11-03 (below) | the operator for tos-sensitive titles |

## Real-game evidence (2026-11-03, `tools/integration_games.py`, Windows 11)

Every game folder hashed before and after; detect, survey, extract, repack plan and sanitize plan
ran on each; 11/11 passed (`viwo-data/integration/report.md`, not committed).

| Game | Engine | Result |
|------|--------|--------|
| Doki Doki Literature Club 1.1.1 | Ren'Py 95 % | 8/8 RPA, 797 files, 35 `.rpyc` decompiled to `.rpy` (unrpyc) |
| Freedoom 0.13.0 | Doom 90 % | 2/2 WAD, 4,100 files (3,095 PNG, 109 WAV, 76 MIDI) |
| ULTRAKILL Prelude, Baldi's Basics CR, Burning Snow | Unity 92 % | UnityPy: 5,481 / 1,761 / 116 files (textures, audio, meshes to OBJ) |
| Void's Cave DEMO, The Basement | Unreal 5 92 % | 3/3 containers each (`.pak` by repak, `.utoc/.ucas` by retoc): 5,312 / 2,623 files |
| My first shitty game with RPG Maker MV | RPG Maker 90 % | 1,512 files, encrypted media decrypted (1,118 PNG, 264 OGG) |
| Ubu 2.0b | KiriKiri 90 % | 3/3 XP3, 1,984 files |
| GodotOne, "MAD game" | Godot 60 % | bare export templates: the PE `pck` section is empty and no `.pck` is beside the exe; reported as "no PCK data" (1.2.2) |

Static analysis (1.3, Ghidra 12.2 + Temurin 25 installed by `viwo install ghidra`):
`viwo analyze Test-games/ultrakill-prelude --target ultrakill-exe` ran headless in about a minute
and wrote `functions.csv` (324 functions), `decompiled.c` (11,473 lines), `strings.txt`,
`symbols.tsv` and `record.json`; the project `viwo.gpr` sits in `<workspace>.ghidra/ultrakill-exe/`.
Found on the way: `cmd /c` drops the quotes of a batch path with spaces (`call` fixes it), Ghidra
12.2 refuses JDK 21 (25 pinned) and any project path element starting with a dot.

retoc on real UE5 IoStore data and the Unreal `.pak` path are verified by the two UE5 titles;
the Godot PCK path still waits for a title that ships its data (`sqc/games.md`).

## Rules that hold everywhere

- The game folder is only read: extraction copies, repack writes a separate marked copy, capture
  agents write through a journal that is restored.
- No policy boundaries in code (owner's decision, 1.0): anti-cheat, online titles and sensitive
  plugins produce warnings and one confirmation, never refusals; the user is responsible (README:
  Philosophy, Legal and disclaimer). Keys come from the user or from the game's own files and are
  verified (D18); ViWo authors no code for defeating copy protection or brute-forcing keys.
- Secrets and found keys are never logged or written to disk.

## Known limits (1.2.1)
- Round trip: packers with their own `verify` (Unity bundles, RPG Maker MV) have no `unarchive.*`
  route back, so re-extraction checks the edited members only; the in-place save keeps the other
  objects and the repack report says "untouched members were not re-verified" (doc 18.3). Ren'Py,
  zip, Godot and Unreal containers are re-extracted and every untouched member's hash is checked.
