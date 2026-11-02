# RPy Extractor: architecture contract (draft 3, for review)

**Status: proposal, draft 3** (draft 2 added the research in doc 13; draft 3 applies an independent review: new v1 data-loss and security findings, contradictions fixed, prototype split into A/B). Nothing here is implemented or decided. These documents
lay out how I understand the target architecture after reading the v1 code
(`extract.py`, `api/*`, `extraction_core/*`, `extraction_types/*`,
`sorting.py`, `media_merger/*`, `startup.py`, `web/app.js`). The goal is to
agree on the concepts first and only then lock the interfaces. Items marked ❓
are places where I'm unsure or where the choice is yours.

## Reading order

| # | Document | Scope |
|---|----------|-------|
| 0 | [00-glossary.md](00-glossary.md) | **Start here.** One meaning per term; v1 words that carry several meanings; metrics that don't count what their names say |
| 1 | [01-kernel.md](01-kernel.md) | Linux / Windows kernels: where OS-specific code would live |
| 2 | [02-engine-plugins.md](02-engine-plugins.md) | Ren'Py, Unity, Unreal, Godot, custom plugins; detection; dependencies |
| 3 | [03-pipeline-and-mixed-mode.md](03-pipeline-and-mixed-mode.md) | stages, plugin routing, mixed mode, the combination test matrix |
| 4 | [04-v1-locks.md](04-v1-locks.md) | what the v1 UI depends on (API, payloads, workspace layout, logs) and should be kept |
| 5 | [05-asset-sanitizer.md](05-asset-sanitizer.md) | review of the Tdarr-style sanitizer idea, and a sketch of its interfaces |
| 6 | [06-analysis-hook.md](06-analysis-hook.md) | decompiler hook (Ghidra first) |
| 7 | [07-migration-and-findings.md](07-migration-and-findings.md) | v1 issues found while reading, where each v1 file would go, order of work |
| 8 | [08-backend-slots.md](08-backend-slots.md) | every pipeline engine behind an interface: slots with a **main** and a **spare** backend |
| 9 | [09-startup-ini.md](09-startup-ini.md) | startup wiring declared in an `.ini` file; boot sequence |
| 10 | [10-third-party-submodules.md](10-third-party-submodules.md) | third-party tools as sparse submodules; open problems |
| 11 | [11-runtime-capture.md](11-runtime-capture.md) | runtime capture (assets that only exist decoded at runtime), with a safety policy |
| 12 | [12-core-cli-jobs.md](12-core-cli-jobs.md) | headless core, CLI, jobs; the web UI as one client |
| 13 | [13-landscape.md](13-landscape.md) | existing tools and frameworks, where this fits, what to borrow |
| 14 | [14-prototype.md](14-prototype.md) | the prototype: scope, slices, success criteria |
| 15 | [15-loc-caps.md](15-loc-caps.md) | strict caps on non-blank, non-comment LoC: counting rules, v1 baseline, budgets |
| 16 | [16-roadmap.md](16-roadmap.md) | milestones M0–M12, decision gates, exit criteria |
| 17 | [17-testing-model.md](17-testing-model.md) | test levels L0–L7, safety catalogue, fixtures, CI, definition of done |

## Scope decisions taken (your answers)

| Topic | Answer |
|-------|--------|
| Framing | A **game reverse-engineering framework oriented towards asset extraction** |
| Scope | **Static extraction + runtime capture**; code RE through hooks |
| Form | **Headless core + CLI + web UI** (the web UI is one client) |
| Build vs wrap | **Orchestrate existing tools, write glue**; native code only where nothing exists or as a light spare |
| Prototype engines | **Ren'Py + Unity (port v1), Godot, Unreal, plus a custom-plugin showcase (e.g. Overwatch)** |

## Goals (as I understood them)

1. Split the product into **distros**: one *kernel* (host OS) plus one *profile* (which game engines are supported).
2. Each game engine is an **engine plugin**. Adding an engine should not require changes to core, API or UI code.
3. **Mixed mode**: any combination of plugins can run on one game folder, and the test suite covers every combination.
4. Every processing engine of the pipeline sits behind an **interface**, filled by a **main** backend and, where it makes sense, a **spare** (unarchiving first).
5. **Startup wiring comes from an `.ini` file**, so a distro is just an ini file.
6. Third-party tools are **vendored as sparse submodules**.
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
  kernels/    linux | windows: process, tool location, installer, shell, filesystem rules
  contracts/  interfaces + value types only (stdlib, no app imports)
  third_party/  vendored tools (sparse submodules)
