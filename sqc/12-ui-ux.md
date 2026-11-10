# 12 UI and UX

Area code `UI`. Browser window sizes: 1920x1080, 1440x900, 1280x800, 1024x768 (use the browser's
device toolbar or resize the window; the rail collapses to its tab codes under 1200 px). Views, by arm:
STATIC (`#static` home, SURVEY, EXTRACT, WORKSPACE, SORT, CLEANUP, MERGER,
ANALYSIS), DYNAMIC (`#dynamic` home, CAPTURE, RUNTIME), PATCHING (`#patching` home,
PATCHED COPY, PATCHES + MODS), global strip (SYSTEM, WORKBOOKS, RUNBOOKS, SETTINGS; JOBS opens
from the job chip). Views are named here, never numbered: the tab codes are computed and change
when a view is added. Error codes
(`viwo\web\js\ui\feedback.js` ERRORS): offline, http, invalid_request, not_found, busy,
unavailable, needs_key, needs_decision, failed, cancelled, refused, internal.

## SQC-UI-01 (P0) Every view at 1920 and 1440

Steps: at 1920, then 1440, open each arm with the arm switch above the rail, then every view of
that arm from the rail; open SYSTEM, WORKBOOKS, RUNBOOKS and SETTINGS from the top-bar strip and
JOBS from the job chip; scroll to the bottom of each.

Expected: no horizontal scrollbar; each arm opens on its home (`END-TO-END PATH`, every step
`SHIPPED` or `ROADMAP` with an `OPEN` link); the view head (`EXTRACT`, subtitle), panels with
their titles and the action bars (EXTRACT, PATCHED COPY) are visible; text does not overflow its
panel; the top bar shows the strip (SYSTEM, WORKBOOKS, RUNBOOKS, SETTINGS), the GAME selector,
the `WORKSPACE` path and the chips `FORMATS n/m READY` and `JOB IDLE` (the OS and plugin counts
are in SYSTEM); opening a global view keeps the arm;
the rail marks the current view (`aria-current`); the document title is `<VIEW> // ViWo`.

## SQC-UI-02 (P0) Every view at 1280 and 1024

Steps: as 01 at 1280 and 1024.

Expected: under 1200 px the rail shows only the tab codes of the current arm's views with the
names as tooltips; two-column grids become one
column; tables scroll inside their panel, never the page sideways; the action bar stays
reachable; nothing overlaps the activity dock.

## SQC-UI-03 (P0) Activity console dock

Steps: click `// ACTIVITY CONSOLE`; run an extraction; `CLEAR`; collapse.

Expected: the dock expands, shows `n LINES`, auto-scrolls while lines arrive, stops auto-scroll
when you scroll up; `CLEAR` empties it (server log cleared, toast or count `0 LINES`); the open
state is remembered after a reload; collapsed, the dock's header shows the latest line (what is
happening now) while a job runs.

## SQC-UI-04 (P0) Status chips reflect jobs and tools

Steps: start a survey, watch the chip; install a tool from SYSTEM; stop the server.

Expected: `RUNNING SURVEY` (live chip, links to JOBS) while it runs, `JOB IDLE` after;
`FORMATS` count increases after the install without a reload; after stopping the server the chip
becomes `SERVER OFFLINE` (red) with the tooltip to restart, and no uncaught error appears in the
browser console.

## SQC-UI-05 (P0) One error box per code, with the right NEXT text and link

Steps and where to trigger each:
1. `offline`: stop the server, click `DETECT ENGINE`.
2. `http`: with the server running, open `http://127.0.0.1:8081/api/nope` in a tab (JSON 404), and
   in the app trigger a route that returns non-JSON (not reachable normally: SKIP if impossible).
3. `invalid_request`: EXTRACT with an empty path, `RUN EXTRACTION`.
4. `not_found`: EXTRACT with `C:\nope`.
5. `busy`: SQC-SAFE-06.
6. `unavailable`: remove `third_party\gdre` and `third_party\godotpcktool`, extract the godot
   fixture.
