# SQC: manual check suite for ViWo

Hand-run checks that cover what the automated tests cannot: a real browser, real tools, real
downloads, real games, real eyes. One file per area. Every check has an ID, a priority, exact
steps and exact expected results, so two testers get the same verdict.

| File | Area |
|------|------|
| 01-install-first-run.md | install, first start, startup installer, landing screen, `strict_preflight`, `Start.py` |
| 02-dependencies.md | tools: the pins, `viwo slots`, `viwo install`, SYSTEM, `[tools]` precedence, the APK signer |
| 03-detection-survey.md | engine detection for every plugin, SURVEY, `viwo survey` |
| 04-extraction-per-engine.md | every plugin (incl. AGS, Android, Defold, GameMaker, LÖVE, TyranoScript, Wolf RPG, XNA, Qt, Chromium, .NET, Java, frozen Python, Kaitai), encrypted / needs-key cases, nested archives, the carver |
| 05-modes-options.md | auto / single / mixed, policies, carve modes, filter, on-existing, options, replay, workers, `--plugin ID=on` / `=off`, `--profile` |
| 06-game-integrity-safety.md | game folder unchanged, refused layouts, hostile names, marked folders, zip bomb, lock, interrupted runs, secrets, memory ceiling, known games |
| 07-workspace-sort-trash.md | WORKSPACE, SORT, trash areas, undo, SWITCH and CONVERT INTO WORKSPACE |
| 08-cleanup.md | CLEANUP: sanitizer phases 1-3, plan, apply, undo, stale plans |
| 09-round-trip.md | PATCHED COPY: plan, build, verify, UNTOUCHED, mod / overwrite, every engine's way back, Android signing |
| 10-merger.md | MERGER |
| 11-capture.md | runtime capture (RenderDoc), warnings and confirmation |
| 12-ui-ux.md | every view of the three arms and the global strip at four widths, every error code, failures said, the reload after a restart, keyboard, reduced motion |
| 13-cli.md | every `viwo` command, `tools/version.py` |
| 14-security.md | token, Host, JSON-only, preview containment, pinned downloads |
| 15-release-package.md | portable zip, wheel |
| 16-analysis.md | ANALYSIS: targets, Ghidra headless run, Continue in Ghidra, managed and bytecode analyzers, Detect It Easy, version diff, emulate and solve, feature switch |
| 17-ctf.md | CTF flags per game (`ctf.json`): one plain extraction must reach the named assets |
| 18-patching.md | patch sets (plan, apply, AOB, assembly) and mod packages |
| 19-dynamic.md | Continue in x64dbg / Cheat Engine, memory dump, API trace, hook script, runtime agents, audio loopback |
| 20-guides.md | WORKBOOKS, RUNBOOKS, the structured runbook editor, the workflow recorder (`viwo workbook`, `viwo runbook`) |
| **21+ (areas added after 20; owned by the second half of the suite)** | |
| 21-search.md | content search: `viwo search`, `POST /api/search`, SEARCH |
| 22-isolation.md | isolation sessions: `viwo isolate`, `/api/runtime/isolation`, RUNTIME > ISOLATION PATCHER |

## Real games: `games.md` and the automated integration run

`games.md` lists free titles per engine (verified store pages, sizes, what each exercises), the
`Test-games/<slug>/` folder to install each into, and which ones are installed today. Once
installed:

```powershell
python tools/integration_games.py                 # detect, survey, extract, repack plan, sanitize plan
python tools/integration_games.py --deep          # survey with the carver
python tools/integration_games.py --skip-extract  # detect + survey only
python tools/integration_games.py --only freedoom --games <folder> --out C:\sqc\_ws\integration
```

