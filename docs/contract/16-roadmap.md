# 16. Roadmap (proposal)

Milestones follow the prototype slices (doc 14) and are gated by decisions
(README), LoC budgets (doc 15) and tests (doc 17). There are **no dates**:
each milestone is sized by its LoC budget and its exit criteria. Every
milestone leaves the app working, and the v1 web UI stays usable throughout.

## 16.1 Overview

```
M0 Decisions ─▶ M1 Safety net ─▶ M2 Contracts+Kernels ─▶ M3 Core+Wiring+CLI ─┬▶ M4 Ren'Py ─┐
                                                                              ├▶ M5 Unity  ─┤
                                                                              ├▶ M6 Godot  ─┼▶ M9 Mixed+Sanitizer P1 ─▶ ★ PROTOTYPE
                                                                              ├▶ M7 Unreal ─┤
                                                                              └▶ M8 Custom ─┘
                                                     ★ ─▶ M10 Capture pilot ─▶ M11 Vendoring ─▶ M12+ next engines / UI / analysis
```

M4–M8 depend only on M3 and can run in any order or in parallel. The order
shown is the suggested risk order.

## 16.2 Milestones

| M | Name | Content | Needs decisions | New LoC (cap) | Exit criteria |
|---|------|---------|-----------------|---------------|---------------|
| **M0** | Decisions & semantics | Review and sign off docs 0–17. Close D0–D15, or record them as deliberately open. Rewrite the scratchpad interface draft to match draft 2 (code goes in at M2) | — | 0 | glossary agreed; caps agreed; README decision table filled in |
| **M1** | Safety net | L2 characterization tests of v1 (payloads + workspace snapshots on synthetic games); LoC counter + L0 gate in **report-only** mode; **reproduce F7 and F1**, and fix F7 in v1 if it reproduces (data loss) | D10 | tests + counter ≤ 120 | golden files committed; CI running on Linux + Windows; F7 fixed or disproved |
| **M2** | Contracts + kernels | `contracts/` package; conformance kit; Linux and Windows kernels (process with tree-kill, ToolLocator, installer, shell, fs); v1 OS code moved behind them **without behavior change** | D0, D2, D6 | contracts 900, kernels 1,300 | L1 green on both OSes; L2 unchanged; F4 and F13 gone |
| **M3** | Core + wiring + CLI | ini boot (doc 9); slot binder (main/spare/promote/unbound); stage runner with identify/carve, unpack, collect; workspace with reserved dot-folders; jobs + run records; CLI (`info`, `detect`, `extract`, `unpack`, `slots`, `serve`); v1 routes as job adapters; `generic` plugin; core backends zip/tar/7z/rar/py7zr | D3, D8 (partly), D12, D15 | pipeline 900, wiring 700, jobs 350, workspace 800, api 700, cli 400, backends ≤ 600 | L0 **blocking**; L1–L4 green for generic; L2 golden identical (or differences explained); re-run reproducibility; F1, F3, F7 structurally impossible |
| **M4** | Ren'Py | `renpy` plugin; safe RPA reader (main) + unrpa subprocess (spare); `game/` source root; optional `analysis.python` (unrpyc) | D11 | 500 | malicious-RPA test green; v1 Ren'Py parity on L2; L5 with unrpa |
| **M5** | Unity | port v1: UnityPy bundles/WebGL; `export.unity` main/spare per D7; drop placeholder slices; honest metrics | D7 | 700 | v1 parity minus known bugs (F1, F11) on fixtures; L5 with UnityPy and AssetStudioModCLI; swapping main/spare in the ini demonstrated |
| **M6** | Godot | PCK v1–v4 identification, carving of embedded PCKs, GDRE (main) / GodotPckTool (spare), `keys.godot` | — | 500 | PCK fixtures incl. embedded/encrypted; L5 with both tools |
| **M7** | Unreal (unpack) | repak (main) / QuickBMS (spare) for pak; retoc for IoStore; `keys.unreal-aes` from the user | — | 500 | pak fixtures built with repak; AES path tested; export explicitly out of scope |
| **M8** | Custom plugin showcase | the custom plugin loader (folder + `plugin.json`, entry-point alternative); showcase plugin per D14 (Overwatch via DataTool **or** an open-source custom-engine game); CATALOG → SELECT path | D5, D12, D14 | loader within the wiring budget; plugin 300 | the plugin loads from outside the tree and passes conformance; catalog/select works from CLI and API; offline defaults verified |
| **M9** | Mixed mode + sanitizer phase 1 | the full combination matrix over M4–M8; mixed policies in API/UI (minimal selector); report-only sanitizer (zero-byte, extension fixes from magic bytes, hash dedupe) | D1, D4 | sanitizer 400, web ≤ 300 | L4 matrix green; product LoC ≤ **8,000**; **★ the prototype is done** (doc 14.4 criteria) |
| **M10** | Runtime capture pilot | capture policy + refusal list (data); journal/overlay + crash recovery; RenderDoc capture → texture harvest → DIFF, on an open game | D13 | capture 400 | refusal tests green; restore leaves identical hashes; DIFF report shows assets found only by capture |
| **M11** | Vendoring | `third_party/manifest.ini` + bootstrap script (sparse rules reapplied); pinned versions; nightly L5 runs on vendored tools | D8, D9 | bootstrap within wiring | a clean clone + bootstrap → `rpyx slots --check` all green on both OSes |
| **M12+** | Next | RPG Maker, Electron/NW wrapper, GameMaker (doc 13.3); Unreal export (CUE4Parse wrapper); sanitizer phases 2–3; analysis backends (Ghidra, ILSpy, Cpp2IL); UI work (plugin option forms, run history, sanitizer panel); Wine adapters | — | within the 10k total | per-item exit criteria |

## 16.3 Decision gates

| Gate | Before | Decisions |
|------|--------|-----------|
| G0 | M2 | D0 terminology, D2 missing-dependency behavior, D6 macOS |
| G1 | M3 | D3 Unity layout, D12 catalog stage, D15 name; D8 for the core backends (7z, py7zr) |
| G2 | M4/M5 | D11 safe RPA reader, D7 Unity export main |
| G3 | M8 | D5 declarative plugins, D14 showcase choice |
| G4 | M10 | D13 overlay vs copy; legal and terms-of-service stance written into the README |
| G5 | M11 | D8/D9 vendoring and project license |

## 16.4 What's deliberately last

- **UI redesign:** the v1 UI is kept; only small additions (selectors, option forms) come before M12.
- **Code analysis backends:** only the hook exists until M12.
- **More engines:** the plugin model has to prove itself on five first.

## 16.5 Risks to the roadmap

| Risk | Signal | Response |
|------|--------|----------|
| M3 is the big one (core rewrite) | its budget overruns, or L2 differences pile up | split M3 into M3a (wiring + slots + CLI on top of the v1 pipeline) and M3b (new stage runner) |
| v1 parity turns out to be inconsistent (bugs are part of the "behavior") | golden diffs that are actually bug fixes | each one listed in the milestone notes as an intentional difference |
| Third-party tool churn | L5 nightly failures | pins + spares; slot self-test |
| LoC caps too tight in a specific area | repeated exception requests | revisit the cap once, in M0 or at a milestone boundary, never mid-milestone |
