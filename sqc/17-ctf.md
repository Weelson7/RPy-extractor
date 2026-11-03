# 17 CTF flags: one asset per game, reached simply or not at all

Each installed game in `Test-games/` carries flags in `sqc/ctf.json`: five basic objectives plus
up to one more per GB of game data (the owner's sizing rule), each a specific asset a reverse
engineer would want (the music out of the RPA, the meshes of a Unity level, a texture out of a UE5
IoStore container). A flag passes when one plain extraction (`viwo extract <game> --workspace W`,
no options, no scripts written by hand) leaves the asset in the workspace, or when ViWo says
plainly why it cannot (the bare Godot templates). Anything that needs a manual detour is a FAIL
and a roadmap item, never a judgement call.

Run: `python tools/integration_games.py` (all games) or `--only <slug>`. The report gains a
`Flags` column (`passed/total`) and lists every failed flag under the table; a game with a failed
flag is a FAIL even when every pipeline step succeeded.

## SQC-CTF-01 (P0) Shipped free titles
Every flag of the eleven `sqc/games.md` titles passes (DDLC, Freedoom, ULTRAKILL Prelude, Baldi's
CR, Burning Snow, Void's Cave, The Basement, RPG Maker MV, Ubu, GodotOne, MAD game).

## SQC-CTF-02 (P1) The owner's installed games
`powershell -File tools/games_pass.ps1` copies each game under `C:\Users\<you>\Games` into
`Test-games/pass-<slug>`, runs it, keeps the report under `viwo-data/games-pass/<slug>/` and
deletes the copy. A game too large to copy whole carries a `subset` (the files copied: a few
archives plus the executable and, for Cyberpunk, the game's own Oodle DLL); its flags describe
that subset. Every engine in the owner's library has a plugin since 1.3.3 (Cyberpunk `.archive`,
Bannerlord `.tpac`, Rome II `.pack`, AoE II `.drs`). Their flags (owner's rule, 2026-11-03) are
three shared baselines (the run record names the plugin, a provenance line per file, the
executable collected) and then only objectives specific to that game: the named DRS members of
AoE, the Kraken-inflated CR2W classes of Cyberpunk, the TPAC texture and mesh segments of
Bannerlord, the db tables and `.loc` text of Rome II, the Cpp2IL stub assemblies of the two
IL2CPP titles, and Detect It Easy's identification of every executable.

## SQC-CTF-03 (P1) Adding a flag
Add the slug and a flag `{"name", "glob", "min"}` (or `{"name", "warning"}`) to `ctf.json`;
an analysis flag adds `"analyze": "<target key from viwo analyze --list>"` (and `"slot"` for a
second analyzer such as `analysis.protector`): the runner runs that analysis once, with the
`analysis` feature on, before the glob is checked under `.analysis/`.
`tests/test_integration_games.py` keeps the file valid.

| ID | Result | Version | Notes |
|----|--------|---------|-------|
| SQC-CTF-01 | PASS | 1.3.7 | agent, 2026-11-03: 55/55 flags over the eleven titles (viwo-data/integration/report.md) |
| SQC-CTF-02 | | | |
| SQC-CTF-03 | | | |
