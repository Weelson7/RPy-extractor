# ViWo architecture

The map of the code. The normative design is [docs/contract/](docs/contract/README.md); what is
implemented, partial or open is in [CONFORMANCE.md](docs/contract/CONFORMANCE.md).

ViWo is a headless core with two clients (the CLI and the web UI) over three arms: **static**
(survey, extraction, curation, code analysis), **dynamic** (capture, runtime agents, dumps,
traces, audio, debugger and memory handoffs) and **patching** (round trip, patch sets, mods).
Every tool sits behind a slot with a main and an optional spare backend; capability comes from
pinned third-party tools; ViWo writes the glue.

## Layer rule

```
contracts  <-  os  <-  plugins, backends  <-  core  <-  api, cli*
```

A module imports only its own layer and the layers to its left (`tests/test_l0_static.py`).
`contracts` imports nothing from the app; plugins never import `core` or each other; core reaches
plugins, backends and the OS layer through the registries filled at boot. GPL/AGPL tools run
only as separate processes.

## Module map

```
viwo/
  contracts/   interfaces and value types (stdlib only); workspace.py (layout, member names
               and their record), paths.py (walking without following links)
    plugin.py      EnginePlugin, PluginManifest, ExtractionContext, GameProbe, CliCommand
    slots.py       SlotDefinition, Backend, Unarchiver, Exporter, Carver, Decoder, Prober, Packer
    analysis.py    AnalysisTarget, Analyzer, Handoff, LaunchSpec
    runtime.py     RuntimeAgent
    pipeline.py    ExtractionRequest/Result, Stage, CONTRACT_VERSION
    types.py, errors.py, os.py, workspace.py   value types, envelope, OS interfaces, layout rules
  os/          LinuxOS, WindowsOS (_shared.py): processes with tree kill and tracked children,
               tool lookup, filename rules, pickers, homes, scan exclusions, process list, dumps
  backends/    core unarchivers (zip, tar, 7-Zip, py7zr, unrar) and the zip packer
  plugins/     one folder per engine: generic, renpy, unity, godot, unreal, doom, rpgmaker,
               kirikiri, electron, source, bethesda, genie, warscape, redengine, taleworlds,
               quickbms, overwatch; game plugins under their engine in <engine>/games/
               (redengine/games/cyberpunk2077, taleworlds/games/bannerlord; doc 2.10)
  core/
    wiring/      ini parsing, plugin registry (scan, drop-ins, entry points), slot binder,
                 boot (Runtime), distros, conformance checks, settings writer
    pipeline/    probe, detect, select, identify, unpack, export (+ wrapper re-detection),
                 carving, collect, failover, guard (game-folder checks), runner, ticker
    carve/       signature carver (format sizers) and compressed-stream scan
    decode.py    DECODE: audio to WAV, DDS to PNG, Bink to MP4; media.probe backends
    curation/    extension groups, sorting with undo, three trash areas
    merger/      media merger: candidates, timeline, ffmpeg builds
    sanitizer.py, sanitizer_rules.py   cleanup: plan, apply, undo
    survey.py, surveys.py              coverage report per game or library, numbered reports
    analysis/    static analysis: targets, Ghidra (headless + GUI), managed analyzers, Detect It
                 Easy, emulate/symbolic workers, version diff; nothing here runs the game
    handoff.py   "continue in <tool>": a prepared GUI tool as a tracked child (both arms)
    guides.py    the guide files of doc 19: shipped in viwo/data/<kind>/, the user's own in
                 viwo-data/<kind>/, problems named; save and delete of the user's copy
    workbooks.py step-by-step how-tos for a child tool's own interface (doc 19.1)
    runbooks.py  named step sequences (doc 19.2): rules and the `{name}` values; they run
                 through the API's job handlers (api/handlers_runbooks.py, cli_guides.py)
    workflows.py recorded runbooks (doc 19.3): portable parameters, secret inputs, the
                 expected answers a replay compares with; the recorder is api/recording.py
    capture/     dynamic arm: policy (warnings, confirmation), RenderDoc capture and harvest,
                 runtime agents, dump, trace, profile, audio loopback, attach (x64dbg on the
                 game's own process, Cheat Engine)
    roundtrip.py, roundtrip_edits.py   edit set, plan, patched copy, pack, verify
    patchsets.py, patch_tools.py       T1 patch sets (offset, RVA, AOB, Keystone, capstone)
    mods.py                            T2 mod packages
    jobs.py, workspace.py, records.py, provenance.py, context.py, steps.py, media.py
    thirdparty.py, workers.py, preflight.py   pinned installer, worker tools, startup check
    downloads.py                       verified download, safe unzip/untar, folder swap
    scan_exclusions.py, indexes.py, diag.py   antivirus exclusions, per-game indexes, diagnostics
  api/         server.py (token, JSON only, Host check, preview), peers.py (loopback, token
               comparison), ranges.py (byte ranges), routes.py (envelope routes),
               handlers*.py (legacy-shaped routes per area), app.py (jobs, locks, payloads),
               recording.py (the workflow recorder), plugin_assets.py (plugin UI modules)
  web/         index.html, css/base.css + css/skin.css + css/themes/, js/ (api, registry, game selector,
               progress, ui/ component library, views/ one module per view)
  data/        tools.json (pins), locks/ (hash locks), capture_policy.json, ghidra/ViwoExport.java,
               workers/ (emulate.py, symbolic.py)
  cli.py       entry point; cli_args.py (arguments), cli_arms.py (arms), cli_check.py (slots
               --check, unpack --slot, analyze, diff), cli_extra.py (survey, sanitize, repack,
               install, config, indexes, diag), cli_dynamic.py, cli_patch.py, cli_format.py
tools/         version.py, loc_count.py + caps_ini.py, coverage_check.py, notices.py,
               pin_python.py, integration_games.py, games_pass.ps1, deep_pass.py (+ deep_checks,
               deep_arms: every capability on one real game), presentation/ (frames, the
               technical PDF, the demo video)
packaging/     build_portable.py, viwo_entry.py (the frozen viwo.exe)
indexes/       per-game indexes (future vidya_wormhole_indexes repository)
distros/       twelve generated ini files
examples/      plugins/hello: a drop-in with a CLI command and a UI module
sqc/           manual check suite, real-game list, CTF flags, fixture builder
tests/         unittest suites L0-L6 and the browser smoke (tests/ui/smoke.mjs)
```

## Invariants (each has a test)

- The game folder is read-only: COLLECT copies from it, staging is the only place files are
  moved from, every run compares the game folder before and after. Repack, patch sets, mods and
  runtime agents write a separate, marked patched copy.
- Only folders carrying `.viwo-workspace` are ever cleared.
- Retryable failures fall through to the spare and the fallback is always said; `needs_key`
  never falls through.
- Ren'Py pickles are read with an allow-list; `.rpyc` is decompiled in a separate process.
- Secrets and found keys are never written to disk or logged (run records store `<secret>`).
- Nothing is refused because of what a game is: anti-cheat, online titles and sensitive plugins
  produce warnings; the dynamic arm and analysis are feature switches.
- GUI tools and launched games are tracked children, killed when ViWo exits.
- Code size caps: `loc_caps.ini`, `tools/loc_count.py`.