7. `needs_key`: SQC-EXT-07 step 1 in the UI.
8. `needs_decision`: SQC-MODE-07 step 2 in the UI.
9. `failed`: extract `C:\sqc\doom\game` with only `broken.wad` in a copy of the folder.
10. `cancelled`: cancel a job.
11. `refused`: SQC-SAFE-02 step 3.
12. `internal`: edit `viwo\api\handlers_tools.py` to raise `RuntimeError` in `survey_library`,
    restart, run a survey (restore the file afterwards).

Expected, per code, the box title and NEXT text exactly:
- offline: `VIWO IS NOT REACHABLE` / `Start ViWo again (viwo serve, or Start.py), then reload this page.`
- http: `UNEXPECTED SERVER REPLY` / `Reload the page. If it keeps happening, check the terminal ViWo runs in.`
- invalid_request: `CHECK YOUR INPUT` / `A path or option is not valid. Correct it and try again.`
- not_found: `NOT FOUND` / `The file or folder is gone, or the path has a typo. Check it, or refresh this view.`
- busy: `WORKSPACE BUSY` / `Another job is using this workspace. Wait for it to finish, then try again.` + `Open JOBS →`
- unavailable: `TOOL NOT INSTALLED` / `A tool this needs is missing. Install it with one click in SYSTEM, then try again.` + `Open SYSTEM →`
- needs_key: `ENCRYPTION KEY NEEDED` / `These files are encrypted. Enter the key under ENGINE OPTIONS, then run again.` + `Open EXTRACT →`
- needs_decision: `YOUR CHOICE IS NEEDED` / `Answer the question ViWo asked, then run again.` (EXTRACT shows the modal instead)
- failed: `IT DID NOT WORK` / `The message above says why; the same line is in the activity console below.` (no link)
- cancelled: `CANCELLED` / `Stopped on request. Run it again whenever you are ready.`
- refused: `REFUSED FOR SAFETY` / `ViWo only writes into an empty folder or one it created, never into a game folder. Pick another folder.`
- internal: `SOMETHING BROKE INSIDE VIWO` / `This is a bug, not your mistake. JOBS has the details; please report it.` + `Open JOBS →`
Each box also shows the server message, `HINT:` when present and `code: <code>`.

## SQC-UI-06 (P0) Keyboard: skip link, focus, modals, sort shortcuts

Steps: reload; press Tab once (skip link `Skip to content` appears, Enter jumps to main); Tab
through the rail and the current view; open `WORKSPACE > SWITCH` and press Tab repeatedly, then
Escape; in SORT run SQC-SORT-02.

Expected: every control is reachable and shows a visible focus ring; the modal traps Tab inside
itself and closes on Escape; Enter in the modal field triggers the primary action; no control is
mouse-only.

## SQC-UI-07 (P0) Reduced motion

Preconditions: OS reduce-motion on.

Steps: landing (new tab), an extraction, a merger build, SYSTEM install.

Expected: no scan animation, no typing animation on the feed line, no rail pop, no fade on
toasts or the landing; the determinate bars still fill; the job clock updates once per second;
nothing is hidden or unreadable.

## SQC-UI-08 (P0) Progress honesty

Steps: extract `C:\sqc\doom\game`, then a large real game; watch `LIVE FEED`.

Expected: the rail follows the real stages (`prepare › detect › unpack › export › carve › collect
› decode › verify › report`), stages without events are marked `no events reported` (dashed),
never `done`; the bar is determinate only while a stage reports `x / y` counts (unpack lumps,
decode files, collect files), scan-bar otherwise; the counters (`FILES SCANNED`, `ARCHIVES OK`,
`FILES CARVED`...) match the run record; `still working · last update N s ago` appears after 5 s
without events; a stage of a second or more ends with `<stage> took <t>`; the clock matches the
job's duration in JOBS within 1 s; `COMPLETE` is shown
only after the server answered.

## SQC-UI-09 (P1) JOBS registry and detail

Steps: run three jobs of different kinds; open JOBS from the job chip; select each; cancel a
running one.

