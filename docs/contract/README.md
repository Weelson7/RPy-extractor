# ViWo architecture contract

The normative description of ViWo: what each part is, what it must do, and where it lives. The
code and these documents describe the same system; where they differ, the difference is listed
as `partial` or `open` in [CONFORMANCE.md](CONFORMANCE.md). Contract version: `CONTRACT_VERSION =
"1.2"` (`viwo/contracts/pipeline.py`, mirrored in `viwo/__init__.py`); optional additions bump the
minor, anything else the major. The product version (`va.b.c`) is separate (`tools/version.py`).

Code and tests cite sections as "doc N.M"; section numbers are stable.

| # | Document | Scope |
|---|----------|-------|
| 0 | [00-glossary.md](00-glossary.md) | one meaning per term; what the result metrics count |
| 1 | [01-os-layer.md](01-os-layer.md) | the OS layer: processes, tool lookup, filesystem rules, shell |
| 2 | [02-engine-plugins.md](02-engine-plugins.md) | engine plugin contract, detection, discovery, conformance |
| 3 | [03-pipeline-and-mixed-mode.md](03-pipeline-and-mixed-mode.md) | extraction stages, request, plugin selection, mixed mode, result |
| 4 | [04-v1-locks.md](04-v1-locks.md) | HTTP API, security model, workspace layout, progress lines, configuration |
| 5 | [05-asset-sanitizer.md](05-asset-sanitizer.md) | the sanitizer (cleanup): rules, plan, apply, undo |
| 6 | [06-analysis-hook.md](06-analysis-hook.md) | static analysis arm: targets, analyzers, worker tools, diff |
| 7 | [07-migration-and-findings.md](07-migration-and-findings.md) | the data-safety rules and the v1 findings they answer |
| 8 | [08-backend-slots.md](08-backend-slots.md) | slots, backends, failover, handoffs, the slot table |
| 9 | [09-startup-ini.md](09-startup-ini.md) | the startup ini, distros, boot sequence |
| 10 | [10-third-party-submodules.md](10-third-party-submodules.md) | pinned third-party tools and their installer |
| 11 | [11-runtime-capture.md](11-runtime-capture.md) | dynamic arm: capture, agents, dump, trace, record, debugger and memory attach tools |
| 12 | [12-core-cli-jobs.md](12-core-cli-jobs.md) | headless core, jobs, envelope, CLI |
| 13 | [13-landscape.md](13-landscape.md) | the tools ViWo wraps and the engines it covers |
| 14 | [14-prototype.md](14-prototype.md) | product scope and the structural choices behind it |
| 15 | [15-loc-caps.md](15-loc-caps.md) | code size caps |
| 16 | [16-roadmap.md](16-roadmap.md) | coverage ladder and the orchestrator rungs: shipped and open |
| 17 | [17-testing-model.md](17-testing-model.md) | test levels, safety catalogue, fixtures, CI |
| 18 | [18-round-trip.md](18-round-trip.md) | patching arm: round trip, patch sets, mod packages |
| 19 | [19-guides.md](19-guides.md) | guides for the child tools: workbooks, runbooks, workflows (embedded GUIs dropped) |

## Scope

ViWo is a local-first game reverse-engineering orchestrator over three arms, all on the same
slot, OS-layer, pinned-tool and provenance plumbing:

- **Static** (the game is not running): survey, extraction (unpack, export, carve, decode),
  curation, and code analysis (doc 3, 5, 6).
- **Dynamic** (the game is running): GPU capture, runtime agents in a patched copy, memory dumps,
  API traces, audio loopback, debugger and memory-editor handoffs (doc 11).
- **Patching** (you change its content): round trip into a patched copy, binary patch sets, mod
  packages (doc 18).

Headless backends do batch work; handoffs ("Continue in Ghidra / x64dbg / Cheat Engine", doc
8.3a) open a GUI tool as a tracked child. Form: a headless core with two clients, the CLI and the
web UI (doc 12). License: MIT core; GPL/AGPL tools run only as separate processes.

## Layers

```
  web/        UI: plain ES modules over HTTP; one client of the core
  cli*.py     command-line client of the core (doc 12)
  api/        HTTP server, routes, JSON <-> contract types, security checks
  core/       pipeline, wiring, jobs, workspace, curation, merger, sanitizer, analysis,
              capture, round trip, patch sets, mods, installer, indexes
  plugins/    engine plugins, one folder per engine
  backends/   core-owned unarchive and pack backends
  os/         LinuxOS, WindowsOS
  contracts/  interfaces and value types only (stdlib, no app imports)
```

