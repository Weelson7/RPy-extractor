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
| M11 | runtime capture pilot: refusal policy, journaled overlay, RenderDoc capture + harvest, diff vs static | done (RenderDoc itself not run, see below) |
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

## Not verified yet (honest list)

| Item | Why | How it gets verified |
|------|-----|----------------------|
| Unity round trip on a real Unity file | no redistributable Unity fixture; tested with a stateful fake UnityPy | real-game check (D20) |
| RenderDoc capture / harvest | no GPU on CI; tested with fake `renderdoccmd` and fake RenderDoc Python | operator run on a desktop |
| QuickBMS flags (`-o -Y script input output`) | binary host not reachable from this environment | first real use / CI if a mirror is allowed |
| DataTool modes on a real install | Overwatch is tos-sensitive | independent operator (doc 17.4b) |
| Real commercial games end to end | D20: after Prototype B | you / the operator |
| retoc IoStore conversion on real UE5 data | no redistributable UE5 IoStore fixture | real-game check |

## Rules that hold everywhere

- The game folder is only read: extraction copies, repack writes a separate marked copy, capture
  agents write through a journal that is restored.
- No DRM or anti-cheat circumvention; no password or key guessing. Keys come from the user or from
  the game's own files and are verified (D18). Capture is refused when anti-cheat or an online title
  is detected.
- Secrets and found keys are never logged or written to disk.