Expected: the registry lists kind names `EXTRACTION`, `SURVEY`, `MERGER BUILD`, `PATCHED COPY`,
`STARTUP CHECK`, `TOOL INSTALL` with state badges `RUNNING` / `SUCCEEDED` / `FAILED` /
`CANCELLED`; the latest job opens by itself; the detail shows the full log and result; durations
read as a person says them (`8.2 s`, `3 min 20 s`, `3 h 28 min`); `CANCEL JOB` is visible only
for running jobs.

## SQC-UI-10 (P1) No dead ends

Steps: visit every empty state (empty workspace in WORKSPACE, SORT, CLEANUP; no survey; no plan
in PATCHED COPY; no groups in MERGER) and every error box.

Expected: each empty state names the next step with a button or link (`GO TO EXTRACT`, `See
SYSTEM for what to install →`); every error box has a NEXT line.

## SQC-UI-11 (P1) Second browser

Steps: repeat SQC-UI-01 and SQC-UI-05 (two codes) in a second browser family (Firefox if the
first was Chromium).

Expected: same results; no console errors.

## SQC-UI-12 (P2) Page without token

Steps: save the page as HTML and open it from disk, or open `http://localhost:8081/index.html`
in a way that strips the meta token (view source and open a copy).

Expected: the alert `NO API TOKEN` at the top of main with the instruction to start ViWo and open
the printed address; no requests succeed.

## SQC-UI-13 (P0) Failures are said; error toasts stay until read

Steps:
1. Open the activity console. In SORT press `F2` on a file and rename it to `bad/name`.
2. Read the toast; wait ten seconds; open another view.
3. Cause the failure again; click `DISMISS`.
4. Run an extraction into a workspace that already holds one; `CANCEL` the question.
5. Do something that succeeds (keep a file in SORT).

Expected: 1: the console and the log gain one line `[FAILED] POST /api/<route>: <message>
(<hint>)`: the route, the message and the hint of the answer; the toast (`ERROR`) carries the
same message and does not send you to JOBS for something no job held. 2: the error toast does not
fade and has a `DISMISS` button; leaving the view removes it. 3: `DISMISS` removes it. 4: no
`[FAILED]` line: a question (`needs_decision`) and a cancel are not failures. 5: `DONE`, `NOTE`
and `INFO` toasts still fade after about four seconds.

## SQC-UI-14 (P1) The open page reloads after a server restart

Steps: with the page open on WORKSPACE, stop `viwo serve` (Ctrl+C); start it again; wait. Then
stop and start it a second time within the same minute.

Expected: `SERVER OFFLINE` while it is down; after the first restart the page reloads by itself
within a few seconds (the old page's token is refused with `code: "token"`) and works again
without a manual reload; the terminal does not fill with SECURITY lines. After the second
restart it does not reload in a loop: at most one automatic reload a minute (then it reloads, or
F5 does).

## SQC-UI-15 (P0) The strip and the job chip

Steps: read the top bar; click each strip entry; click the job chip; start a survey and click the
chip again; open `#jobs` in the address bar; click `FORMATS`.

Expected: the strip shows SYSTEM, WORKBOOKS, RUNBOOKS, SETTINGS, in that order; JOBS is not in the
strip and opens from the job chip (`JOB IDLE`, `RUNNING SURVEY` while one runs, `+n` when
several run) and from `#jobs`; JOBS has no tab code of its own (its panels are tagged `JOB`);
`FORMATS n/m READY` opens SYSTEM on its format list; while a workflow is recorded a `● REC n
STEPS` chip is added (SQC-GUIDE-03); opening any of these keeps the current arm.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-UI-01 | | version: | | |
| SQC-UI-02 | | | | |
| SQC-UI-03 | | | | |
| SQC-UI-04 | | | | |
| SQC-UI-05 | | | | |
| SQC-UI-06 | | | | |
| SQC-UI-07 | | | | |
| SQC-UI-08 | | | | |
| SQC-UI-09 | | | | |
| SQC-UI-10 | | | | |
| SQC-UI-11 | | | | |
| SQC-UI-12 | | | | |
| SQC-UI-13 | NOT RUN | added at 1.20.40 | | |
| SQC-UI-14 | NOT RUN | added at 1.20.40 | | |
| SQC-UI-15 | NOT RUN | added at 1.20.40 | | |
