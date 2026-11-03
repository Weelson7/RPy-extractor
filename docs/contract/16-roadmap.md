# 16. Roadmap (draft 3; state of 1.1 noted per milestone)

> **History (2026-11-03):** every milestone through M12 is delivered or consciously replaced; the
> "State" notes below record the evidence and the replacements. M13+ items that shipped are marked.

Milestones are gated by decisions (README), LoC budgets (doc 15) and tests
(doc 17). There are **no dates**: each milestone is sized by its LoC budget
and its exit criteria. Every milestone leaves the app working, and the v1 web
UI stays usable throughout.

Draft 3 change, after the independent review: an **urgent hotfix comes
first** (v1 moves files out of game folders and can delete a user-chosen
folder), and the prototype is split into **A (viable core)** and
**B (breadth)**.

## 16.0 Prototype B composition (decided D16-D19)

Prototype B = M7 Unreal unpack (+ AES key finder spare) · M8 custom plugins (Doom WAD/Freedoom in CI, Overwatch tos-sensitive) · M9 round trip for all four engines · M10 mixed mode + sanitizer phase 1 · **M11 capture pilot moved inside B**. Prototype A was extended first: legacy app removed, everything ported to ViWo, new UI.

**State:** all of the above delivered, plus the D21 coverage ladder; see `docs/prototype-b/STATUS.md` for evidence and the list of items not yet verified on real data.

## 16.0b Coverage ladder (D21)

Goal: any asset stored on the local disk comes out, whatever the engine. Each rung catches what
the rungs above it missed, and every rung reports what it could not handle, so gaps are visible.