Every game folder is hashed before and after (a change fails the run); the report lands in
`viwo-data/integration/report.md` and `report.json` (or `--out`). Attach it to a bug report with
`viwo diag`. Installed games outside the repository (the owner's library) go through
`tools/games_pass.ps1` from a worktree at a committed version, with the CTF flags of `ctf.json`
(`17-ctf.md`, `docs/HANDOFF.md`).

## Conventions

- **ID** `SQC-<AREA>-<NN>`; **priority** P0 (release blocker), P1 (must pass before a major),
  P2 (nice to have). **OPERATOR** marks checks that need a real protected game or a real GPU
  game and are run by the independent operator, not by the author. IDs are stable: a check that
  goes away is deleted, its number is not reused; new checks are appended.
- **Result** values: PASS, FAIL, BLOCKED (a precondition is missing), SKIP (not applicable on
  this OS), NOT RUN (with the reason: needs eyes, a browser, a game not installed, the network).
  A check run in part names its parts: `PASS steps 1-2; NOT RUN step 3`, `PASS API; NOT RUN UI`.
  Never PASS for what was not run. Write the ViWo version (`python tools/version.py show`) in the
  Notes column of the first row of each file.
- Paths: `<out>` is the fixture folder (`C:\sqc` below), `<repo>` the checkout, `<ws>` the active
  ViWo workspace shown in the top bar. UI paths read `view > panel > control`, with the labels the
  UI shows, for example `SYSTEM > OPTIONAL TOOLS BY ENGINE > INSTALL`. Views and panels are named,
  never numbered: the tab codes in front of them are computed and change when a view is added. The
  strip shows SYSTEM, WORKBOOKS, RUNBOOKS, SETTINGS; JOBS opens from the job chip.
- Commands are PowerShell from `<repo>` with the venv active unless stated otherwise. Linux: same
  commands with forward slashes and `python3`.
- Nothing in the suite needs a commercial game except the OPERATOR checks. Where a real game helps
  (Unity, Unreal 5 IoStore, RenderDoc), the check says so.
- **API checks.** Many UI checks name their API form (the routes the view calls). Without a
  browser, run it against `viwo serve --port 8191 --no-browser` (stop it afterwards): every
  `/api/` call needs the page's token, read from `<meta name="viwo-token" content="...">` of
  `GET /`, sent as `X-VIWO-Token`; POST bodies are JSON. For example:
  ```python
  import json, re, urllib.request

  BASE = "http://127.0.0.1:8191"
  TOKEN = re.search(
      r'name="viwo-token" content="([^"]+)"', urllib.request.urlopen(BASE + "/").read().decode()
  ).group(1)


  def call(method, route, body=None):
      req = urllib.request.Request(
          BASE + route,
          method=method,
          data=None if body is None else json.dumps(body).encode(),
          headers={"X-VIWO-Token": TOKEN, "Content-Type": "application/json"},
      )
      return json.loads(urllib.request.urlopen(req).read())


  call("POST", "/api/workspace", {"path": r"C:\sqc\_ws\sort"})
  print(call("GET", "/api/status"))
  ```
  Jobs started by a route (cleanup, merge, repack) run in the foreground: the answer is the job's
  result plus `jobId`.

## Setup

1. Python 3.10 or newer (the floor is 3.10; 3.10 to 3.13 are used) and a checkout of branch
   `makeover`:
   ```powershell
   py -3.10 -m venv .venv; .venv\Scripts\Activate.ps1
   pip install -e ".[unity,sevenzip,renpy,lz4,dev]"
   python tools\run_tests.py                      # the whole suite in parallel; green before any manual check
   ```
2. Build the fixtures (synthetic, no game data):
   ```powershell
   python sqc\fixtures\build_fixtures.py --out C:\sqc
   python sqc\fixtures\build_fixtures.py --out C:\sqc --tools-from <a checkout with third_party\>
   python sqc\fixtures\build_fixtures.py --list     # names and what each contains
   ```
   `<out>` = `C:\sqc`. Fake tools and their ini files land in `C:\sqc\ini\` (`godot-fake.ini`,
   `unreal-fake.ini`, `overwatch-fake.ini`, `quickbms-fake.ini`, `android-signer-fake.ini`,
   `capture-on.ini`). The `zip-bomb` fixture is built only on request (`--only zip-bomb`).
   `--tools-from` also writes `C:\sqc\ini\real-tools.ini` (a `[tools]` line per tool installed in
   that checkout's `third_party\`, used where it is; tools run through a runtime get a wrapper in
   `C:\sqc\ini\wrappers\`) and `C:\sqc\real-containers\` (a pak and a PCK written by the real
   repak and GodotPckTool: the synthetic ones are for the fake tools). `encrypted-zip` and the
   `.mp4`/`.avi` of `merger` and `phases` need 7-Zip and ffmpeg; without them a note says how.
   A run with `--ini C:\sqc\ini\<x>.ini` keeps its `viwo-data\` next to that ini.
3. A browser (Chromium, Firefox or Edge), a second one for 12-ui-ux, and the OS "reduce motion"
   setting reachable (Windows: Settings > Accessibility > Visual effects > Animation effects).
4. Internet access for 01 and 02 (the startup installer downloads about 1 GB the first time; on a
   slow line let it run).
5. Start the app for the UI checks:
   ```powershell
   viwo serve            # opens the browser on http://127.0.0.1:8081/
   ```
   `startup.ini` is the one in `<repo>`; `third_party\` and `viwo-data\` appear next to it.

## P0 smoke subset (about 90 minutes)

Run these first, in this order. All must PASS before anything else is worth running.

| Order | Check | What it proves |
|-------|-------|----------------|
| 1 | SQC-INST-01, SQC-INST-02 | fresh install, `viwo` and `viwo slots` run |
| 2 | SQC-INST-04, SQC-INST-05 | landing screen runs the real preflight, tools install into `third_party\` |
| 3 | SQC-DEP-01, SQC-DEP-03 | every pinned tool binds, `viwo install --all` is idempotent |
| 4 | SQC-DET-01, SQC-SUR-01 | detection and survey on fixtures |
| 5 | SQC-EXT-01, SQC-EXT-02, SQC-EXT-04, SQC-EXT-06, SQC-EXT-24 | zip, nested, Ren'Py, Godot (fake and real tools), Android |
| 6 | SQC-SAFE-01, SQC-SAFE-03, SQC-SAFE-09 (steps 1-2), SQC-SAFE-10 | game folder unchanged, hostile names contained, the memory ceiling said, known games stay read-only |
| 7 | SQC-WS-01, SQC-WS-05, SQC-WS-06, SQC-SORT-01, SQC-SORT-04, SQC-SORT-08 | workspace groups, convert a folder, group restore after SORT, sort keep/trash, undo, no preview holds a file |
| 8 | SQC-CLEAN-01, SQC-CLEAN-02 | cleanup plan, apply, undo |
| 9 | SQC-RT-01, SQC-RT-02, SQC-RT-10, SQC-RT-14 | patched copy plan and build, original UNTOUCHED, an APK rebuilt, packer notes said |
| 10 | SQC-MERGE-01 | one merger build |
| 11 | SQC-CAP-01, SQC-CAP-02 | capture switch and confirmation (no refusals) |
| 12 | SQC-UI-01, SQC-UI-05, SQC-UI-13, SQC-UI-15 | every view at 1920, one error box per code, failures said, the strip and the job chip |
| 13 | SQC-CLI-01, SQC-CLI-11, SQC-CLI-14, SQC-CLI-15 | `viwo extract --json`, `tools/version.py`, stage durations and `Time:`, a clean stdout |
| 14 | SQC-SEC-01, SQC-SEC-04 | token and checksum refusal |
| 15 | SQC-REL-01 | portable bundle starts and serves |
| 16 | SQC-GUIDE-01, SQC-GUIDE-02, SQC-GUIDE-03 | workbooks, a runbook run, a workflow recorded and replayed |
| **21+** | | **areas after 20 (second half of the suite): pick with that half's owner** |
| 17 | SQC-SE-01, SQC-SE-06, SQC-SE-07, SQC-SE-10 | content search: text, an exe's section/RVA/VA and signature, where the report lands, the API |
| 18 | SQC-ISO-01, SQC-ISO-03, SQC-ISO-04, SQC-ISO-05 | isolation (needs QEMU installed): tiers, start and hold, live patch with journal and undo, stop with the image untouched |

## Reporting

Fill the result table at the end of each file. For a FAIL, attach the run record from
`<ws>\.extraction_metadata\runs\` (extractions), `<copy>\.viwo-patched\report.json` (patched
copies), the job log from JOBS or `viwo-data\logs\viwo-<date>.log`, or the terminal output, and
the ViWo version. File issues against the SQC ID.
