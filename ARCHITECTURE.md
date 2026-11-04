# ViWo architecture (overview)

The full contract is in [docs/contract/](docs/contract/README.md); this page is the map.

ViWo is a **full game reverse-engineering orchestrator** over three arms, all built on the same
slot/backend, OS-layer, pinned-tool and provenance plumbing:

- **Static** — extraction (the mature arm: unpack, export, decode, carve) plus code and data
  analysis (Ghidra and friends: disasm/decompile, type/symbol recovery, bytecode VMs, protector ID,
  emulation, version diffing). Reads copies, never runs the game. Docs 3 and 6.
- **Dynamic/runtime** — capture, debugging, instrumentation/tracing, memory, hooking, own-traffic
  networking, profiling. Runs or attaches to the game through `core/capture/journal.py`, behind the
  `runtime` feature flag with warnings and one opt-in. Doc 11.
- **Authoring** — asset round trip, binary patch sets with AOB signatures, and mod-runtime
  packaging. Writes only a separate, marked patched copy. Doc 18.

Each arm offers headless backends for batch/automation and **"continue in &lt;tool&gt;" handoffs**
(doc 8.3a) that prepare a target and open a GUI tool (Ghidra, x64dbg, RenderDoc, ReClass.NET) as a
tracked child subprocess. ViWo writes the glue; capability is pinned third-party tools (philosophy
point 5: no first-party borderline code). No capability is gated for what a game is (D22).

```
viwo/
  contracts/   interfaces + value types only (stdlib, no app imports)
  os/          OS layer: LinuxOS, WindowsOS (processes with tree-kill, tool lookup,
               filename rules, folder/file pickers)
  core/
    wiring/    startup.ini parsing, plugin registry, slot binder (main / spare / promoted)
    pipeline/  probe -> detect -> select -> identify/carve -> unpack -> export -> collect
               -> verify -> report, plus the game-folder guard
    curation/  extension groups, sorting (keep / trash / rename / undo), three trash areas
    merger/    media merger: candidates, timeline expansion, ffmpeg filtergraph and builds
    carve/     signature carver (format sizers) and zlib/gzip stream inflation
    capture/   runtime capture pilot: warnings policy, journaled overlay, RenderDoc backend
    analysis/  static analysis arm (A1): targets from the plugins, Ghidra headless into
               <workspace>/.analysis/, "Continue in Ghidra" handoff as a tracked child
    decode.py  DECODE stage: game audio -> WAV (vgmstream), DDS -> PNG, Bink -> MP4
    roundtrip.py  edit set -> plan -> patched copy -> pack.* slots -> verify -> report
    sanitizer.py  phase 1: zero-byte, junk, wrong extension, duplicates, health; journaled
    survey.py  read-only coverage report per game / library
    jobs.py    background work with events, cancellation and results
    workspace.py  ownership marker, re-extraction policy, per-workspace lock (+ lock file)
    thirdparty.py / preflight.py  pinned tool installer (tools.json) and the startup check
    indexes.py  per-game indexes (indexes/): validate, match, install tools and scripts, update
    provenance.py / diag.py  provenance rewrite on moves; diagnostics bundle
  backends/    core unpackers: zip, tar (stdlib), 7-Zip, py7zr, unrar; zip packer
  plugins/     generic, renpy, unity, godot, unreal (repak/retoc, verified AES keys), doom (WAD),
               rpgmaker, kirikiri (XP3), electron (asar), source (VPK), bethesda (BSA/BA2),
               genie (DRS), warscape (Total War packs), redengine (Cyberpunk RDAR, Kraken
               through the game's own Oodle DLL), taleworlds (Bannerlord TPAC), quickbms
  api/         local web server (token, JSON-only, Host check), JSON handlers (tools, capture,
               settings, system), job routes
  web/         the web UI (plain HTML/CSS/ES modules, no build step): landing, a global strip
               (SYSTEM, JOBS, SETTINGS, game, workspace) and three arms (STATIC, DYNAMIC,
               PATCHING), each opening on a home view with its end-to-end path
  data/        tools.json (pinned tools), capture_policy.json (warnings, never refusals),
               ghidra/ViwoExport.java (the headless export script)
  cli.py       commands grouped by arm (cli_arms.py): static (survey, detect, extract, replay,
               unpack, sanitize, analyze, diff), dynamic (capture, dump, trace, agent, record),
               patching (repack, patch, mod), system (serve, info, slots, install, config,
               indexes, diag); `viwo <arm>` lists one, `viwo <arm> <command>` = `viwo <command>`
```

Dependency direction: every layer may use the layers listed above it in this tree (contracts
first), never the reverse. Plugins never import each other or the core.

Key invariants (tested):

- The game folder is read-only: COLLECT copies from it, staging is the only place files are
  moved from, and every run compares the game folder before and after.
- Only folders carrying the `.viwo-workspace` marker are ever cleared.
- Each slot has a main and a spare backend; retryable failures fall through to the spare,
  "needs key" does not.
- GPL/AGPL tools run as separate processes; Ren'Py pickles are read with an allow-list.
- Secrets are never written to disk (run records store `<secret>`); found AES keys are never logged.
- Round trip writes only into a separate, marked patched copy and verifies every packed member.
- No policy boundaries: nothing is refused because of what a game is. Anti-cheat, online titles and
  sensitive plugins produce warnings; the user confirms once and is responsible (README: Philosophy).
- Two job classes: **static** jobs (extraction, `analysis.*`) read copies and never run or touch the
  game; **dynamic** jobs (`capture/runtime/debug/trace/memory/hook/net/profile`) touch the running
  game and so go through the capture journal, the `runtime` feature flag and the opt-in. A GUI
  handoff that runs code in the game is a dynamic action; one that opens a static file is not.
- GUI tools are launched as tracked child subprocesses inside ViWo's process tree, so tree-kill and
  timeouts reach them (doc 8.3a, doc 1).
- Code size caps: see `loc_caps.ini` and `tools/loc_count.py`.
