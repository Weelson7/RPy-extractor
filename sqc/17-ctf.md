# 17 CTF flags: one asset per game, reached simply or not at all

Each installed game in `Test-games/` carries flags in `sqc/ctf.json`: a specific asset a reverse
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
deletes the copy. Flags for those slugs live in `ctf.json` too; a failing flag names the engine
that still needs a plugin or a QuickBMS script (Cyberpunk `.archive`, Bannerlord `.tpac`, Rome II
`.pack`, AoE II `.drs`).

## SQC-CTF-03 (P1) Adding a flag
Add the slug and a flag `{"name", "glob", "min"}` (or `{"name", "warning"}`) to `ctf.json`;
`tests/test_integration_games.py` keeps the file valid.

| ID | Result | Version | Notes |
|----|--------|---------|-------|
| SQC-CTF-01 | | | |
| SQC-CTF-02 | | | |
| SQC-CTF-03 | | | |
