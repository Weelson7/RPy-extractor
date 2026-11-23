# 20 Guides: workbooks, runbooks, workflows (`viwo workbook`, `viwo runbook`)

Area code `GUIDE`. Contract doc 19. WORKBOOKS and RUNBOOKS are in the strip (`00 SYSTEM`, `01
WORKBOOKS`, `02 RUNBOOKS`, `03 SETTINGS`); the workflow recorder is the panel `RECORD A WORKFLOW` of
RUNBOOKS; RUNBOOKS > `EDIT` opens the structured step editor. Shipped guides live in
`viwo\data\workbooks\` and `viwo\data\runbooks\`, yours in `viwo-data\workbooks\` and
`viwo-data\runbooks\` (beside `tmp`). A workbook teaches, it never drives the tool: a ViWo action
inside a child tool is a FAIL. Save your own JSON files without a byte-order mark (PowerShell 5.1
`Set-Content -Encoding utf8` writes one: use `[IO.File]::WriteAllText`).

## SQC-GUIDE-01 (P0) WORKBOOKS: one step at a time, the step remembered

Steps:
1. Strip > WORKBOOKS. Read the list; use the tool filter (`ALL`, then each tool).
2. Open "Patch a byte, live and into a file"; `NEXT →` twice; reload the page; open another view
   and come back.
3. `← PREVIOUS`; click a step under `// ALL STEPS`; on the last step `DONE: START OVER`.
4. Click `OPEN THE TOOL IN ... →` on an x64dbg, a Cheat Engine and a Ghidra workbook.
5. ANALYSIS > `HOW TO: GHIDRA`; RUNTIME > `DEBUGGER AND MEMORY` > `HOW TO: X64DBG` and
   `HOW TO: CHEAT ENGINE`; CAPTURE > `HOW TO: RENDERDOC`.
6. `viwo workbook`; `viwo workbook x64dbg-patch-a-byte`; `viwo --json workbook`.
7. Write `{"id": "broken"` to `viwo-data\workbooks\broken.json`; copy
   `viwo\data\workbooks\x64dbg-patch-a-byte.json` to `viwo-data\workbooks\mine.json` and change its
   title (no BOM); `viwo workbook`; reload WORKBOOKS. Then delete both files.

Expected:
- 1: six workbooks, each with its tool badge and `n steps`: `Find a value, change it, find what
  writes it` (CHEAT ENGINE, 6), `Find the code that uses a string` (GHIDRA, 6), `Patch an
  instruction and export the program` (GHIDRA, 6), `Read your game's own web traffic` (MITMPROXY,
  5), `Read a captured frame: draws, textures, meshes, shaders` (RENDERDOC, 6), `Patch a byte, live
  and into a file` (X64DBG, 6); the counter reads `6 OF 6` and follows the filter; filters `ALL
  CHEAT ENGINE GHIDRA MITMPROXY RENDERDOC X64DBG` (names as users know them, never pin ids).
- 2: `STEPS` shows one step: `// STEP 3 OF 6`, title, text, keys, `YOU SHOULD SEE`; the step
  reached is still shown after the reload and after the view change.
- 3: each moves to the step named; the last step's button starts over at step 1.
- 4: x64dbg, Cheat Engine and mitmproxy workbooks open `D2 RUNTIME`, Ghidra ones `S8 ANALYSIS`; the
  RenderDoc one has no such button.
