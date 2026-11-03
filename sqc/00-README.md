# SQC: manual check suite for ViWo

Hand-run checks that cover what the automated tests cannot: a real browser, real tools, real
downloads, real games, real eyes. One file per area. Every check has an ID, a priority, exact
steps and exact expected results, so two testers get the same verdict.

| File | Area |
|------|------|
| 01-install-first-run.md | install, first start, startup installer, landing screen |
| 02-dependencies.md | tools: `viwo slots`, `viwo install`, 05 SYSTEM, pinned tools |
| 03-detection-survey.md | engine detection, 07 SURVEY, `viwo survey` |
| 04-extraction-per-engine.md | every plugin, encrypted / needs-key cases, nested archives |
| 05-modes-options.md | auto / single / mixed, policies, carve modes, filter, on-existing |
| 06-game-integrity-safety.md | game folder unchanged, workspace marker, hostile names |
| 07-workspace-sort-trash.md | 02 WORKSPACE, 03 SORT, trash areas, undo |
| 08-cleanup.md | 08 CLEANUP: sanitizer plan, apply, undo |
| 09-round-trip.md | 09 PATCHED COPY: plan, build, verify, UNTOUCHED |
| 10-merger.md | 06 MERGER |
| 11-capture.md | runtime capture (RenderDoc), warnings and confirmation |
| 12-ui-ux.md | all nine views at four widths, every error code, keyboard, reduced motion |
| 13-cli.md | every `viwo` command, `tools/version.py` |
| 14-security.md | token, Host, JSON-only, preview containment, pinned downloads |
| 15-release-package.md | portable zip, wheel |

## Real games: `games.md` and the automated integration run

`games.md` lists free titles per engine (verified store pages, sizes, what each exercises) and the
`Test-games/<slug>/` folder to install each into. Once installed:

```powershell
python tools/integration_games.py                 # detect, survey, extract, repack plan, sanitize plan
python tools/integration_games.py --deep          # survey with the carver
python tools/integration_games.py --skip-extract  # detect + survey only
```

Every game folder is hashed before and after (a change fails the run); the report lands in
`viwo-data/integration/report.md` and `report.json`. Attach it to a bug report with `viwo diag`.

## Conventions

- **ID** `SQC-<AREA>-<NN>`; **priority** P0 (release blocker), P1 (must pass before a major),
  P2 (nice to have). **OPERATOR** marks checks that need a real protected game or a real GPU
  game and are run by the independent operator, not by the author.
- **Result** values: PASS, FAIL, BLOCKED (a precondition is missing), SKIP (not applicable on
  this OS). Write the ViWo version (`python tools/version.py show`) in the Notes column of the
  first row of each file.
- Paths: `<out>` is the fixture folder (below), `<repo>` the checkout, `<ws>` the active ViWo
  workspace shown in the top bar. UI paths read `view > panel > control`, with the labels the UI
  shows, for example `05 SYSTEM > 05.A OPTIONAL TOOLS BY ENGINE > INSTALL`.
- Commands are PowerShell from `<repo>` with the venv active unless stated otherwise. Linux:
  same commands with forward slashes and `python3`.
- Nothing in the suite needs a commercial game except the OPERATOR checks. Where a real game
  helps (Unity, Unreal 5 IoStore, RenderDoc), the check says so.

## Setup

1. Python 3.11+ and a checkout of branch `makeover`:
   ```powershell
   py -3.13 -m venv .venv; .venv\Scripts\Activate.ps1
   pip install -e ".[unity,sevenzip,renpy,lz4,dev]"
   python -m unittest discover -s tests -t .      # must be green before any manual check
   ```
2. Build the fixtures (synthetic, no game data):
   ```powershell
   python sqc\fixtures\build_fixtures.py --out C:\sqc
   python sqc\fixtures\build_fixtures.py --list     # names and what each contains
   ```
   `<out>` = `C:\sqc`. Fake tools and their ini files land in `C:\sqc\ini\`. The `zip-bomb`
   fixture is built only on request (`--only zip-bomb`).
3. A browser (Chromium, Firefox or Edge), a second one for 12-ui-ux, and the OS "reduce motion"
   setting reachable (Windows: Settings > Accessibility > Visual effects > Animation effects).
4. Internet access for 01 and 02 (the installer downloads about 800 MB the first time; on a slow
   line let it run).
5. Start the app for the UI checks:
   ```powershell
   viwo serve            # opens the browser on http://127.0.0.1:8081/
   ```
   `startup.ini` is the one in `<repo>`; `third_party\` and `viwo-data\` appear next to it.

## P0 smoke subset (about 45 minutes)

Run these first, in this order. All must PASS before anything else is worth running.

| Order | Check | What it proves |
|-------|-------|----------------|
| 1 | SQC-INST-01, SQC-INST-02 | fresh install, `viwo` and `viwo slots` run |
| 2 | SQC-INST-04, SQC-INST-05 | landing screen runs the real preflight, tools install into `third_party\` |
| 3 | SQC-DEP-01, SQC-DEP-03 | every pinned tool binds, `viwo install --all` is idempotent |
| 4 | SQC-DET-01, SQC-SUR-01 | detection and survey on fixtures |
| 5 | SQC-EXT-01, SQC-EXT-02, SQC-EXT-04, SQC-EXT-06 | zip, nested, Ren'Py, Godot (fake tools) |
| 6 | SQC-SAFE-01, SQC-SAFE-03 | game folder unchanged, hostile names contained |
| 7 | SQC-WS-01, SQC-SORT-01, SQC-SORT-04 | workspace groups, sort keep/trash, undo |
| 8 | SQC-CLEAN-01, SQC-CLEAN-02 | cleanup plan, apply, undo |
| 9 | SQC-RT-01, SQC-RT-02 | patched copy plan and build, original UNTOUCHED |
| 10 | SQC-MERGE-01 | one merger build |
| 11 | SQC-CAP-01, SQC-CAP-02 | capture switch and confirmation (no refusals) |
| 12 | SQC-UI-01, SQC-UI-05 | nine views at 1920, one error box per code |
| 13 | SQC-CLI-01, SQC-CLI-09 | `viwo extract --json`, `tools/version.py verify` |
| 14 | SQC-SEC-01, SQC-SEC-04 | token and checksum refusal |
| 15 | SQC-REL-01 | portable bundle starts and serves |

## Reporting

Fill the result table at the end of each file. For a FAIL, attach the run record from
`<ws>\.extraction_metadata\runs\` (extractions), the job log from 04 JOBS, or the terminal
output, and the ViWo version. File issues against the SQC ID.
