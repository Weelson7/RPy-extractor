# 12 UI and UX

Area code `UI`. Window sizes: 1920x1080, 1440x900, 1280x800, 1024x768 (device toolbar or a resized
window). The three arms and the strip, with their computed tab codes (a code changes when a view is
added: name views, never numbers, in reports):

| Where | Views (code) |
|-------|--------------|
| STATIC | STATIC HOME (S0), SURVEY (S1), EXTRACT (S2), WORKSPACE (S3), SEARCH (S4), SORT (S5), CLEANUP (S6), MERGER (S7), ANALYSIS (S8) |
| DYNAMIC | DYNAMIC HOME (D0), CAPTURE (D1), RUNTIME (D2) |
| PATCHING | PATCHING HOME (P0), PATCHED COPY (P1), ASSETS (P2), PATCHES + MODS (P3) |
| strip | SYSTEM (00), WORKBOOKS (01), RUNBOOKS (02), SETTINGS (03); JOBS opens from the job chip (`#jobs`), its panels tagged `JOB` |

Error codes (`viwo\web\js\ui\feedback.js` ERRORS): offline, http, invalid_request, not_found, busy,
unavailable, needs_key, needs_decision, failed, cancelled, refused, internal. The browser smoke
`python -m unittest tests.test_ui_smoke` (headless Edge or Chrome + Node) runs the scripted part of
these checks; it must be green first.

## SQC-UI-01 (P0) Every view at 1920 and 1440

Steps: at 1920, then 1440: each arm with the arm switch above the rail, every view of it from the
rail; SYSTEM, WORKBOOKS, RUNBOOKS, SETTINGS from the strip; JOBS from the job chip; scroll each to
the bottom.

Expected: no horizontal scrollbar (page or main); each view head shows its code and title
(`// S4` + `SEARCH`, `// 03` + `SETTINGS`) and subtitle; panels lettered `<code>.A`, `.B`...; the action bars (EXTRACT,
SEARCH, ANALYSIS, PATCHED COPY, ASSETS, SETTINGS) visible; no text overflows its panel; the top bar
shows the strip, the `GAME` selector, the `WORKSPACE` path and the chips `FORMATS n/m READY` and `JOB
IDLE`; opening a strip view keeps the arm's rail; the rail marks the current view
(`aria-current="page"`); the document title is `<VIEW TITLE> // ViWo` (`STATIC HOME // ViWo`,
`PATCHES + MODS // ViWo`); no console error.

## SQC-UI-02 (P0) Every view at 1280 and 1024

Steps: as 01 at 1280 and 1024.

Expected: under 1200 px the rail shows only the current arm's tab codes (names as tooltips and for
screen readers), and the arm switch above it stays readable; two-column grids become one column;
tables scroll inside their panel, never the page or main sideways; the action bar stays reachable;
nothing overlaps the activity dock.

## SQC-UI-03 (P0) Activity console dock

Steps: click `// ACTIVITY CONSOLE`; run an extraction; scroll up while lines arrive; `CLEAR`;
reload; collapse it while a job runs.

Expected: the dock expands (`aria-expanded="true"`), shows `n LINES`, auto-scrolls while lines
arrive and stops when you scroll up; `CLEAR` empties it (`0 LINES`, the server log cleared); the open
state is remembered after a reload; collapsed, its header shows the latest line while a job runs.

## SQC-UI-04 (P0) Status chips follow jobs, tools and the server

Steps: start a long run (RUNTIME > TRACE CALLS for 40 s on a process of your own, or a survey of a
big library); watch the chips; install a tool from SYSTEM; stop the server.

Expected: `RUNNING <KIND>` (live, `API TRACE`, `SURVEY`..., `+n` when several run) linking to `#jobs`
while it runs, `JOB IDLE` after; `FORMATS` grows after the install without a reload; with the server
stopped the chips become `SERVER OFFLINE` (red) with the restart tooltip; no uncaught error in the
console.

