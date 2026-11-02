# 12 UI and UX

Area code `UI`. Browser window sizes: 1920x1080, 1440x900, 1280x800, 1024x768 (use the browser's
device toolbar or resize the window; the rail collapses to numbers under 1200 px). Views: 01
EXTRACT, 02 WORKSPACE, 03 SORT, 04 JOBS, 05 SYSTEM, 06 MERGER, 07 SURVEY, 08 CLEANUP, 09 PATCHED
COPY. Error codes (`viwo\web\js\ui.js` ERRORS): offline, http, invalid_request, not_found,
busy, unavailable, needs_key, needs_decision, failed, cancelled, refused, internal.

## SQC-UI-01 (P0) Every view at 1920 and 1440

Steps: open each of the nine views (rail click, then the hash `#system` etc.) at 1920, then 1440;
scroll to the bottom of each.

Expected: no horizontal scrollbar; the view head (`01 EXTRACT`, subtitle), panels with their
`NN.X` tags, and the action bar (01, 09) are visible; text does not overflow its panel; the top
bar shows the chips `OS`, `PLUGINS`, `FORMATS n/m READY`, `JOB IDLE` and the `WORKSPACE` path;
the rail marks the current view (`aria-current`); the document title is `<VIEW> // ViWo`.

## SQC-UI-02 (P0) Every view at 1280 and 1024

Steps: as 01 at 1280 and 1024.

Expected: under 1200 px the rail shows only the numbers `01..09` with the names as tooltips; two-
column grids become one column; tables scroll inside their panel, never the page sideways; the
action bar stays reachable; nothing overlaps the activity dock.

## SQC-UI-03 (P0) Activity console dock

Steps: click `// ACTIVITY CONSOLE`; run an extraction; `CLEAR`; collapse.

Expected: the dock expands, shows `n LINES`, auto-scrolls while lines arrive, stops auto-scroll
when you scroll up; `CLEAR` empties it (server log cleared, toast or count `0 LINES`); the open
state is remembered after a reload.

## SQC-UI-04 (P0) Status chips reflect jobs and tools

Steps: start a survey, watch the chip; install a tool from 05 SYSTEM; stop the server.

Expected: `RUNNING SURVEY` (live chip, links to 04 JOBS) while it runs, `JOB IDLE` after;
`FORMATS` count increases after the install without a reload; after stopping the server the chip
becomes `SERVER OFFLINE` (red) with the tooltip to restart, and no uncaught error appears in the
browser console.

## SQC-UI-05 (P0) One error box per code, with the right NEXT text and link

Steps and where to trigger each:
1. `offline`: stop the server, click `DETECT ENGINE`.
2. `http`: with the server running, open `http://127.0.0.1:8081/api/nope` in a tab (JSON 404), and
   in the app trigger a route that returns non-JSON (not reachable normally: SKIP if impossible).
3. `invalid_request`: 01 EXTRACT with an empty path, `RUN EXTRACTION`.
4. `not_found`: 01 EXTRACT with `C:\nope`.
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
- offline: `VIWO IS NOT REACHABLE` / `Start ViWo again (python3 Start.py), then reload this page.`
- http: `UNEXPECTED SERVER REPLY` / `Reload the page. If it keeps happening, check the terminal ViWo runs in.`
- invalid_request: `CHECK YOUR INPUT` / `A path or option is not valid. Correct it and try again.`
- not_found: `NOT FOUND` / `The file or folder is gone, or the path has a typo. Check it, or refresh this view.`
- busy: `WORKSPACE BUSY` / `Another job is using this workspace...` + `Open 04 JOBS →`
- unavailable: `TOOL NOT INSTALLED` / `A tool this needs is missing. Install it, restart ViWo and try again.` + `Open 05 SYSTEM →`
- needs_key: `ENCRYPTION KEY NEEDED` / `These files are encrypted. Enter the key under ENGINE OPTIONS, then run again.` + `Open 01 EXTRACT →`
- needs_decision: `YOUR CHOICE IS NEEDED` / `Answer the question ViWo asked, then run again.` (01 shows the modal instead)
- failed: `IT DID NOT WORK` / `The message above says why. The full log is in 04 JOBS.` + `Open 04 JOBS →`
- cancelled: `CANCELLED` / `Stopped on request. Run it again whenever you are ready.`
- refused: `REFUSED FOR SAFETY` / `ViWo only writes into an empty folder or one it created, never into a game folder. Pick another folder.`
- internal: `SOMETHING BROKE INSIDE VIWO` / `This is a bug, not your mistake. 04 JOBS has the details; please report it.` + `Open 04 JOBS →`
Each box also shows the server message, `HINT:` when present and `code: <code>`.

## SQC-UI-06 (P0) Keyboard: skip link, focus, modals, sort shortcuts

Steps: reload; press Tab once (skip link `Skip to content` appears, Enter jumps to main); Tab
through the rail and the current view; open `WORKSPACE > SWITCH` and press Tab repeatedly, then
Escape; in 03 SORT run SQC-SORT-02.

Expected: every control is reachable and shows a visible focus ring; the modal traps Tab inside
itself and closes on Escape; Enter in the modal field triggers the primary action; no control is
mouse-only.

## SQC-UI-07 (P0) Reduced motion

Preconditions: OS reduce-motion on.

Steps: landing (new tab), an extraction, a merger build, 05 SYSTEM install.

Expected: no scan animation, no typing animation on the feed line, no rail pop, no fade on
toasts or the landing; the determinate bars still fill; the job clock updates once per second;
nothing is hidden or unreadable.

## SQC-UI-08 (P0) Progress honesty

Steps: extract `C:\sqc\doom\game`, then a large real game; watch `01.E LIVE FEED`.

Expected: the rail follows the real stages (`prepare › detect › unpack › export › carve › collect
› decode › verify › report`), stages without events are marked `no events reported` (dashed),
never `done`; the bar is determinate only while a stage reports `x / y` counts (unpack lumps,
decode files, collect files), scan-bar otherwise; the counters (`FILES SCANNED`, `ARCHIVES OK`,
`FILES CARVED`...) match the run record; `still working · last update N s ago` appears after 5 s
without events; the clock matches the job's `elapsed` in 04 JOBS within 1 s; `COMPLETE` is shown
only after the server answered.

## SQC-UI-09 (P1) 04 JOBS registry and detail

Steps: run three jobs of different kinds; open 04 JOBS; select each; cancel a running one.

Expected: the registry lists kind names `EXTRACTION`, `SURVEY`, `MERGER BUILD`, `PATCHED COPY`,
`STARTUP CHECK`, `TOOL INSTALL` with state badges `RUNNING` / `SUCCEEDED` / `FAILED` /
`CANCELLED`; the detail shows the full log and result; `CANCEL JOB` is visible only for running
jobs.

## SQC-UI-10 (P1) No dead ends

Steps: visit every empty state (empty workspace in 02, 03, 08; no survey; no plan in 09; no
groups in 06) and every error box.

Expected: each empty state names the next step with a button or link (`GO TO 01 EXTRACT`, `SEE 05
SYSTEM...`); every error box has a NEXT line.

## SQC-UI-11 (P1) Second browser

Steps: repeat SQC-UI-01 and SQC-UI-05 (two codes) in a second browser family (Firefox if the
first was Chromium).

Expected: same results; no console errors.

## SQC-UI-12 (P2) Page without token

Steps: save the page as HTML and open it from disk, or open `http://localhost:8081/index.html`
in a way that strips the meta token (view source and open a copy).

Expected: the alert `NO API TOKEN` at the top of main with the instruction to start ViWo and open
the printed address; no requests succeed.

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
