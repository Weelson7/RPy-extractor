# Vidya Wormhole (ViWo): architecture contract (draft 3, decisions closed)

**Status: in force (1.1).** Draft 3 (2026-11-02) was the proposal; the decisions below were closed the same day and the implementation was audited against every document on 2026-11-03 (`CONFORMANCE.md`). Where a document still reads as a proposal, its History line says what the shipped design is. These documents
lay out how I understand the target architecture after reading the v1 code
(`extract.py`, `api/*`, `extraction_core/*`, `extraction_types/*`,
`sorting.py`, `media_merger/*`, `startup.py`, `web/app.js`). The goal is to
agree on the concepts first and only then lock the interfaces. Items marked ❓
are places where I'm unsure or where the choice is yours.

## Reading order

| # | Document | Scope |
|---|----------|-------|
| 0 | [00-glossary.md](00-glossary.md) | **Start here.** One meaning per term; v1 words that carry several meanings; metrics that don't count what their names say |
| 1 | [01-os-layer.md](01-os-layer.md) | Linux / Windows OS layers: where OS-specific code would live |
| 2 | [02-engine-plugins.md](02-engine-plugins.md) | Ren'Py, Unity, Unreal, Godot, custom plugins; detection; dependencies |
| 3 | [03-pipeline-and-mixed-mode.md](03-pipeline-and-mixed-mode.md) | stages, plugin routing, mixed mode, the combination test matrix |
| 4 | [04-v1-locks.md](04-v1-locks.md) | what the v1 UI depends on (API, payloads, workspace layout, logs) and should be kept |
| 5 | [05-asset-sanitizer.md](05-asset-sanitizer.md) | review of the Tdarr-style sanitizer idea, and a sketch of its interfaces |
| 6 | [06-analysis-hook.md](06-analysis-hook.md) | **static-analysis arm:** binary loading, disasm/decompile, type/symbol recovery, bytecode VMs, protector ID, emulation, version diffing (Ghidra and friends) |
| 7 | [07-migration-and-findings.md](07-migration-and-findings.md) | v1 issues found while reading, where each v1 file would go, order of work |
| 8 | [08-backend-slots.md](08-backend-slots.md) | every pipeline engine behind an interface: slots with a **main** and a **spare** backend |
| 9 | [09-startup-ini.md](09-startup-ini.md) | startup wiring declared in an `.ini` file; boot sequence |
| 10 | [10-third-party-submodules.md](10-third-party-submodules.md) | third-party tools as sparse submodules; open problems |
| 11 | [11-runtime-capture.md](11-runtime-capture.md) | **dynamic/runtime arm:** capture, debugging, instrumentation/tracing, memory, hooking, own-traffic networking, profiling, through the journal and one opt-in |
| 12 | [12-core-cli-jobs.md](12-core-cli-jobs.md) | headless core, CLI, jobs; the web UI as one client |
| 13 | [13-landscape.md](13-landscape.md) | existing tools and frameworks, where this fits, what to borrow |
| 14 | [14-prototype.md](14-prototype.md) | the prototype: scope, slices, success criteria |
| 15 | [15-loc-caps.md](15-loc-caps.md) | strict caps on non-blank, non-comment LoC: counting rules, v1 baseline, budgets |
| 16 | [16-roadmap.md](16-roadmap.md) | milestones M0–M12, decision gates, exit criteria |
| 17 | [17-testing-model.md](17-testing-model.md) | test levels L0–L7, safety catalogue, fixtures, CI, definition of done |
| 18 | [18-round-trip.md](18-round-trip.md) | **authoring arm:** asset round trip, binary patch sets with AOB signatures and patch export, mod-runtime packaging; patched game copy |

## Scope decisions taken (your answers)

| Topic | Answer |
|-------|--------|
| Framing | A **full game reverse-engineering orchestrator** over three arms: **static** (extraction + code/data analysis, doc 6), **dynamic/runtime** (doc 11), **authoring** (round trip, patching, mods, doc 18). Asset extraction is the mature arm; the others follow the respec (doc 16.2b) |
| Scope | **Static extraction + static analysis + dynamic/runtime + authoring.** Headless backends for batch, "continue in &lt;tool&gt;" handoffs for interactive work (doc 8.3a). No capability is gated for what a game is (D22); heavy arms are feature flags off by default |
| Form | **Headless core + CLI + web UI** (the web UI is one client) |
| Build vs wrap | **Orchestrate existing tools, write glue**; native code only where nothing exists or as a light spare |
| Prototype engines | **Ren'Py + Unity (port v1), Godot, Unreal, plus a custom-plugin showcase (e.g. Overwatch)** |
| Round trip | **Full round trip; repack in Prototype B**; output = **patched game copy**; strategy **per plugin**; **same format first** (doc 18) |
| License | **MIT core**; dependencies keep their own licenses (GPL/AGPL tools only as subprocesses) |
| Re-extraction | **ask every time** (new workspace / replace / cancel) |
| Terms-of-service-sensitive testing | run by an **independent operator** (doc 17.4b) |
| v1 hotfix | **done** on branch `hotfix/v1-data-safety` (H1, H2, H3, F17 + 11 regression tests), not merged yet |
| Naming | product **Vidya Wormhole (ViWo)**, CLI `viwo`; OS adapter layer called **OS** |

