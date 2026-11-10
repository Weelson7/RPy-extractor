# 20 Guides: workbooks, runbooks, workflows (`viwo workbook`, `viwo runbook`)

Area code `GUIDE`. Contract doc 19. WORKBOOKS and RUNBOOKS are in the strip (SYSTEM, WORKBOOKS,
RUNBOOKS, SETTINGS); the workflow recorder is the panel `RECORD A WORKFLOW` of RUNBOOKS. Shipped
guides live in `viwo\data\workbooks\` and `viwo\data\runbooks\`, yours in `viwo-data\workbooks\`
and `viwo-data\runbooks\`. Fixtures: `renpy`, `godot` (encrypted). A workbook teaches, it never
drives the tool: a ViWo action inside a child tool is a FAIL.

## SQC-GUIDE-01 (P0) WORKBOOKS: one step at a time, the step remembered

Steps:
1. Strip > WORKBOOKS. Read the list; use the tool filter (`ALL`, then each tool).
2. Open "Patch a byte, live and into a file"; `NEXT →` twice; reload the page; open another view
   and come back.
3. `← PREVIOUS`; click a step under `// ALL STEPS`; on the last step `DONE: START OVER`.
4. Click `OPEN THE TOOL IN ... →` on an x64dbg, a Cheat Engine and a Ghidra workbook.
5. ANALYSIS > `TARGETS` > `HOW TO: GHIDRA`; RUNTIME > `HOW TO: X64DBG` and `HOW TO: CHEAT ENGINE`;
   CAPTURE > `TARGET` > `HOW TO: RENDERDOC`.
6. `viwo workbook`; `viwo workbook x64dbg-patch-a-byte`; `viwo --json workbook`.
7. Save the text `{"id": "broken"` as `viwo-data\workbooks\broken.json`; copy
   `viwo\data\workbooks\x64dbg-patch-a-byte.json` into `viwo-data\workbooks\` and change its
   title; reload WORKBOOKS; `viwo workbook`.

Expected:
- 1: every shipped workbook with its tool badge and `n steps`; the counter reads `n OF m` and
  follows the filter; a tool is named as its users know it (`RENDERDOC`, `CHEAT ENGINE`), never
  by its pin id.
- 2: `STEPS` shows one step: `// STEP 3 OF n`, its title and text, the keys, `YOU SHOULD SEE`;
  the step reached is still the one shown after the reload and after the view change.
- 3: each moves to the step named; the last step's button starts over at step 1.
- 4: x64dbg and Cheat Engine workbooks open RUNTIME, Ghidra ones open ANALYSIS; a workbook whose
  tool no handoff opens (RenderDoc) has no such button.
- 5: each opens WORKBOOKS filtered to that tool.
- 6: the list; the one workbook with its steps; one JSON document. Steps written for another
  version than the pinned tool are marked stale (`WRITTEN FOR ANOTHER VERSION` in the UI, a
  warning on the CLI).
- 7: `broken.json` is skipped and named under the list and as a CLI warning, never a crash; your
  copy replaces the shipped workbook of that id (`YOURS`, `· yours`). Cleanup: delete both files;
  the shipped one is back.

## SQC-GUIDE-02 (P0) RUNBOOKS: run, your turn, resume, edit

Preconditions: the active workspace is an empty one (`WORKSPACE > SWITCH` to a new empty folder
`C:\sqc\_ws\rb`).

Steps:
1. Strip > RUNBOOKS; select "Extract a game and plan its cleanup".
2. Empty `GAME FOLDER (THE TOP BAR'S GAME)`; `RUN`.
3. Game folder `C:\sqc\renpy\game`; `RUN`.
4. At the step that is yours (`YOUR TURN`): open `ANSWER` on the step before it; `DONE, CONTINUE`.
5. Game folder `C:\nope`; `RUN`; then set `C:\sqc\renpy\game` again and `RUN FROM HERE` on the
   failed step.
6. During a run: `STOP`.
7. `EDIT`: change the title; `SAVE`. Then `DELETE MY COPY` > `DELETE`.
8. `NEW`; remove a brace from the JSON; `SAVE`.
9. CLI: `viwo runbook`; `viwo runbook extract-and-clean`;
   `viwo runbook extract-and-clean --run --workspace C:\sqc\_ws\rb2 --set game=C:\sqc\renpy\game --set nosuch=1 < NUL`;
   then the same with `--from 9`.

