# 17 CTF flags: one asset per game, reached simply or not at all

Each test game carries flags in `sqc/ctf.json`, each a specific asset a reverse engineer would want
(the music out of the RPA, the meshes of a Unity level, a texture out of a UE5 IoStore
container): about five basic objectives for a free title; for a library game three shared
baselines and then the objectives specific to that game (its title in `ctf.json` gives the
count). A flag passes when one plain extraction (`viwo extract <game> --workspace W`, no options,
no scripts written by hand) leaves the asset in the workspace, or when ViWo says plainly why it
cannot (the bare Godot templates). Anything that needs a manual detour is a FAIL and a roadmap
item, never a judgement call.

Run: `python tools/integration_games.py` (every folder of `Test-games/`), `--only <slug>[,<slug>]`,
`--games <folder>` for games kept elsewhere, `--out <folder>` for the report
(`report.md`, `report.json`). The report has a `Flags` column (`passed/total`) and lists every
failed flag under the table; a game with a failed flag is a FAIL even when every pipeline step
(detect, survey, extract, repack_plan, sanitize_plan) succeeded.

What a flag can say (`tools/integration_games.py`, `check_flags`): at least `min` files match
`glob`; or the run's warnings contain `warning` (`""`: the run reported no warning at all); with
`analyze`, the glob is checked after that analysis. Nothing else is read, so:
- Every flag must be able to fail: `min` is 1 or more, and the glob is not a file every run
  writes. There is no "at most": "nothing else is invented" and "no archive is claimed" (the bare
  Godot templates) cannot be flags; the `no PCK data` warning flag carries them.
- The baselines check that the run record and the provenance map are written; the runner does
  not read the plugin id out of the record. Read it in the report's plugins column.
- The two `"warning": ""` flags (Cyberpunk: every Kraken segment inflated; Bannerlord: every LZ4
  segment inflated) are fragile: any warning of the run fails them. When one fails, the report
  lists the warnings: record which one it was; do not loosen the flag.
- No flag may depend on luck (an antivirus happening to hold a file); such a case belongs in a
  fixture test.
- Two flags of Age of Empires share the glob `slp/*.slp` (1000 and 1500): the count cannot tell
  `graphics.drs` from `terrain.drs`; the second only raises the first.

## SQC-CTF-01 (P0) Shipped free titles

Steps: install the titles of `games.md` into `Test-games/<slug>/`; `python
tools/integration_games.py --games Test-games --out C:\sqc\_ws\integration`.

Expected: every flag of the eleven free titles that carry flags passes (`DDLC-1.1.1-pc`,
`freedoom`, `ultrakill-prelude`, `baldi-cr`, `BURNING_SNOW_1_0_4`, `voids-cave`, `the-basement`,
`rpgmv-first`, `ubu`, `godotone`, `godot-mad`): `Total: <n>/<n> games passed; exit code 0`, each
game `Unchanged yes`. Titles without flags (`godot-first`, `ancient-challenger`, a free `tf2`)
run with no `Flags` verdict until flags are written for them (SQC-CTF-03).

## SQC-CTF-02 (P1) The owner's installed games

From a worktree at a committed version with its own venv (`docs/HANDOFF.md`, never a tree being
edited), `powershell -File tools/games_pass.ps1` copies each game under `C:\Users\<you>\Games`
into `Test-games/pass-<slug>`, runs it, keeps the report under `viwo-data/games-pass/<slug>/` and
deletes the copy. A game too large to copy whole carries a `subset` (the files copied); its flags
describe that subset. Their flags (owner's rule, 2026-11-03) are three shared baselines (a run
record, the provenance map, the executable collected) and then only objectives specific to that
game.

Expected: every game of the pass reads `passed/total` with passed = total, the game folder
unchanged, against the flag set `ctf.json` holds at that version. A pass recorded against an
older flag set does not close the check for that game: rerun it.

Recorded passes (the flag set of their date):

| Game (slug) | Flags | Version or date | Against today's `ctf.json` |
|---|---|---|---|
| Age of Empires II HD (`pass-aoe`) | 13/13 | 1.20.34 | same 13 flags |
| Approximately Up (`pass-approximately-up-build-25884550`) | 9/10 | 1.20.36 | the flag missed was the antivirus one, removed since: 9 flags now |
| Schedule I (`pass-schedule-i`) | 12/12 | 1.20.37 | 12 flags; "StreamingAssets collected" rewritten (`mov/*.mov`), not run |
| Cyberpunk 2077 (`pass-cyberpunk-2077`) | 11/11 | 2026-11-03 | predates the current 16-flag set: rerun |
| Mount & Blade II: Bannerlord (`pass-mount-blade-2-bannerlord`) | 11/11 | 2026-11-03 | same 11 flags |
| Team Fortress 2 (`pass-team-fortress-2`) | 9/9 | 2026-11-04 | 9 flags; the localization flag rewritten (`res/*.res`), not run |
| Total War: Rome II (`pass-total-war-rome-ii`) | 12/12 | 2026-11-04 | same 12 flags |
| The Ren'Py title, Returning to Mia (`pass-zipped-game-data`) | 10/10 | 2026-11-04 | 10 flags; three flags rewritten (`jpg`, `ttf`, `mp3`), not run |

## SQC-CTF-03 (P1) Adding a flag

Add the slug and a flag `{"name", "glob", "min"}` (or `{"name", "warning"}`) to `ctf.json`; an
analysis flag adds `"analyze": "<target key from viwo analyze --list>"` (and `"slot"` for a
second analyzer such as `analysis.protector`): the runner runs that analysis once, with the
`analysis` feature on, before the glob is checked under `.analysis/`. Before adding it, check
the rules above: the flag can fail (`min` of 1 or more; not `**/*`, not the run record or the
provenance map under another name), it does not depend on luck, and its name says what the glob
checks. Never rename a top-level slug: the pass reports are keyed by it. Add the title to
`games.md`.

Steps: after any edit of `ctf.json`, `python -m unittest tests.test_integration_games`.

Expected: `OK` (the file parses and every flag has a name and either a `glob` or a `warning`;
the test does not check `min >= 1` or the other rules above: read them by hand).

## Results

| ID | Result | Version | Notes |
|----|--------|---------|-------|
| SQC-CTF-01 | PASS freedoom; NOT RUN the other ten | 1.36.0+search+apk (unreleased) | agent, 2026-11-23: `--games <main checkout>\Test-games --only freedoom`: the report row reads freedoom, doom 90%, plugins doom, copied 4100, archives 2/2, warnings 0, unchanged yes, flags 5/5, steps detect/survey/extract/repack_plan/sanitize_plan all ok, PASS; `Total: 1/1 games passed; exit code 0`. The other ten free titles are not installed (games.md). Earlier: 51/51 over the eleven at 1.20.64 |
| SQC-CTF-02 | NOT RUN | | the owner's games are not here; the recorded passes above stand for their dates |
| SQC-CTF-03 | PASS (validity) | 1.36.0+search+apk (unreleased) | agent, 2026-11-23: `tests.test_integration_games`: `Ran 3 tests ... OK`; `ctf.json` unchanged in this rewrite |