## Goals (as I understood them)

1. Split the product into **distros**: one *OS layer* (host OS) plus one *profile* (which game engines are supported).
2. Each game engine is an **engine plugin**. Adding an engine should not require changes to core, API or UI code.
3. **Mixed mode**: any combination of plugins can run on one game folder, and the test suite covers every combination.
4. Every processing engine of the pipeline sits behind an **interface**, filled by a **main** backend and, where it makes sense, a **spare** (unarchiving first).
5. **Startup wiring comes from an `.ini` file**, so a distro is just an ini file.
6. Third-party tools are **pinned and installed automatically** (`viwo/data/tools.json`: version, HTTPS URL, size, sha256; into `third_party/`), per D8. **History:** draft 3 said sparse submodules; the lock file plus installer replaced them (doc 10).
7. The v1 UI keeps working; new API surface is added alongside the existing routes.

## Layers (proposed)

```
  web/        UI (v1 kept), HTTP only; one client of the core
  cli/        command-line client of the core (doc 12)
  api/        routes, JSON <-> contract types, origin checks; jobs over HTTP
  core/       pipeline runner, workspace, curation (sorting/trash), merger,
              sanitizer runner, analysis jobs, registries, boot (ini), logging
  plugins/    engine plugins: generic, renpy, unity, unreal, godot, <custom>
  backends/   implementations behind slots: unarchivers, exporters, media, analyzers
  os/    linux | windows: process, tool location, installer, shell, filesystem rules
  contracts/  interfaces + value types only (stdlib, no app imports)
  third_party/  pinned tools, installed by viwo/core/thirdparty.py (gitignored)
```

Proposed dependency direction: every layer may use the layers listed below it,
never the ones above. `contracts` imports nothing from the app. Plugins never
import each other. Core reaches plugins, backends and OS layers through
registries that the boot step fills from the ini. In v1 this direction is
broken in several places: `extraction_core` lazily imports `startup`, core
knows about `.rpa`, and OS checks appear in five modules (doc 7, F12/F13).

## Distro model (proposed)

A distro is an ini file: one OS layer plus one profile, with optional slot and
tool overrides (doc 9). Two OS layers times six profiles gives 12 distros. The
`generic` plugin is in all of them.

| Profile | Engine plugins | Mixed mode | Custom plugins |
|---------|----------------|-----------|----------------|
| renpy  | generic, renpy  | no | no |
| unity  | generic, unity  | no | no |
| unreal | generic, unreal | no | no |
| godot  | generic, godot  | no | no |
| custom | generic + plugins from `custom_dirs` | no | yes |
| mixed  | all of the above | yes | yes |

## Proposed principles

These are the ideas the other documents build on. Each is up for debate.