## SQC-UI-05 (P0) One error box per code, with the right NEXT text and link

Where to trigger each:
1. `offline`: stop the server, then `SEARCH` in SEARCH.
2. `http`: `http://127.0.0.1:<port>/api/nope` in a tab (JSON 404); a non-JSON answer in the app is not reachable normally (SKIP).
3. `invalid_request`: SEARCH, kind `NUMBER`, value `abc`.
4. `not_found`: SEARCH in `C:\nope`; RUNTIME > ISOLATION PATCHER > `STATUS` with no session.
5. `busy`: SQC-SAFE-06.
6. `unavailable`: RUNTIME > `RECORD SOUND` without soundcard (or extract the godot fixture without GDRE / GodotPckTool).
7. `needs_key`: SQC-EXT-07 step 1 in the UI.
8. `needs_decision`: EXTRACT into a workspace that holds an extraction.
9. `failed`: PATCHES + MODS > `APPLY` of `C:\sqc\bad.patch.json` (18-patching) into a new folder.
10. `cancelled`: `CANCEL JOB` on a running job in JOBS.
11. `refused`: PATCHES + MODS > `APPLY` into a folder that holds files of yours.
12. `internal`: make a route raise (a code edit; restore it afterwards).

Expected, per code, the box title and NEXT text exactly (the view prefixes its own title: `SEARCH
FAILED // NOT FOUND`):
- offline: `VIWO IS NOT REACHABLE` / `Start ViWo again (viwo serve, or Start.py), then reload this page.` (message `Server unreachable`, hint `Is ViWo running? Start it with \`viwo serve\` (or Start.py), then reload.`)
- http: `UNEXPECTED SERVER REPLY` / `Reload the page. If it keeps happening, check the terminal ViWo runs in.` (`/api/nope` answers `{"success": false, "error": "Unknown route /api/nope"} 404`)
- invalid_request: `CHECK YOUR INPUT` / `A path or option is not valid. Correct it and try again.`
- not_found: `NOT FOUND` / `The file or folder is gone, or the path has a typo. Check it, or refresh this view.`
- busy: `WORKSPACE BUSY` / `Another job is using this workspace. Wait for it to finish, then try again.` + `Open JOBS →`
- unavailable: `TOOL NOT INSTALLED` / `A tool this needs is missing. Install it with one click in SYSTEM, then try again.` + `Open SYSTEM →`; a hint naming `viwo install X` reads `INSTALL X in SYSTEM →`
- needs_key: `ENCRYPTION KEY NEEDED` / `These files are encrypted. Enter the key under ENGINE OPTIONS, then run again.` + `Open EXTRACT →`
- needs_decision: EXTRACT shows the modal `WORKSPACE ALREADY HOLDS AN EXTRACTION` (`CANCEL`, `REPLACE`, `NEW FOLDER`) instead of a box; elsewhere `YOUR CHOICE IS NEEDED` / `Answer the question ViWo asked, then run again.`
- failed: `IT DID NOT WORK` / `The message above says why; the same line is in the activity console below.` (no link)
- cancelled: `CANCELLED` / `Stopped on request. Run it again whenever you are ready.`
- refused: `REFUSED FOR SAFETY` / `ViWo only writes into an empty folder or one it created, never into a game folder. Pick another folder.`
- internal: `SOMETHING BROKE INSIDE VIWO` / `This is a bug, not your mistake. JOBS has the details; please report it.` + `Open JOBS →`
Each box also shows the server message, `HINT:` when present and `code: <code>`.

## SQC-UI-06 (P0) Keyboard: skip link, focus, modals

Steps: reload; press Tab once, then Enter; Tab through the rail and a view; trigger the modal of
SQC-UI-05 step 8 and press Tab repeatedly, then Escape; in SORT run SQC-SORT-02.

Expected: the first Tab stop is `Skip to content` (`#main`); every control is reachable with a
visible focus ring; the modal takes the focus, keeps Tab inside itself and closes on Escape (no
`[FAILED]` line); Enter in a modal field triggers the primary action; no control is mouse-only.

