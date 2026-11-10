# 17 CTF flags: one asset per game, reached simply or not at all

Each installed game in `Test-games/` carries flags in `sqc/ctf.json`, each a specific asset a
reverse engineer would want (the music out of the RPA, the meshes of a Unity level, a texture out
of a UE5 IoStore container): about five basic objectives for a free title; for a library game
three shared baselines and then the objectives specific to that game (its title in `ctf.json`
gives the count). A flag passes when one plain extraction (`viwo extract <game> --workspace W`,
no options, no scripts written by hand) leaves the asset in the workspace, or when ViWo says
plainly why it cannot (the bare Godot templates). Anything that needs a manual detour is a FAIL
and a roadmap item, never a judgement call.

Run: `python tools/integration_games.py` (all games) or `--only <slug>`. The report gains a
`Flags` column (`passed/total`) and lists every failed flag under the table; a game with a failed
flag is a FAIL even when every pipeline step succeeded.

What a flag can say (`tools/integration_games.py`, `check_flags`): at least `min` files match
`glob`; or the run's warnings contain `warning` (`""`: the run reported no warning at all); with
`analyze`, the glob is checked after that analysis. Nothing else is read, so:
- Every flag must be able to fail: `min` is 1 or more, and the glob is not a file every run
  writes. There is no "at most": "nothing else is invented" and "no archive is claimed" (the bare
  Godot templates) cannot be flags and were removed; the `no PCK data` warning flag carries them.
- The baselines check that the run record and the provenance map are written; the runner does
  not read the plugin id out of the record. Read it in the report's plugins column.
- The two `"warning": ""` flags (Cyberpunk: every Kraken segment inflated; Bannerlord: every LZ4
  segment inflated) are fragile: any warning of the run fails them, one about something else
  too (a child tool past its memory cap, a file another program holds). The runner has no
  narrower form ("no warning that says skipped"). When one fails, the report lists the warnings:
  record which one it was; do not loosen the flag.
- No flag may depend on luck. "antivirus-held files are a warning, not a crash" (Approximately
  Up) passed only when an antivirus happened to hold a file during the run: it is removed and
  belongs in a fixture test (a file made unreadable on purpose), not in a games pass.
- Two flags of Age of Empires share the glob `slp/*.slp` (1000 and 1500): the count cannot tell
  `graphics.drs` from `terrain.drs`; the second only raises the first.

## SQC-CTF-01 (P0) Shipped free titles
Every flag of the eleven free titles that carry flags passes (DDLC, Freedoom, ULTRAKILL Prelude,
Baldi's CR, Burning Snow, Void's Cave, The Basement, RPG Maker MV, Ubu, GodotOne, MAD game; all
in `sqc/games.md`). `games.md` also lists titles without flags (My First Godot Game, Ancient
Challenger, a free Team Fortress 2 install): they run through the integration run with no
`Flags` verdict until flags are written for them (SQC-CTF-03).

## SQC-CTF-02 (P1) The owner's installed games
From a worktree at a committed version with its own venv (`docs/HANDOFF.md`, never a tree being
edited), `powershell -File tools/games_pass.ps1` copies each game under `C:\Users\<you>\Games`
into `Test-games/pass-<slug>`, runs it, keeps the report under `viwo-data/games-pass/<slug>/` and
deletes the copy. A game too large to copy whole carries a `subset` (the files copied: a few
archives plus the executable and, for Cyberpunk, the game's own Oodle DLL); its flags describe
that subset. Every engine in the owner's library has a plugin (Cyberpunk `.archive`,
Bannerlord `.tpac`, Rome II `.pack`, AoE II `.drs`). Their flags (owner's rule, 2026-11-03) are
three shared baselines (a run record, the provenance map, the executable collected) and then
only objectives specific to that game: the named DRS members of AoE, the Kraken-inflated CR2W
classes of Cyberpunk, the TPAC texture and mesh segments of Bannerlord, the db tables and `.loc`
text of Rome II, the Cpp2IL stub assemblies of the two IL2CPP titles, and Detect It Easy's
identification of every executable.

Expected: every game of the pass reads `passed/total` with passed = total, the game folder
unchanged, against the flag set `ctf.json` holds at that version. A pass recorded against an
older flag set does not close the check for that game: rerun it.

Recorded passes (the flag set of their date):

| Game (slug) | Flags | Version or date | Against today's `ctf.json` |
|---|---|---|---|
| Age of Empires II HD (`pass-aoe`) | 13/13 | 1.20.34 | same 13 flags |
| Approximately Up (`pass-approximately-up-build-25884550`) | 9/10 | 1.20.36 | the flag missed was the antivirus one, removed since: 9 flags now |
| Schedule I (`pass-schedule-i`) | 12/12 | 1.20.37 | 12 flags; "StreamingAssets collected" rewritten (`mov/*.mov`), not run |
| Cyberpunk 2077 (`pass-cyberpunk-2077`) | 11/11 | 2026-11-03 | predates the current 16-flag set (baselines, path-list names, Detect It Easy added; three flags reworded): rerun |
| Mount & Blade II: Bannerlord (`pass-mount-blade-2-bannerlord`) | 11/11 | 2026-11-03 | same 11 flags |
| Team Fortress 2 (`pass-team-fortress-2`) | 9/9 | 2026-11-04 | 9 flags; the `min: 0` localization flag rewritten (`res/*.res`), not run |
| Total War: Rome II (`pass-total-war-rome-ii`) | 12/12 | 2026-11-04 | same 12 flags |
| The Ren'Py title, Returning to Mia (`pass-zipped-game-data`) | 10/10 | 2026-11-04 | 10 flags; three `min: 0` flags rewritten (`jpg`, `ttf`, `mp3`), not run |

## SQC-CTF-03 (P1) Adding a flag
Add the slug and a flag `{"name", "glob", "min"}` (or `{"name", "warning"}`) to `ctf.json`;
an analysis flag adds `"analyze": "<target key from viwo analyze --list>"` (and `"slot"` for a
second analyzer such as `analysis.protector`): the runner runs that analysis once, with the
`analysis` feature on, before the glob is checked under `.analysis/`.
`tests/test_integration_games.py` keeps the file valid. Before adding it, check the rules above:
the flag can fail (`min` of 1 or more; not `**/*`, not the run record or the provenance map
under another name), it does not depend on luck, and its name says what the glob checks. Never
rename a top-level slug: the pass reports are keyed by it. Add the title to `games.md`.

| ID | Result | Version | Notes |
|----|--------|---------|-------|
| SQC-CTF-01 | PASS | 1.3.7 | agent, 2026-11-03: 55/55 flags over the eleven titles (viwo-data/integration/report.md), with the flag sets of that date. Today's sets hold 51: four flags that could not fail removed (GodotOne, MAD game), two of Burning Snow rewritten: NOT RUN since |
| SQC-CTF-02 | PASS on the recorded sets; NOT RUN on today's | 1.20.37 and earlier | 2026-11-03 to 2026-11-10, table above: AoE II HD 13/13 (1.20.34), Approximately Up 9/10 (1.20.36), Schedule I 12/12 (1.20.37), Cyberpunk 2077 11/11, Bannerlord 11/11, Team Fortress 2 9/9, Rome II 12/12, the Ren'Py title 10/10. Cyberpunk's pass predates the current 16-flag set; five rewritten flags (Schedule I, Team Fortress 2, the Ren'Py title) are not run |
| SQC-CTF-03 | | | |