Import rule (`tests/test_l0_static.py`, layers `contracts` 0, `os` 1, `plugins`/`backends` 2,
`core` 3, `api`/`cli*` 4): a module imports only its own layer and the layers below it, so
plugins and backends never import `core`. Plugins do not import each other. Core reaches plugins,
backends and the OS layer through the registries filled at boot.

## Principles

1. **The game folder is read-only.** COLLECT copies from it; only staging is moved from; only
   PREPARE clears, and only inside a folder holding the workspace marker. Repack, patch sets,
   mods and runtime agents write a separate, marked patched copy.
2. **The local HTTP API is authenticated:** per-start token, JSON only, Host check, path
   containment (doc 4.1).
3. **OS-specific code lives in the OS layer.** Recorded exceptions: the installer runs `msiexec`
   for the 7-Zip MSI (`viwo/core/thirdparty.py`); the `redengine` plugin loads the game's own
   Oodle DLL through `ctypes` on Windows (`viwo/plugins/redengine/rdar.py`).
4. **Every engine sits behind an interface, bound through a slot** (doc 8). Stages never call a
   tool directly.
5. **Failures are isolated** to the plugin or backend that owns them; the rest of the run goes on.
6. **Destructive bulk actions plan first, apply second, and can be undone** (sanitizer, retain
   groups, merger trash).
7. **Top-level dot-folders of a workspace are reserved** (`.trash`, `.extraction_metadata`,
   `.sanitizer`, `.analysis`, `.runtime`).
8. **Determinism:** the same input and the same ini give the same workspace (`viwo replay`).
9. **Honest metrics:** a number's name says what it counts (doc 0.4).
10. **Never silent:** a fallback, an empty export, a skipped or unreadable file is said in the
    CLI and the GUI (doc 8.2).

## Philosophy rules (D22, owner's decision)

ViWo refuses nothing because of what a game is, which plugin runs, or what the user intends.
Anti-cheat markers, online titles and terms-of-service-sensitive plugins produce warnings and one
confirmation; heavy arms are feature switches (`capture`, `analysis`), not gates. A disclaimer
(README, "Legal and disclaimer") replaces safeguards. Borderline code (DRM defeat, key brute
force, anti-cheat evasion) is never first-party. Engineering properties (copy-not-move, traversal
checks, secrets off disk, pinned downloads) are not boundaries; one that blocks a wanted
capability becomes an option.

## Decisions in force

Referenced by code as `D<n>`.

| # | Decision |
|---|----------|
| D0 | Terms: the OS adapter layer is the **OS layer** (`viwo/os/`); backend / main / spare |
| D1 | Mixed mode: any plugin set at runtime, plus combination tests (doc 3.6) |
| D2 | A missing required dependency disables only what needs it; `strict_preflight` is opt-in |
| D3 | Unity output uses the per-extension layout like every engine |
| D4 | The sanitizer's default recipe is safe: nothing lossy |
| D5 | Custom plugins are Python (drop-ins with `plugin.json`, entry points) |
| D6 | macOS is not an OS layer |
| D7 | `export.unity`: UnityPy main, AssetStudioModCLI spare, failover |
| D8 | Compiled tools: pinned release binaries with checksums, installed into `third_party/` |
| D9 | MIT core; dependencies keep their licenses; GPL/AGPL only as separate processes |
| D11 | Ren'Py RPA: ViWo's safe reader is main; unrpa (subprocess) is spare |
| D12 | No CATALOG stage: SELECT, `viwo survey` and the indexes cover it |
| D13 | Runtime agents work in a patched copy (the journaled overlay is retired; doc 11.5) |
| D14, D16 | Showcases: Doom WAD on Freedoom data in CI; Overwatch as a `tos_sensitive` plugin tested by an independent operator |
| D15 | Name: Vidya Wormhole (ViWo), command `viwo` |
| D17 | Round trip covers Ren'Py, Godot, Unreal, Unity (plus zip and RPG Maker MV) |
| D18 | Unreal AES: a user key wins, else the key finder reads the game's executables; every candidate is verified against the pak index; keys are never stored |
| D19 | Runtime capture (RenderDoc) ships with the extraction arm |
| D21 | Coverage goal: whatever is stored locally can be extracted, through the ladder of doc 16.0b |
| D22 | No policy boundaries in code; warnings, one opt-in and a disclaimer |

## Distros

A distro is an ini file: one OS layer plus one profile (doc 9). `viwo config generate` writes the
twelve files in `distros/` (`linux|windows` x `renpy|unity|unreal|godot|custom|mixed`): `mixed`
enables every plugin, an engine profile enables that engine plus `generic`, `custom` enables every
other built-in.