## SQC-UI-07 (P0) Reduced motion

Preconditions: OS reduce-motion on (or DevTools: emulate `prefers-reduced-motion: reduce`).

Steps: the landing (new tab), an extraction, a merger build, a SYSTEM install.

Expected: no scan animation, no typing animation on the feed line, no rail pop, no fade on toasts or
the landing; the determinate bars still fill; the job clock updates once a second; nothing hidden.

## SQC-UI-08 (P0) Progress honesty

Steps: EXTRACT `C:\sqc\doom\game`, then `<repo>\Test-games\freedoom`; watch `LIVE FEED`.

Expected: the rail follows the real stages (`prepare › detect › unpack › export › carve › collect ›
decode › verify › report`); a stage the run did not need is marked `skipped`, never `done`; the bar is
determinate only while a stage reports `x / y` counts, a scan bar otherwise; the counters (`FILES
SCANNED`, `ARCHIVES OK`, ...) match the run record; `still working · last update N s ago` after 5 s
without events; a stage of a second or more ends with `<stage> took <t>`; the clock matches the
job's duration in JOBS within 1 s; `COMPLETE` only after the server answered.

## SQC-UI-09 (P1) JOBS registry and detail

Steps: run jobs of several kinds (an extraction, a search, a failing patch apply, a trace); click
the `RUNNING ...` chip while the trace runs; select each job; cancel the running one.

Expected: the registry lists `n TOTAL` and kind names (`EXTRACTION`, `SURVEY`, `SEARCH`, `CLEANUP`,
`PATCH SET`, `MOD PACKAGE`, `API TRACE`, `AUDIO RECORDING`, `STARTUP CHECK`, `TOOL INSTALL`...) with
state badges `RUNNING` / `SUCCEEDED` / `FAILED` / `CANCELLED`, newest first; opening JOBS (from the
chip or `#jobs`) shows the latest job, so the running one the chip names is in the detail with
`CANCEL JOB`; the detail shows `OPEN <code> <VIEW> →`, the job id, the result, the error box and
`// LOG`; durations as people say them (`4.9 s`, `3 min 20 s`, `3 h 28 min`); `CANCEL JOB` only for
running jobs; a cancelled job ends `CANCELLED` within seconds.

## SQC-UI-10 (P1) No dead ends

Steps: every empty state (an empty workspace in WORKSPACE, SORT, CLEANUP; no survey; no plan in
PATCHED COPY or ASSETS; no groups in MERGER; JOBS with nothing selected) and every error box.

Expected: each names the next step with a button or link (`GO TO EXTRACT`, `See SYSTEM for what to
install →`, `NO JOB SELECTED` + `Pick a job on the left...`); every error box has a NEXT line.

## SQC-UI-11 (P1) Second browser

Steps: SQC-UI-01 and two codes of SQC-UI-05 in a second browser family (Firefox after Chromium).

Expected: the same; no console errors.

## SQC-UI-12 (P2) A page without its token

Steps: save the page as HTML and open the copy, or strip the meta token through a proxy.

Expected: the alert `NO API TOKEN` at the top of main with the instruction to start ViWo and open
the printed address; no request succeeds. (`/index.html` is served with the token like `/`.)

## SQC-UI-13 (P0) Failures are said; error toasts stay until read

Steps:
1. Open the activity console. SEARCH in `C:\nope-ui` (or SORT: `F2` on a file, rename to `bad/name`).
2. Read the toast; wait ten seconds; open another view.
3. Cause the failure again; `DISMISS`.
4. EXTRACT into a workspace that holds one; `CANCEL` (or Escape) the question.
5. Something that succeeds (keep a file in SORT).