```

Proposed dependency direction: every layer may use the layers listed below it,
never the ones above. `contracts` imports nothing from the app. Plugins never
import each other. Core reaches plugins, backends and kernels through
registries that the boot step fills from the ini. In v1 this direction is
broken in several places: `extraction_core` lazily imports `startup`, core
knows about `.rpa`, and OS checks appear in five modules (doc 7, F12/F13).

## Distro model (proposed)

A distro is an ini file: one kernel plus one profile, with optional slot and
tool overrides (doc 9). Two kernels times six profiles gives 12 distros. The
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
3. **OS-specific code only in kernels.** That includes subprocess calls, tool lookup, installers, dialogs and filename rules.
4. **Every engine behind an interface, bound through a slot** (doc 8). Stages never call tools directly.
5. **Failures are isolated.** A failing plugin or backend is recorded against its owner; the other plugins keep running.
6. **Destructive bulk actions plan first, apply second, and can be undone** (sanitizer, retain groups).
7. **Top-level dot-folders in the workspace are reserved** (`.trash`, `.extraction_metadata`, `.sanitizer`, `.analysis`).
8. **Determinism.** The same input and the same ini give the same output.
9. **Honest metrics.** A number's name says what it counts (doc 0.4). Gaining confidence in output quality starts with this.
10. **Versioning.** `MAJOR.MINOR`. Optional additions bump the minor; anything else bumps the major.

## Decisions needed from you

| # | Question | My suggestion |
|---|----------|---------------|
| D0 | Terminology (doc 0.5): "kernel" or "host"? "backend / main / spare"? two trash layouts or one? | — |
| D1 | Mixed mode: does it mean (a) choosing any plugin set at runtime, (b) a test matrix over every set, or both? | both |
| D2 | When an enabled plugin's required dependency is missing: refuse to start (v1, for unrpa) or disable that plugin? | disable the plugin; `strict_preflight` as an opt-in |
| D3 | Unity output in the per-extension layout (`png/`) instead of `images/`? | yes |
| D4 | Sanitizer scope at first | health and identity rules only; nothing lossy by default |
| D5 | Custom plugins: Python only, or also declarative JSON/ini? | Python first |
| D6 | macOS kernel | later |
| D7 | `export.unity`: v1 runs every available exporter and adds up their output. Keep that (`supplement`) or switch to main + spare (`failover`)? | ❓ depends on whether duplicate files are acceptable |
| D8 | Vendored compiled tools: build from source, or pin the version and fetch the release binary? (doc 10.4) | pin + fetch for heavy native tools |
| D9 | Project license, needed before vendoring GPL tools (doc 10.4) | — |
| D10 | **Hotfix v1 now** for H1 (moves files out of the game folder), H2 (deletes a user-chosen folder), H3 (cross-site POSTs) and F17 (zip-slip), before the overhaul? All are confirmed in the code (doc 7) | **yes, urgently** (roadmap M1) |
| D11 | Ren'Py RPA: should our own safe reader (restricted unpickler) be main, with unrpa as a subprocess spare? | yes; RPA indexes are pickles (doc 13.3) |
| D12 | Should CATALOG → SELECT be a separate stage for huge games (CASC, Unreal)? | yes, optional |
| D13 | Runtime agents: journaled overlay on the game folder, or a copy of the game? | overlay + crash recovery |
| D14 | Custom plugin showcase | **decided:** an open-source custom-engine game in CI; Overwatch allowed as a `tos_sensitive` plugin whose real-data tests are run by an **independent operator** (doc 17.4b) |
| D15 | Product and CLI name ("RPy Extractor" undersells a multi-engine framework) | — |

## Not in this draft

- The Python interface code. A draft exists in the session scratchpad and has been held back as you asked. It predates draft 2: it still has archive handlers instead of slots and no ini boot, so it will be rewritten once these documents are agreed.
- Facts still UNVERIFIED after research: anti-cheat marker names, Godot `override.cfg` autoload injection, Ninja Ripper licensing, AESDumpster and UnrealLocres licenses, some Windows-only tools on Linux, and Blizzard's current EULA text (see docs 11 and 13).
