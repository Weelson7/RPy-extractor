# 16. Roadmap (draft 3)

Milestones are gated by decisions (README), LoC budgets (doc 15) and tests
(doc 17). There are **no dates**: each milestone is sized by its LoC budget
and its exit criteria. Every milestone leaves the app working, and the v1 web
UI stays usable throughout.

Draft 3 change, after the independent review: an **urgent hotfix comes
first** (v1 moves files out of game folders and can delete a user-chosen
folder), and the prototype is split into **A (viable core)** and
**B (breadth)**.

## 16.1 Overview

```
M0 Decisions ─▶ M1 Hotfix+Safety net ─▶ M2 Contracts+Kernels ─▶ M3 Lean core+CLI ─┬▶ M4 Ren'Py ─┐
                                                                                   ├▶ M5 Unity  ─┼▶ ★A
                                                                                   └▶ M6 Godot  ─┘
★A ─▶ M7 Unreal unpack ─┬▶ M9 Round trip ─▶ M10 Mixed + Sanitizer P1 ─▶ ★B ─▶ M11 Capture pilot ─▶ M12 Vendoring ─▶ M13+
      M8 Custom plugins ─┘
```

## 16.2 Milestones

| M | Name | Content | Needs | New LoC cap | Exit criteria |
|---|------|---------|-------|-------------|---------------|
| **M0** | Decisions & semantics | sign-off on docs 0–17; close or explicitly park D0–D15; rewrite the scratchpad interface draft to match draft 3 | — | 0 | glossary + caps agreed; decision table filled in |
| **M1** | **Hotfix + safety net** (hotfix part **done**: branch `hotfix/v1-data-safety`) | **in v1:** H1 copy-not-move, H2 workspace marker, H3 token/JSON-only/Host/containment, F17 safe extraction, F1 exports to staging, F3 dot-folder filter. **Then** the L2 characterization tests against the *intended* behavior, with an intended-differences list; LoC counter + L0 in report-only mode; CI on Linux + Windows | D10 | hotfix ≤ 250 in v1; counter ≤ 120 | H1/H2/H3/F17 regression tests green; golden files committed |
| **M2** | Contracts + kernels (lean) | `contracts/`; conformance kit; ProcessRunner (tree-kill, timeout), ToolLocator, FileSystemPolicy for Linux and Windows; v1 OS code behind them; installer/shell kept as thin v1 adapters | D0, D2, D6 | contracts 900; kernels 900 | L1 green on both OSes; L2 unchanged; F4, F13 gone |
| **M3** | Lean core + CLI | flat startup ini; slot binder (failover only); stage runner (identify/carve, unpack, collect copy/move, verify, report); workspace (marker, lock, three trash layouts); jobs + run records + envelope; CLI `info/detect/extract/unpack/serve`; v1 routes as adapters (doc 4.1 mapping); `generic` plugin; core backends zip/tar/7z/rar/py7zr. If it overruns, split into M3a (wiring + slots + CLI on the v1 pipeline) and M3b (new stage runner) | D3, D12, D15 | pipeline 900, wiring 500, jobs 350, workspace 800, api 700, cli 400, backends 600 | L0 **blocking**; L1–L4 for generic; L2 matches the intended behavior; replay identical; `.7z` failover shown |
| **M4** | Ren'Py | safe RPA reader (main) + unrpa subprocess (spare); source root copied | D11 | 500 | malicious-RPA test; v1 Ren'Py parity on L2; L5 with unrpa |
| **M5** | Unity | v1 port; UnityPy ↔ AssetStudioModCLI per D7; placeholder slices and the fake completeness gate removed | D7 | 700 | parity on fixtures minus F1/F11; swap from the ini shown; L5 |
| **M6** | Godot | PCK v1–v4; carving of embedded PCKs; GDRE → GodotPckTool; key as a plugin option | — | 500 | PCK fixtures (embedded, encrypted); L5 with both tools. **★ Prototype A** (doc 14.4) |
| **M7** | Unreal unpack | repak → QuickBMS; retoc; AES key option | — | 500 | pak fixtures built with repak; export explicitly out of scope |
| **M8** | Custom plugins | out-of-tree loader (`user_plugins/`, entry points); open-source custom-engine showcase (CI); optional local-only Overwatch plugin (D14); CATALOG → SELECT if D12 says yes | D5, D12, D14 | loader ≤ 200; plugins ≤ 300 each | conformance from outside the tree; offline defaults verified |
| **M9** | Round trip (repack) | provenance-based edit set; per-plugin `repack_plan`; patched game copy (copy-on-write clones where supported); `pack.*` slots for Ren'Py (override + RPA writer), Godot (PCK rebuild), Unreal (`_P.pak` via repak), Unity (UnityPy save, same-format); verification by re-extraction | — | roundtrip 450; +150 per plugin | round-trip tests green for each engine; original game folder hashes unchanged; repack refused for policy-listed games |
| **M10** | Mixed + sanitizer P1 | exhaustive selection + pairwise pipeline tests; minimal mixed selector in the UI; report-only sanitizer | D1, D4 | sanitizer 400; web ≤ 300 | product ≤ 9,000. **★ Prototype B** |
| **M11** | Capture pilot | policy + refusal list (data); journal overlay + crash recovery; RenderDoc → harvest → DIFF on an open game | D13, legal stance | capture 400 | refusal and restore tests green |
| **M12** | Vendoring | tool lock → sparse submodules for the source-usable tools; bootstrap reapplies sparse rules; nightly L5 on vendored tools | D8, D9 | bootstrap ≤ 150 | clean clone + bootstrap → `rpyx slots --check` green on both OSes |
| **M13+** | Next | distro layering + the 12 ini files + hooks; installer abstraction; RPG Maker, Electron/NW, GameMaker; Unreal export (CUE4Parse wrapper); sanitizer P2–3; analysis backends; UI (plugin option forms, run history, sanitizer panel); Wine | — | within the 10k total | per item |

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
| Third-party tool churn | L5 nightly failures | pins + spares + `rpyx slots --check` |
| Caps too tight somewhere | repeated exception requests | revisit only at milestone boundaries |
| Hotfix delayed by the overhaul | M1 slips | M1 doesn't depend on any decision except D10; ship it on its own |