Expected: 1: one console line `[FAILED] POST /api/<route>: <message> (<hint>)`; the toast `ERROR
<what> failed: <message>` carries the hint and does not send you to JOBS for something no job held.
2: the error toast does not fade, has `DISMISS`; leaving the view removes it. 3: `DISMISS` removes it.
4: no `[FAILED]` line (a question and a cancel are not failures). 5: `DONE`, `NOTE` and `INFO` toasts
fade after about four seconds.

## SQC-UI-14 (P1) The open page reloads after a server restart

Steps: with the page open, stop `viwo serve` (Ctrl+C); start it again; wait. Then stop and start it
a second time within the same minute.

Expected: `SERVER OFFLINE` while it is down; after the first restart the page reloads by itself
within seconds (the old token is refused with `code: "token"`) and works without a manual reload;
the terminal does not fill with `SECURITY` lines. After the second restart: at most one automatic
reload a minute, no loop.

## SQC-UI-15 (P0) The strip and the job chip

Steps: read the top bar; click each strip entry; click the job chip; start a run and click it
again; `#jobs` in the address bar; click `FORMATS`; record a workflow (20-guides).

Expected: the strip reads `00 SYSTEM`, `01 WORKBOOKS`, `02 RUNBOOKS`, `03 SETTINGS` (numbers dropped
under 1500 px); JOBS is not in the strip and opens from the chip (`JOB IDLE`, `RUNNING <KIND>`, `+n`)
and from `#jobs`, with no code of its own (panels `JOB.A`, `JOB.B`); `FORMATS n/m READY` opens SYSTEM
at its format list (`#system@formats`); a recording adds `● REC n STEPS` (`REC PAUSED`) linking to
RUNBOOKS; none of these changes the arm.

## SQC-UI-16 (P1) The arm homes say what ships

Steps: open STATIC HOME, DYNAMIC HOME and PATCHING HOME; read `END-TO-END PATH`; pick no game first
(`START HERE`).

Expected: with no game, `START HERE` + `PICK A GAME FOLDER`; each row names the tab that runs it by
its live code (`S4 SEARCH`, `D2 RUNTIME`, `P3 PATCHES + MODS`; one in another arm says `(opens in
DYNAMIC)`), shared rows list their steps once; a row is `PLANNED` only when nothing of it ships:
DYNAMIC lists the hook script (`viwo hook`, RUN HOOK SCRIPT) and own-traffic inspection (mitmproxy)
as shipped, PATCHING lists the isolation patcher (RUNTIME > ISOLATION PATCHER, `viwo isolate`).

## SQC-UI-17 (P0) Tab codes are computed

Steps: read the rail of each arm and the strip; add a drop-in plugin with a UI view
(`examples\plugins\hello`) and reload.

Expected: `S0`...`S8`, `D0`...`D2`, `P0`...`P3`, `00`...`03`, each code shown once per arm home; the
add-on view takes the next code of its arm and every later code moves with it.

## Results

