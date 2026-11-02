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
    jobs.py    background work with events, cancellation and results
    workspace.py  ownership marker, re-extraction policy, per-workspace lock
  backends/    core unpackers: zip, tar (stdlib), 7-Zip, py7zr, unrar
  plugins/     generic, renpy (safe RPA reader, unrpa), unity (UnityPy, AssetStudioModCLI),
               godot (GDRE Tools, GodotPckTool, embedded PCK carving)
  api/         local web server (token, JSON-only, Host check), JSON handlers, job routes
  web/         the web UI (plain HTML/CSS/ES modules, no build step)
  cli.py       viwo info | slots | detect | extract | replay | unpack | serve
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
- Secrets are never written to disk (run records store `<secret>`).
- Code size caps: see `loc_caps.ini` and `tools/loc_count.py`.