1. **One writer per folder; the game folder is read-only.** Plugins and backends write to staging; only COLLECT writes the workspace, by **copying** from the game folder and moving only from staging. Only PREPARE clears, and only inside a folder holding the workspace marker. This rules out v1's H1 (files moved out of the game), H2 (user folder deleted) and F1 (Unity exports wiped).
2. **The local HTTP API is authenticated** (a per-start token, JSON only, Host check, path containment; doc 4.1).
3. **OS-specific code only in OS layers.** That includes subprocess calls, tool lookup, dialogs and filename rules. Two recorded exceptions in core, each a single call with no OS primitive to delegate to: the installer runs `msiexec` for the 7-Zip MSI through `subprocess.run` with a verbatim command line (`viwo/core/thirdparty.py`), and the workspace lock checks a pid with `OpenProcess` on Windows (`viwo/core/workspace.py`).
4. **Every engine behind an interface, bound through a slot** (doc 8). Stages never call tools directly.
5. **Failures are isolated.** A failing plugin or backend is recorded against its owner; the other plugins keep running.
6. **Destructive bulk actions plan first, apply second, and can be undone** (sanitizer, retain groups).
7. **Top-level dot-folders in the workspace are reserved** (`.trash`, `.extraction_metadata`, `.sanitizer` for sanitizer plans and journals; `.analysis` stays reserved for the analysis rung).
8. **Determinism.** The same input and the same ini give the same output.
9. **Honest metrics.** A number's name says what it counts (doc 0.4). Gaining confidence in output quality starts with this.
10. **Versioning.** The contract keeps `CONTRACT_VERSION` (`"1.1"` since the 1.2 batch's additive types; `MAJOR.MINOR`: optional additions bump the minor, anything else the major). The product uses `va.b.c` (`tools/version.py`, CLAUDE.md): `a` per finished roadmap, `b` per feature, `c` per commit. **History:** draft 3 had one scheme for both.

## Decisions (all closed)

You accepted every recommendation on 2026-11-02, so this table is now the record.

| # | Topic | Decision |
|---|-------|----------|
| D0 | Terminology | the OS adapter layer is called **OS** (`viwo/os/`, `LinuxOS`, `WindowsOS`); **backend / main / spare**; three explicit trash layouts (groups, items, merger) |
| D1 | Mixed mode | both: any plugin set at runtime, plus combination tests |
| D2 | Missing required dependency | **disable that plugin** and show why; `strict_preflight` is an opt-in |
| D3 | Unity output layout | per-extension layout (`png/`, `wav/`), like everything else |
| D4 | Sanitizer first scope | health and identity rules, report-only; nothing lossy by default |
| D5 | Custom plugins | Python first; declarative form later |
| D6 | macOS | later |
| D7 | `export.unity` | `failover`: **UnityPy main** (v1 parity), **AssetStudioModCLI spare**; `supplement` later if needed |
| D8 | Vendored compiled tools | pin the version + fetch release binaries for heavy native tools |
| D9 | License | MIT core; dependencies keep their own licenses |
| D10 | v1 hotfix | done (`hotfix/v1-data-safety`, merged into `makeover`) |
| D11 | Ren'Py RPA | our safe reader is main; unrpa (subprocess) is spare |
| D12 | CATALOG → SELECT | **closed, not built.** SELECT (`viwo/core/pipeline/select.py`) plus `viwo survey` and the per-game indexes cover what CATALOG was for (knowing what a folder holds before choosing plugins); a separate stage would add a pass over the folder for no new decision |
| D13 | Runtime agents | journaled overlay + crash recovery |
| D14 | Custom plugin showcase | open-source custom-engine game in CI; Overwatch as a `tos_sensitive` plugin tested by an independent operator |
| D15 | Name | **Vidya Wormhole (ViWo)**; CLI `viwo` |
| D16 | Custom-engine showcase (Prototype B) | **Doom WAD with Freedoom data** (BSD) as the CI-tested custom plugin, plus an **Overwatch (CASC/DataTool) plugin** marked `tos_sensitive` and tested only by the independent operator |
| D17 | Round trip scope in B | **all four engines**: Ren'Py (override + safe RPA writer), Godot (PCK rebuild), Unreal (`_P.pak` via repak), Unity (UnityPy same-format replacement) |
| D18 | Unreal AES keys | an offline-playable game must carry its pak key locally, so the key is always reachable: **a user-supplied key wins; otherwise the key finder runs automatically**; every candidate is **verified against the pak's encrypted index** before use; keys are never stored |
| D19 | Runtime capture pilot | **inside Prototype B** (refusal policy, journaled overlay, RenderDoc harvest, diff against the static extraction) |
| D20 | Real-game check | after Prototype B (you / the independent operator). **Pending the owner:** `sqc/games.md` lists the games, `tools/integration_games.py` runs them; the `docs/prototype-b/STATUS.md` "not verified" table closes row by row with the results |
| D21 | Coverage goal | **whatever is stored locally can be extracted**, through a ladder of fallbacks (doc 16.0b): engine plugin, container unpackers, signature carver, compressed-stream scan, decoders, script-driven unpackers (QuickBMS), runtime capture. `viwo survey` measures coverage per game. The "limits that stay" sentence of draft 3 is superseded by D22: ViWo authors no code for defeating copy protection or brute-forcing keys (keys come from the user or from the game's own local files and are verified, D18), and refuses nothing |

## Not in this draft

- Implementation status of Prototype A: see [docs/prototype-a/STATUS.md](../prototype-a/STATUS.md).
- Facts still UNVERIFIED after research: anti-cheat marker names, Godot `override.cfg` autoload injection, Ninja Ripper licensing, AESDumpster and UnrealLocres licenses, some Windows-only tools on Linux, and Blizzard's current EULA text (see docs 11 and 13).

## D22 (1.0): no policy boundaries, a disclaimer instead

Owner's decision, confirmed: ViWo is a community tool that refuses nothing because of what a game
is, which plugin runs, or what the user intends. Refusal lists became warnings plus one opt-in.
Borderline code is never first-party. The README "Philosophy" section is the reference; doc 11.1
and doc 14 keep their original proposals with a revision note.