| ID | Result | Version | Notes | Tester | Date |
|----|--------|---------|-------|--------|------|
| SQC-UI-01 | PASS (scripted part) | 1.36.0+search+apk (unreleased) | headless Edge 158 over CDP: 21 views at 1920 and 1440, none overflows, titles, `aria-current`, strip and chips (`FORMATS 107/117 READY`, `JOB IDLE`) as written; no console error. "Text never overflows a panel" needs eyes | agent | 2026-11-23 |
| SQC-UI-02 | FAIL | 1.36.0+search+apk (unreleased) | at 1024: SETTINGS scrolls main sideways (a horizontal scrollbar under the form); the arm switch in the 64 px rail clips its labels (`DYNAMI`, `PATCHIN`). 1280 clean | agent | 2026-11-23 |
| SQC-UI-03 | PASS (open, count, clear) / NOT RUN (rest) | 1.36.0+search+apk (unreleased) | `aria-expanded="true"`, `224 LINES`, `CLEAR` -> `0 LINES`; auto-scroll, remembered state and the collapsed latest line need eyes | agent | 2026-11-23 |
| SQC-UI-04 | PASS (but the install) | 1.36.0+search+apk (unreleased) | `RUNNING API TRACE` -> `#jobs`, then `JOB IDLE`; `SERVER OFFLINE` after the server stopped; no console error. Install not run (download) | agent | 2026-11-23 |
| SQC-UI-05 | PASS (offline, http, invalid_request, not_found, unavailable, needs_decision, failed, refused) / NOT RUN (busy, needs_key, cancelled, internal) | 1.36.0+search+apk (unreleased) | every observed title, NEXT text, link and `code:` as written. A cancelled RUNTIME trace showed no `CANCELLED` box in RUNTIME (only the JOBS badge); internal needs a code edit | agent | 2026-11-23 |
| SQC-UI-06 | PASS (scripted part) | 1.36.0+search+apk (unreleased) | first Tab = `Skip to content` (`#main`); the modal held the focus over 8 Tabs and closed on Escape. Focus rings and SORT shortcuts need eyes | agent | 2026-11-23 |
| SQC-UI-07 | NOT RUN | 1.36.0+search+apk (unreleased) | needs eyes | agent | 2026-11-23 |
| SQC-UI-08 | PASS (skipped stages) / NOT RUN (rest) | 1.36.0+search+apk (unreleased) | `tests/test_ui_smoke.py`: skipped stages read `skipped`, visible; the live feed needs eyes | agent | 2026-11-23 |
| SQC-UI-09 | FAIL | 1.36.0+search+apk (unreleased) | the `RUNNING API TRACE` chip opened JOBS on an older job (the latest when the page loaded: `views/jobs.js` 47 picks the latest only when nothing is selected), `CANCEL JOB` hidden; picking the running row showed it, the job was `CANCELLED` in 1 s and the button went. Names, badges and durations (`4.9 s`, `40.7 s`) as written | agent | 2026-11-23 |
| SQC-UI-10 | NOT RUN | 1.36.0+search+apk (unreleased) | needs eyes | agent | 2026-11-23 |
| SQC-UI-11 | NOT RUN | 1.36.0+search+apk (unreleased) | only Edge is scripted here | agent | 2026-11-23 |
| SQC-UI-12 | NOT RUN | 1.36.0+search+apk (unreleased) | `/index.html` also injects the token; a saved copy cannot load its modules from `file://`: needs a proxy or a person | agent | 2026-11-23 |
| SQC-UI-13 | PASS (steps 1-4) / NOT RUN (5) | 1.36.0+search+apk (unreleased) | one `[FAILED] POST /api/search: nothing to search at C:\nope-ui (an absolute path to a file or a folder)`; the error toast with `DISMISS` still there after 6 s, gone after a view change; no `[FAILED]` for the extract question | agent | 2026-11-23 |
| SQC-UI-14 | PASS (first restart) / NOT RUN (second) | 1.36.0+search+apk (unreleased) | the page reloaded by itself and answered; 0 `SECURITY` lines in the new server's terminal | agent | 2026-11-23 |
| SQC-UI-15 | PASS (but REC chip) | 1.36.0+search+apk (unreleased) | strip `00 SYSTEM 01 WORKBOOKS 02 RUNBOOKS 03 SETTINGS`; chip -> `#jobs`; FORMATS -> `#system@formats`; REC chip not looked at | agent | 2026-11-23 |
| SQC-UI-16 | FAIL | 1.36.0+search+apk (unreleased) | DYNAMIC HOME: `— HOOKS + NETWORK a hook loader with hot reload, own-traffic tooling PLANNED` although `viwo hook` (D4) and mitmproxy (attach.net) ship (doc 11.7); PATCHING HOME has no isolation row (`views/home.js` 28-34) | agent | 2026-11-23 |
| SQC-UI-17 | PASS (codes) / NOT RUN (add-on) | 1.36.0+search+apk (unreleased) | S0-S8, D0-D2, P0-P3, 00-03 read in headless Edge and by the smoke test | agent | 2026-11-23 |
