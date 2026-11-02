# 14. Prototype proposal (draft 3)

## 14.1 The idea in one paragraph

A **cross-platform orchestration and curation layer for game asset
extraction**. You point it at a game. It works out which engine and which
containers it's dealing with, sends each container to the best available
existing tool (with a spare if that one fails), gathers everything into one
curated workspace, and writes down where every file came from. Runtime
capture and code analysis plug into the same workspace for what static
extraction can't reach. It is **not** a new format library. The research
(doc 13) suggests the open gap is integration, safety, curation and
provenance, not parsing.

## 14.2 What changed between draft 1 and draft 2

| # | Change | Why |
|---|--------|-----|
| 1 | Unpacking is **identify, then extract** (slot `matches` becomes an Identifier with access to both the file's head *and* tail, and can carve embedded containers) | unblob's handler/extractor split; Godot PCKs embedded in executables, AGS, Love2D and NW.js all need tail access |
| 2 | New optional **CATALOG → SELECT** step before EXPORT: a plugin lists what can be extracted (heroes, maps, bundles, paks), the user or CLI picks, and only that is exported. "Dump everything" stays the default for small games | Overwatch's storage (CASC) and big Unreal games are far too large to dump in full. DataTool, AssetStudioMod and repak already filter. It could extend INVENTORY ❓ |
| 3 | **Wrapper plugins + one re-detection**: after unpacking an outer wrapper (Electron/NW.js `.asar`, `package.nw`), detection runs again on the contents | covers TyranoScript, Construct and RPG Maker MV/MZ cheaply |
| 4 | New slot family **`keys.*`** (user-supplied key first; automatic key finders only as spares) | Unreal AES, Godot encryption, Overwatch keyring |
| 5 | Every backend declares its **network use**; offline is the default | DataTool fetches a remote keyring and uses Blizzard's CDN; MelonLoader calls a remote API |
| 6 | **GPL backends are always subprocess backends** | licenses (doc 13.5) |
| 7 | **Untrusted input:** never unpickle game data in-process. Risky parsers can run isolated | Ren'Py RPA and `.rpyc` are pickles; unrpa and rpatool unpickle them unsafely |
| 8 | Runtime capture has a **hard refusal policy** and a journaled game-folder overlay | doc 11 |
| 9 | Ghidra needs **JDK 25** (12.2), not "17+"; UABEA *has* a CLI (F8 corrected) | research |

## 14.3 Prototype slices (draft 3: re-sequenced after review)

The independent review (draft 2 → 3) found draft 2's S0 was "the whole
framework before any user-visible gain", and that S0–S7 was a product, not a
prototype. Draft 3 keeps **every engine and scope you chose** but splits the
work into an urgent hotfix plus two prototypes:

| Slice | Content | Main / spare demonstrated |
|-------|---------|---------------------------|
| **S-1 v1 hotfix** (urgent, in v1, small) | H1: copy instead of moving out of the game folder · H2: the workspace marker check before `rmtree` · H3: the API token, JSON-only, Host check, static/preview containment · F17: safe extraction filters · F1: Unity exports into staging · F3: dot-folder filter | — |
| **Prototype A: a viable core** | | |
| S0 lean core | `contracts`; ProcessRunner, ToolLocator and FileSystemPolicy for Linux and Windows; one flat startup ini; slot binder (**failover only**); stage runner (identify/carve → unpack → collect → verify → report); workspace lock; jobs + run records; CLI `info`, `detect`, `extract`, `unpack`, `serve`; `/api/extract` and merger build as job adapters; `generic` plugin | `.7z`: 7z CLI → py7zr |
| S1 Ren'Py | safe RPA reader + unrpa subprocess spare; `game/` source root (copied, not moved) | rpa-safe → unrpa |
| S2 Unity | port v1 with D3/D7 decided; UnityPy ↔ AssetStudioModCLI swappable from the ini | UnityPy → AssetStudioModCLI |
| S3 Godot | PCK v1–v4, carving of embedded PCKs, GDRE → GodotPckTool | GDRE → GodotPckTool |
| **Prototype B: breadth** (after A is green) | | |
| S4 Unreal unpack | repak → QuickBMS; retoc; AES key as a plugin option | repak → QuickBMS |
| S5 custom plugin | loader for out-of-tree plugins (`user_plugins/`); **an open-source custom-engine game as the CI showcase**; **Overwatch (DataTool) as an optional, local-only plugin** with offline defaults, if you keep it (D14) | DataTool → CascLib |
| S6 mixed + sanitizer P1 | exhaustive selection tests + pairwise pipeline runs (doc 3.6); report-only sanitizer | — |
| S7 capture pilot | policy + journal + RenderDoc texture capture + DIFF, on an open game | RenderDoc → apitrace |

## 14.4 How we'd know it works

**Prototype A is done when:**
1. CLI and HTTP extraction of the Ren'Py, Unity and Godot fixtures pass on the Linux and Windows CI runners, with the game folder's hashes unchanged.
2. Each slot used by A passes the failover cases (main up/down × spare up/down) with fakes. L5 smoke tests pass with the real tools.
3. The v1 web UI works (characterization tests, compared against the *intended* behavior after S-1, with a written list of intended differences).
4. Re-running from a run record gives an identical workspace (names, sizes, hashes).
5. Product LoC ≤ **5,500** (doc 15). The startup ini with each single profile boots on its native runner. Ini files for the other kernel are validated but not booted.

**Prototype B is done when:** the doc 14.4 draft-2 criteria hold for all
five engines, product LoC ≤ 8,000, and the capture pilot's refusal and restore
tests pass.

## 14.5 Not in either prototype

UI redesign (beyond option forms rendered from plugin data, and maybe a run
history list), Wine adapters, decompiler backends beyond the hook,
sanitizer apply/transcode, Unreal asset export, additional engines (RPG
Maker, Electron/NW, GameMaker are next, doc 13.3), and third-party
vendoring beyond what S0–S3 need (doc 10's open problems come first).

## 14.6 Biggest risks

| Risk | Mitigation |
|------|-----------|
| Building on v1 semantics that are wrong (counts, layouts) | glossary first (doc 0); characterization tests before migrating; honest metrics |
| Third-party tools change or break (DataTool after every game patch, Cpp2IL pre-release) | pin versions; spares; slot self-tests (`rpyx slots --check`) |
| Legal and terms-of-service exposure | static first; capture refusal policy; offline defaults; clear user responsibility; no evasion features |
| Scope creep (it's a framework) | slices with exit criteria; each new engine is a plugin with fixtures, not a core change |
| Linux parity for Windows-only tools | prefer tools with native Linux builds (repak, retoc, GDRE, AssetStudioMod, DataTool CI); Wine is out of scope for now |

## 14.7 Decisions still open (collected)

D0 terminology · D2 missing dependency = disable the plugin? · D3 Unity layout
· D7 Unity export main (UnityPy vs AssetStudioMod) and supplement mode ·
D8/D9 vendoring and license · D10 hotfix H1–H3/F17 first · **D11** RPA:
safe native reader as main? · **D12** CATALOG/SELECT as its own stage? ·
**D13** journaled overlay or a game copy for runtime agents? · **D14**
Overwatch or an open-source showcase for S5? · **D15** CLI and product name.