| Rung | What it does | State |
|------|--------------|-------|
| 1. Engine plugins | native decoding with real names (Ren'Py, Unity, Godot, Doom; Unreal M7; then RPG Maker, KiriKiri XP3, Electron asar, Source VPK, Bethesda BSA/BA2, GameMaker) | partly done |
| 2. Container unpackers | zip, tar, 7z, rar, WAD, PCK, RPA..., recursive to depth 10 | done |
| 3. Signature carver | complete standard files embedded in unknown blobs (PNG, JPEG, GIF, WAV/WEM, Ogg, MIDI, MP4, Bink, FSB5, BNK, DDS, glTF, zip, 7z) | done |
| 4. Compressed-stream scan | zlib and gzip streams inside unknown blobs are inflated (bounded) and carved; zstd / LZ4 when their modules are present | done (zlib, gzip always; zstd, LZ4 when `zstandard` / `lz4` import: `tests/test_carve.py::OptionalStreamTests`) |
| 5. Decoders | game media to viewable files: vgmstream (WEM, FSB, BNK...), DDS to PNG, Bink via ffmpeg (opt-in) | done |
| 6. Script-driven unpackers | QuickBMS (GPL, subprocess): `[options.quickbms] scripts = <folder>`, one `<ext>.bms` per format, in every game | done (flags not yet verified on a binary) |
| 7. Runtime capture | RenderDoc / audio capture for encrypted or procedural content (M11, policy-gated) | pilot done (RenderDoc) |
| Survey | `viwo survey <library>`: per game, the engine, which files each rung covers, and unknown blobs with a density estimate (dense = encrypted/compressed) | done |

Not authored first-party (philosophy point 5, D22): ViWo writes no DRM-defeat, no anti-cheat
evasion, no key brute-forcing. These are not refusals — nothing is refused for what a game is — they
are things the *project* does not author; a user who wants them runs a pinned third-party tool or
community script under the disclaimer. Content that only exists decoded at runtime is in scope via
the dynamic arm (doc 11); keys come from the user or the game's own local files and are verified
(D18). This ladder is the **extraction** arm; the **static-analysis** (doc 6) and **dynamic/runtime**
(doc 11) arms are their own ladders, below.

## 16.1 Overview

```
M0 Decisions ─▶ M1 Hotfix+Safety net ─▶ M2 Contracts+OS layers ─▶ M3 Lean core+CLI ─┬▶ M4 Ren'Py ─┐
                                                                                   ├▶ M5 Unity  ─┼▶ ★A
                                                                                   └▶ M6 Godot  ─┘
★A ─▶ M7 Unreal unpack ─┬▶ M9 Round trip ─▶ M10 Mixed + Sanitizer P1 ─▶ ★B ─▶ M11 Capture pilot ─▶ M12 Vendoring ─▶ M13+
      M8 Custom plugins ─┘
```

## 16.2 Milestones

| M | Name | Content | Needs | New LoC cap | Exit criteria |
|---|------|---------|-------|-------------|---------------|
| **M0** | Decisions & semantics | sign-off on docs 0–17; close or explicitly park D0–D15; rewrite the scratchpad interface draft to match draft 3 | — | 0 | glossary + caps agreed; decision table filled in |
| **M1** (done; L2 golden files replaced by removing v1, doc 17.1) | **Hotfix + safety net** (hotfix part **done**: branch `hotfix/v1-data-safety`) | **in v1:** H1 copy-not-move, H2 workspace marker, H3 token/JSON-only/Host/containment, F17 safe extraction, F1 exports to staging, F3 dot-folder filter. **Then** the L2 characterization tests against the *intended* behavior, with an intended-differences list; LoC counter + L0 in report-only mode; CI on Linux + Windows | D10 | hotfix ≤ 250 in v1; counter ≤ 120 | H1/H2/H3/F17 regression tests green; golden files committed |
| **M2** (done; conformance kit: `tests/test_conformance_kit.py`, OS layers: `tests/test_os_layer.py`) | Contracts + OS layers (lean) | `contracts/`; conformance kit; ProcessRunner (tree-kill, timeout), ToolLocator, FileSystemPolicy for Linux and Windows; v1 OS code behind them; installer/shell kept as thin v1 adapters | D0, D2, D6 | contracts 900; OS layers 900 | L1 green on both OSes; L2 unchanged; F4, F13 gone |
| **M3** (done; `docs/prototype-a/STATUS.md`) | Lean core + CLI | flat startup ini; slot binder (failover only); stage runner (identify/carve, unpack, collect copy/move, verify, report); workspace (marker, lock, three trash layouts); jobs + run records + envelope; CLI `info/detect/extract/unpack/serve`; v1 routes as adapters (doc 4.1 mapping); `generic` plugin; core backends zip/tar/7z/rar/py7zr. If it overruns, split into M3a (wiring + slots + CLI on the v1 pipeline) and M3b (new stage runner) | D3, D12, D15 | pipeline 900, wiring 500, jobs 350, workspace 800, api 700, cli 400, backends 600 | L0 **blocking**; L1–L4 for generic; L2 matches the intended behavior; replay identical; `.7z` failover shown |
| **M4** (done) | Ren'Py | safe RPA reader (main) + unrpa subprocess (spare); source root copied | D11 | 500 | malicious-RPA test; v1 Ren'Py parity on L2; L5 with unrpa |
| **M5** (done; real-file round trip is an L7 item) | Unity | v1 port; UnityPy ↔ AssetStudioModCLI per D7; placeholder slices and the fake completeness gate removed | D7 | 700 | parity on fixtures minus F1/F11; swap from the ini shown; L5 |
| **M6** (done) | Godot | PCK v1–v4; carving of embedded PCKs; GDRE → GodotPckTool; key as a plugin option | — | 500 | PCK fixtures (embedded, encrypted); L5 with both tools. **★ Prototype A** (doc 14.4) |
| **M7** (done; `unarchive.upak` is repak main with `quickbms-cli` as spare when the quickbms plugin is on and a `.pak` script sits in the scripts folder; engine distros without that plugin bind no spare; the indexes supply scripts per game) | Unreal unpack | repak → QuickBMS; retoc; AES key option | — | 500 | pak fixtures built with repak; export explicitly out of scope |
| **M8** (done; CATALOG closed per D12) | Custom plugins | out-of-tree loader (`user_plugins/`, entry points); open-source custom-engine showcase (CI); optional local-only Overwatch plugin (D14); CATALOG → SELECT if D12 says yes | D5, D12, D14 | loader ≤ 200; plugins ≤ 300 each | conformance from outside the tree; offline defaults verified |
| **M9** (done; the patched copy is a plain copy, copy-on-write clones were not pursued; untouched members are hash-verified since 1.1) | Round trip (repack) | provenance-based edit set; per-plugin `repack_plan`; patched game copy (copy-on-write clones where supported); `pack.*` slots for Ren'Py (override + RPA writer), Godot (PCK rebuild), Unreal (`_P.pak` via repak), Unity (UnityPy save, same-format); verification by re-extraction | — | roundtrip 450; +150 per plugin | round-trip tests green for each engine; original game folder hashes unchanged; repack refused for policy-listed games |
| **M10** (done; the 9,000 target became the 10,800 budget with the 1.0-1.2 scope, doc 15.3) | Mixed + sanitizer P1 | exhaustive selection + pairwise pipeline tests; minimal mixed selector in the UI; report-only sanitizer | D1, D4 | sanitizer 400; web ≤ 300 | product ≤ 9,000. **★ Prototype B** |
| **M11** (done; the refusal list became a warnings list per D22; RenderDoc on a real GPU is an L7 item) | Capture pilot | policy + refusal list (data); journal overlay + crash recovery; RenderDoc → harvest → DIFF on an open game | D13, legal stance | capture 400 | refusal and restore tests green |
| **M12** (done as the pinned installer: `tools.json` + `viwo install --all` replaced submodules and bootstrap; the indexes become a submodule, `docs/indexes.md`; L5 runs in the CI real-tools job, no nightly by the cost rule) | Vendoring | tool lock → sparse submodules for the source-usable tools; bootstrap reapplies sparse rules; nightly L5 on vendored tools | D8, D9 | bootstrap ≤ 150 | clean clone + `viwo install --all` → `viwo slots --check` green on both OSes (shipped in 1.1) |
| **M13+** (shipped: distro layering + 12 ini files, RPG Maker, Electron/NW.js, UI option forms, run history, sanitizer panel, drop-in plugins with CLI/UI add-ons; open: `[hooks]`, GameMaker, Unreal export, sanitizer P2-3, analysis backends, Wine) | Next | distro layering + the 12 ini files + hooks; installer abstraction; RPG Maker, Electron/NW, GameMaker; Unreal export (CUE4Parse wrapper); sanitizer P2–3; analysis backends; UI (plugin option forms, run history, sanitizer panel); Wine | — | within the 10k total | per item |

## 16.2b RE orchestrator arms (post-1.x; the respec)

1.0–1.2 delivered the **extraction** arm (16.0b) plus the capture pilot (M11) and the normative
shapes for the other two arms (doc 6, doc 11, doc 18). The respec turns those shapes into rungs. Each
is additive: a slot family group, pinned tools, a job type, a feature flag off by default, and UI
(headless backend + a "continue in &lt;tool&gt;" handoff, doc 8.3a). No core invariant changes;
nothing is refused (D22). Rungs are sized by LoC like every milestone and ship one tool path at a
time.

| Arm | Rung | Content (doc) | Pinned tools (main) | temp.md |
|-----|------|---------------|---------------------|---------|
| Static | A1 | `analysis.native` + Ghidra GUI handoff; `.analysis/` output; `analysis` flag | Ghidra headless, JDK 25 | §1–4 |
| Static | A2 | managed/bytecode: `analysis.dotnet`, `analysis.il2cpp`, `analysis.script` | ilspycmd, Cpp2IL, unluac | §5, §13 |
| Static | A3 | `analysis.signatures`, `analysis.diff` (update resilience), `analysis.protector` | Ghidra FID, BinDiff, DIE | §4, §14, §16 |
| Static | A4 | `analysis.emulate`, `analysis.symbolic` (isolated routines) | Unicorn/Qiling, angr | §15 |
| Dynamic | D1 | capture pilot hardened to a real GPU; shader disasm | RenderDoc | §11 |
| Dynamic | D2 | `runtime.<engine>` agents feeding static extraction; `capture.audio` | BepInEx, UE4SS, Frida | §5, §11 |
| Dynamic | D3 | `debug.*`, `trace.*`, `memory.*` headless backends + handoffs | x64dbg, Frida, Cheat Engine | §6, §7, §8 |
| Dynamic | D4 | `hook.inject` loader + hot-reload; `net.*` own-traffic tooling; `profile.*` | our loader, tshark, Tracy | §9, §10, §20 |
| Authoring | T1 | `patch.bytes` + `patch.sig` (AOB), patch export (18.8) | our writer, Keystone (lib) | §9, §16 |
| Authoring | T2 | `mod.package`: loader, stable API layer, crash handler, update checker (18.9) | — (glue + SDK) | §19 |

Sequencing: A1→A3 first (static is low-risk and feeds everything), then D1→D2 (asset runtime), then
T1 (needs A1/A3 for addresses), then D3→D4 and T2 as demand shows. Cross-cutting: the `runtime`
feature flag, `os.launch`, and the handoff launcher (doc 8.3a) are shared plumbing built once at D1.
The LoC total cap holds; each rung requests its own budget line in `loc_caps.ini` with a reason, and
because every heavy capability is a pinned third-party tool driven as a subprocess, first-party code
per rung stays small (slot wiring, a prepare/handoff shim, a UI view).

## 16.3 Decision gates

| Gate | Before | Decisions |
|------|--------|-----------|
| G0 | M1 | D10 (H2 fix approach), re-extraction policy (doc 4.3) |
| G1 | M2 | D0 terminology, D2 missing dependency, D6 macOS |
| G2 | M3 | D3 Unity layout, D12 catalog stage, D15 name |
| G3 | M4/M5 | D11 safe RPA reader, D7 Unity export main |
| G4 | M8 | D5 declarative plugins, D14 showcase |
| G5 | M11 | D13 overlay vs copy; written legal/terms-of-service stance |
| G6 | M12 | D8 vendoring (D9 license already decided: MIT core) |

## 16.4 Risks to the roadmap

| Risk | Signal | Response |
|------|--------|----------|
| M3 is the big one | budget overrun or a pile of L2 differences | split into M3a/M3b (above) |
| v1 "behavior" includes bugs | golden diffs that are really fixes | every one goes on the milestone's intended-differences list |
| Third-party tool churn | L5 failures in the real-tools job | pins (`tools.json`) + spares + `viwo slots --check` (backend self-tests, 1.1) |
| Caps too tight somewhere | repeated exception requests | revisit only at milestone boundaries |
| Hotfix delayed by the overhaul | M1 slips | M1 doesn't depend on any decision except D10; ship it on its own |