Expected:
- 1: three shipped runbooks ("Extract a game and plan its cleanup", "Find a hardcoded value and
  patch it live", "Apply a patch set into a patched copy"), each with `n steps · m yours to do`;
  the note names the active workspace.
- 2: refused before anything runs, the empty value named; no job is created.
- 3: the steps run in order as jobs (`RUNNING`, then `DONE`), each with its job id, `OPEN JOBS →`
  and its `ANSWER`; JOBS lists a `SURVEY`, an `EXTRACTION` and the cleanup plan.
- 4: the run waits on `YOUR TURN` until `DONE, CONTINUE`; `ANSWER` holds what the action
  answered (the plan); at the end the toast `<title>: every step done.`
- 5: the step fails (`FAILED`, error box `STEP n FAILED` with `Fix it, then RUN FROM HERE.`),
  the run stops there, the later steps are not run; `RUN FROM HERE` resumes at that step.
- 6: toast `The run stops after the current step.`; the running step finishes, the next does
  not start.
- 7: toast `Saved <id>.`; the file is in `viwo-data\runbooks\`; the runbook shows `YOURS` and
  replaces the shipped one until deleted; after the delete the shipped one is back.
- 8: toast `Not valid JSON: ...`; nothing is written.
- 9: the list; the one runbook; the run prints each step and its answer on stderr, says `--set
  nosuch: extract-and-clean has no value of that name (...)`, and without a terminal stops at
  the step that is yours, naming `--from <n>` to resume; `--from 9` answers `invalid_request:
  --from 9: extract-and-clean has steps 1-<n>`, exit 2.

## SQC-GUIDE-03 (P0) Workflow recorder: record, save, replay, differ

Preconditions: the `godot` fake tools (`--ini C:\sqc\ini\godot-fake.ini` on `viwo serve`), an
empty active workspace.

Steps:
1. RUNBOOKS > `RECORD A WORKFLOW`: `START RECORDING` with an empty title; then with a title and
   no game picked in the top bar.
2. Pick the game `C:\sqc\godot\encrypted` (top bar `GAME`), title `sqc flow`, `START RECORDING`.
3. Open EXTRACT: enter the PCK key under `ENGINE OPTIONS`, `RUN EXTRACTION`. Open CLEANUP: `SCAN`.
4. Back in RUNBOOKS: `PAUSE`; run a survey; `CONTINUE`.
5. `ADD A STEP YOU DO (IN A CHILD TOOL)`: a title and a `HOW` text, `ADD THE STEP`.
6. `STOP AND SAVE`. Open `viwo-data\runbooks\` and read the saved file.
7. Switch to a new empty workspace; select the saved runbook; `RUN` (enter the key when asked).
8. Copy the game fixture, delete one file from the copy, pick the copy as the game (top bar
   `GAME`); `RUN` again.
9. Start a recording and `DISCARD` > `DISCARD`.

Expected:
- 1: toasts `Give the workflow a title first.` and `Pick the game first (the top bar's GAME): the
  workflow replays on a game.`; nothing is recorded.
- 2: the panel shows `● REC`, the title and the game; the status chips gain `● REC 0 STEPS`,
  visible from every view and linking to RUNBOOKS.
- 3: each action that succeeds adds a step (the chip counts `1 STEPS`, `2 STEPS`); the panel
  lists them with their kind.
- 4: `PAUSED` / `REC PAUSED`; the survey is not added; after `CONTINUE` actions are added again.
- 5: the note is listed as a step marked `(you)`.
- 6: toast `Saved as the runbook <id>.`; the runbook is selected, badge `YOURS`. In the file: the
  game and the workspace are `{game}` and `{workspace}`; the PCK key is nowhere (not in the
  file, the log or JOBS): it is a secret input; no process id, job id or time is recorded; the
  cleanup plan's id is a `{step<N>_...}` reference.
- 7: the key is asked in a password field and not kept after a reload; the replay goes on by
  itself while every answer is the one recorded (`recorded: a replay stops here only if the
  answer differs` before a step runs), waits at the note (`YOUR TURN`), and ends `every step
  done`. The recorded extract replays with `onExisting: new` (no question).
- 8: the replay stops at the step whose answer differs: `DIFFERS: YOUR CALL`, each difference
  listed (`differs from the recording: ...`); `CONTINUE ANYWAY` goes on, `STOP` ends it.
- 9: the confirmation `DISCARD THE RECORDING`; nothing is saved; the `REC` chip is gone.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-GUIDE-01 | NOT RUN | version: ; added at 1.20.40 | | |
| SQC-GUIDE-02 | NOT RUN | added at 1.20.40 | | |
| SQC-GUIDE-03 | NOT RUN | added at 1.20.40 | | |
