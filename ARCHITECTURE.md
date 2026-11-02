# ViWo architecture (overview)

The full contract is in [docs/contract/](docs/contract/README.md); this page is the map.

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
    capture/   runtime capture pilot: refusal policy, journaled overlay, RenderDoc backend
    decode.py  DECODE stage: game audio -> WAV (vgmstream), DDS -> PNG, Bink -> MP4
    roundtrip.py  edit set -> plan -> patched copy -> pack.* slots -> verify -> report
    sanitizer.py  phase 1: zero-byte, junk, wrong extension, duplicates, health; journaled
    survey.py  read-only coverage report per game / library
    jobs.py    background work with events, cancellation and results
    workspace.py  ownership marker, re-extraction policy, per-workspace lock
  backends/    core unpackers: zip, tar (stdlib), 7-Zip, py7zr, unrar; zip packer
  plugins/     generic, renpy, unity, godot, unreal (repak/retoc, verified AES keys), doom (WAD),
               rpgmaker, kirikiri (XP3), electron (asar), source (VPK), bethesda (BSA/BA2),
               quickbms (script bridge)
  api/         local web server (token, JSON-only, Host check), JSON handlers, job routes
  web/         the web UI (plain HTML/CSS/ES modules, no build step)
  data/        policy data (capture refusal list)
  cli.py       viwo info | slots | detect | extract | replay | unpack | survey | sanitize |
               repack | capture | serve
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
- Runtime capture is refused when anti-cheat or an online title is detected (no override).
- Code size caps: see `loc_caps.ini` and `tools/loc_count.py`.