- 5: each opens WORKBOOKS filtered to that tool.
- 6: the table `ID TOOL STEPS TITLE` with the six ids; the workbook's numbered steps with `you should
  see:`; one JSON document (`data.workbooks` 6, none `stale` while the pins match).
- 7: `viwo: warning: workbook ...\broken.json skipped: unreadable (Expecting ',' delimiter: ...)`
  (CLI warning, envelope `warnings`, and named under the list in the UI), never a crash; the copy
  replaces the shipped one: `x64dbg-patch-a-byte ... SQC copy title (yours)`, `source: "yours"`,
  `YOURS` in the UI; after the delete the shipped one is back.

## SQC-GUIDE-02 (P0) RUNBOOKS: run, your turn, resume, stop (UI)

Preconditions: `viwo serve`; WORKSPACE > SWITCH to a new empty folder `C:\sqc\_ws\rb`.

Steps:
1. Strip > RUNBOOKS; select "Extract a game and plan its cleanup".
2. Empty `GAME FOLDER (THE TOP BAR'S GAME)`; `RUN`.
3. Game folder `C:\sqc\renpy\game`; `RUN`.
4. At the step that is yours (`YOUR TURN`): open `ANSWER` on the step before it; `DONE, CONTINUE`.
5. Game folder `C:\nope`; `RUN`; then `C:\sqc\renpy\game` again and `RUN FROM HERE` on the failed step.
6. During a run: `STOP`.

Expected:
- 1: three shipped runbooks: "Apply a patch set into a patched copy" (3 steps), "Extract a game and
  plan its cleanup" (4), "Find a hardcoded value and patch it live" (4), each with `n steps · m yours
  to do`; every step a readable row (what it runs, its target, its options as key/value) with its
  JSON behind a closed toggle; the note names the active workspace.
- 2: refused before anything runs, the empty value named; no job is created.
- 3: the steps run in order as jobs (`RUNNING`, then `DONE`), each with its job id, `OPEN JOBS →`
  and its `ANSWER`; JOBS lists a `SURVEY`, an `EXTRACTION` and a `CLEANUP`.
- 4: the run waits on `YOUR TURN` until `DONE, CONTINUE`; `ANSWER` holds the plan; at the end the
  toast `<title>: every step done.`
- 5: `FAILED`, error box `STEP n FAILED` with `Fix it, then RUN FROM HERE.`; the later steps do not
  run; `RUN FROM HERE` resumes at that step.
- 6: toast `The run stops after the current step.`; the running step finishes, the next does not start.

## SQC-GUIDE-03 (P0) Workflow recorder: record, save, replay, differ

Preconditions: `viwo serve`; an empty active workspace; the game `C:\sqc\renpy\game`.

Steps (UI: RUNBOOKS > `RECORD A WORKFLOW`; API equivalents in brackets):
1. `START RECORDING` with an empty title; then with a title and no game picked in the top bar
   [`POST /api/recording {action: start, title: "", game}`; `{title: "sqc flow", game: ""}`].
2. Pick the game (top bar `GAME`), title `sqc flow`, `START RECORDING`.
3. SURVEY the game; EXTRACT it; CLEANUP `SCAN` (plan).
4. `PAUSE`; run a search; `CONTINUE`.
5. `ADD A STEP YOU DO (IN A CHILD TOOL)`: a title and a `HOW` text, `ADD THE STEP`.
6. `STOP AND SAVE`; read `viwo-data\runbooks\sqc-flow.json`.
7. Switch to a new empty workspace; select the saved runbook; `RUN` [`POST /api/runbooks/step` per
   step with `values {game}`].
8. Copy `C:\sqc\renpy` to `C:\sqc\renpy-copy`, delete `game\script.rpy` from the copy, pick the copy
   as the game; `RUN` again.
9. Start a recording and `DISCARD` > `DISCARD`.

Expected:
- 1: `Give the workflow a title first.` / `Pick the game first (the top bar's GAME): the workflow
  replays on a game.` [`invalid_request` `give the workflow a title`, `pick the game first (the top
  bar's GAME)`]; nothing recorded.
- 2: the panel shows `● REC`, the title and the game; the status chips gain `● REC 0 STEPS`, from
  every view, linking to RUNBOOKS.
- 3: each action that succeeds adds a step (`Survey`/`survey`, `Extract`/`extract`, `Cleanup
  (plan)`/`cleanup`); the chip counts them.
- 4: `PAUSED` / `REC PAUSED`; the search is not added; after `CONTINUE` actions are added again.
- 5: the note is a step marked `(you)` (no `do`).
- 6: toast `Saved as the runbook sqc-flow.`, badge `YOURS` [`saved: "sqc-flow"`]. In the file: `{game}`
  and `{workspace}` instead of the paths; the extract with `onExisting: "new"`; each action step's
  `expect {digest, facts}`; no process id, job id or time; the note step `{title, text, workbook}`.
- 7: every step proceeds by itself (`differs: []`), the run waits at the note (`YOUR TURN`) and ends
  `every step done`.
- 8: the survey step stops: `DIFFERS: YOUR CALL` with each difference (`differs from the recording:
  ...`, or `the answer differs deeper than its facts show (see JOBS)`); `CONTINUE ANYWAY` goes on,
  `STOP` ends it.
- 9: the confirmation `DISCARD THE RECORDING`; nothing saved; the `REC` chip gone
  [`GET /api/recording` → `recording: null`].

## SQC-GUIDE-04 (P0) Runbooks on the command line

Steps:
1. `viwo runbook`; `viwo runbook extract-and-clean`
2. `cmd /c "type NUL | viwo runbook extract-and-clean --run --workspace C:\sqc\_ws\rb2 --set game=C:\sqc\renpy\game --set nosuch=1"`
3. The same with stdin from the NUL device: `cmd /c "viwo runbook extract-and-clean --run --workspace C:\sqc\_ws\rb3 --set game=C:\sqc\renpy\game < NUL"`
4. `viwo runbook extract-and-clean --run --workspace C:\sqc\_ws\rb2 --set game=C:\sqc\renpy\game --from 9`
5. `viwo runbook extract-and-clean --run --workspace C:\sqc\_ws\rb4` (no `game`)

Expected:
- 1: the table `ID STEPS TITLE` with the three ids; the steps of one, an action step as `do <kind>
  {params}`.
- 2: stderr `[RUNBOOK] 1/4 Survey the game (read-only)` ... `4/4 Review the plan and apply what you
  want`, each action's answer; `--set nosuch: extract-and-clean has no value of that name (...)`;
  without a terminal it stops at the step that is yours: `step 4 is yours: do it; it is the last
  step` (an earlier one names `--from <n>`); exit 0.
- 3: as 2: no terminal, the run stops at the step that is yours and says so; never `internal`.
- 4: `viwo: invalid_request: --from 9: extract-and-clean has steps 1-4`, exit 2.
- 5: `viwo: invalid_request: step 1 (Survey the game (read-only)): this step needs a value for game`,
  hint `then --from 1`, exit 2.

## SQC-GUIDE-05 (P0) The structured runbook editor

Preconditions: `viwo serve`.

Steps: RUNBOOKS > select "Extract a game and plan its cleanup" > `EDIT`.
1. Read the editor: `ID (LOWERCASE, DIGITS, DASHES)`, `TITLE`, `SUMMARY`, the inputs, the steps.
2. `ADD STEP`; type a title; `ADD OPTION` with key `folder`, value `{game}`; `UP` / `DOWN` on it;
   switch a step between `ACTION` and `YOU DO`; open the JSON toggle, change the title there,
   `APPLY JSON`.
3. Make a rule error (an unknown job kind in the JSON, or an id with a capital); `SAVE`.
4. Fix it; `SAVE`; reload RUNBOOKS; `DELETE MY COPY` > `DELETE`.
5. `NEW`; remove a brace from the JSON; `SAVE`.

Expected: 1: every field present, an action step with its job (from the known kinds), target and
options as typed key/value, a secret input's value masked. 2: the new step appears with its title
and option; reordering moves it; the kind switch swaps the fields; `APPLY JSON` reads the edit back
into the form (one working copy). 3: the server's rule error shows inline, no step is dropped,
nothing is written. 4: toast `Saved <id>.`; the file is in `viwo-data\runbooks\`; the runbook shows
`YOURS`; the untouched first step keeps `gamePath: {game}` and the boolean `plan`; after the delete
the shipped one is back. 5: toast `Not valid JSON: ...`; nothing written.

## SQC-GUIDE-06 (P0) A secret is never written: the PCK key of a recorded extract

Preconditions: `viwo serve --ini C:\sqc\ini\godot-fake.ini` (fake GDRE + GodotPckTool; key `ab` x 32);
an empty active workspace.

Steps: record (title `sqc secret`, game `C:\sqc\godot\encrypted`) one extract with the key under
ENGINE OPTIONS [`pluginOptions: {godot: {encryption_key: <key>}}`]; stop and save; search
`viwo-data\`, the workspace, `GET /api/logs` and `GET /api/jobs` for the key; replay the step on a
new workspace without the key, then with it.

Expected: the runbook has `inputs: [{name: "secret_1", label: "godot.encryption_key (secret: given
at each run, never saved)", secret: true}]` and the step's option `"encryption_key": "{secret_1}"`;
the key is in no file, log or job; the UI asks it in a password field and does not keep it after a
reload; without it the replay answers `invalid_request` `this step needs a value for secret_1`; with
it the step proceeds (`differs: []`).

## Results

| ID | Result | Version | Notes | Tester | Date |
|----|--------|---------|-------|--------|------|
| SQC-GUIDE-01 | PASS (steps 1, 6, 7) / NOT RUN (2-5) | 1.36.0+search+apk (unreleased) | list, filter names and step 1 read in headless Edge; CLI 6-7 as written. A copy saved with a UTF-8 BOM is refused (`Unexpected UTF-8 BOM (decode using utf-8-sig)`). Steps 2-5 need a person (step navigation, handoff buttons) | agent | 2026-11-23 |
| SQC-GUIDE-02 | NOT RUN | 1.36.0+search+apk (unreleased) | UI run flow not scripted; the same actions ran through the API in SQC-GUIDE-03 | agent | 2026-11-23 |
| SQC-GUIDE-03 | PASS (API) / NOT RUN (UI) | 1.36.0+search+apk (unreleased) | through the API on a live server: steps 1-9 as written (step 8 answered `the answer differs deeper than its facts show (see JOBS)`); the UI panel, chip and DIFFERS box need a person | agent | 2026-11-23 |
| SQC-GUIDE-04 | FAIL | 1.36.0+search+apk (unreleased) | steps 1, 2, 4, 5 as written; step 3 (stdin from NUL, the old SQC's `< NUL`): `press Enter when it is done ... viwo: internal: EOFError: EOF when reading a line`, exit 1 (`viwo/cli_guides.py` 91-93: `isatty()` is true for NUL on Windows and EOFError is not caught) | agent | 2026-11-23 |
| SQC-GUIDE-05 | PASS (add step, option, save, round trip) / NOT RUN (rest) | 1.36.0+search+apk (unreleased) | `tests/test_ui_smoke.py` (14 tests, OK): ADD STEP, ADD OPTION `folder={game}`, SAVE, reload, `gamePath {game}` and boolean `plan` kept; reorder, kind switch, APPLY JSON, rule error, DELETE, NEW not run | agent | 2026-11-23 |
| SQC-GUIDE-06 | PASS (API) / NOT RUN (UI) | 1.36.0+search+apk (unreleased) | key in no file under `viwo-data\` or the workspace, not in logs or jobs; replay refused without it, same with it. The password field and reload need a person | agent | 2026-11-23 |
