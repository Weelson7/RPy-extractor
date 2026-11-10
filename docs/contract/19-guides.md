# 19. Guides: workbooks, runbooks, workflows

The owner's UI capabilities (doc 16.4). All are OS-agnostic: nothing may assume Windows or
Linux. They follow one principle: **what a child tool can do natively, it does natively, in its
own window**. ViWo teaches the child's interface, sequences its own actions around it and
records them; it does not reimplement, embed or drive the child.

| # | Capability | State |
|---|------------|-------|
| 19.1 | Workbooks: a guided how-to for a child tool's own interface | shipped 1.18.0 |
| 19.2 | Runbooks: named, editable, saved sequences of steps | shipped 1.19.0 |
| 19.3 | Workflows: record, pause, continue; replay that stops only where the output differs | shipped 1.20.0 |
| 19.4 | Embedded child GUIs inside ViWo's web surface | dropped (owner): native tools stay native |

## 19.1 Workbooks

A workbook explains, step by step, how to do one thing in a child tool's own interface: "patch a
byte in x64dbg", "find the code that uses a string in Ghidra". It is teaching text, never
automation: ViWo does not click or type in the tool, and draws nothing over its window. A
workbook is shown beside the tool, which stays in its own window.

**Files.** One JSON object per file, `*.json`:

```text
id           [a-z0-9-]+, unique; the file name is free
title        what it teaches, as a task ("Patch a byte, live and into a file")
tool         the tool's dependency id in viwo/data/tools.json (x64dbg, ghidra, cheatengine), or
             any name for a tool ViWo does not pin (an unmanaged tool, doc 16.3)
written_for  the tool version the steps were checked against
opens        optional: the slot whose handoff opens the tool pre-loaded (handoff.native,
             attach.debug, attach.memory); the UI offers it as the first move
summary      one or two sentences
steps        one or more {title, text, keys?: [shortcut...], expect?: what you should see}
```

**Where they come from.** Shipped: `viwo/data/workbooks/`. The user's own:
`<data>/workbooks/` (`viwo-data/workbooks/` beside `tmp`), read at every request; one there with
a shipped id replaces the shipped one and is marked `yours`. A future source is the indexes
repository (`docs/indexes.md`).

**Never silent.** A file that is not valid JSON, misses a field, has a bad id or no steps, or
names a slot that does not exist is skipped and named in `problems`. A workbook whose
`written_for` differs from the pinned version of its tool carries `stale` (the pinned version
beside it): the steps may differ, and the UI and CLI say so. The shipped workbooks are written for
the current pins; a test fails when a pin moves, so they are checked again.

**Entry points.** `viwo workbook` lists them; `viwo workbook ID` prints the steps.
`GET /api/workbooks` -> `{workbooks: [{id, title, tool, writtenFor, pinned, stale, opens,
summary, steps, source}], problems}` (`source`: `viwo` or `yours`; `pinned`: the tool's version
in `tools.json`, empty for an unpinned tool). UI: WORKBOOKS in the global strip (the list by
tool, one step at a time with PREVIOUS and NEXT, the step reached remembered per workbook, the
view that opens the tool); a HOW TO button beside Continue in Ghidra (ANALYSIS), beside the
x64dbg and Cheat Engine buttons (RUNTIME) and on the target of CAPTURE (RenderDoc, whose frames
the user opens in qrenderdoc: no handoff opens it) opens the tool's workbooks.

Code: `viwo/core/guides.py` (the files), `viwo/core/workbooks.py`, `viwo/data/workbooks/`,
`viwo/api/handlers_system.py`, `viwo/cli_guides.py`, `viwo/web/js/views/workbooks.js`.

## 19.2 Runbooks

A runbook is a named sequence of steps a user runs, tweaks and saves: ViWo's own actions (a
survey, an extraction, an analysis, a patch set: any job kind) and steps the user does, in a
child tool when a workbook says how. Shipped defaults plus the user's own.

**Files.** One JSON object per file, in the same two places as workbooks (`viwo/data/runbooks/`,
`<data>/runbooks/`; one of the user's with a shipped id replaces it, marked `yours`):

```text
id       [a-z0-9-]+          title, summary   texts
inputs   optional [{name, label, default?, secret?}]   name [a-z][a-z0-9_]*, not game or
                                      workspace; a secret one has no default and is never kept
steps    one or more of
  {title, do: KIND, with: {params}, expect?}   a ViWo action: KIND is a job kind of POST
                                      /api/jobs (doc 12.5), params its parameters; expect: what
                                      a recording saw (19.3)
  {title, text, workbook?: ID}        a step the user does, then confirms; the workbook (19.1)
                                      says how in the child tool
```

In a string anywhere inside `with`, `{name}` takes the run's value: `{game}` the game folder,
`{workspace}` the active workspace, `{<input>}` the input's value (its default when none is
given); a parameter that is one `{name}` alone whose value is `true` or `false` becomes that
boolean (an input is text). A file that is not valid (a wrong type anywhere included), an unknown
job kind, an unknown `{name}` or an unknown workbook is named in `problems` and skipped; so is a
second file with an id already read (never silently).

**Running.** One step at a time, each in the active workspace: an action step goes through the
same handler as `POST /api/jobs` and comes back with its job's result or failure; a value the
step needs that is empty is refused before anything runs (`invalid_request`, naming it). A
failed step stops the run where it is; the run continues from any step (the UI's RUN FROM HERE,
`--from N`). A step the user does pauses the run until it is confirmed (the UI's DONE,
CONTINUE; on the command line Enter, and without a terminal the run stops there and says
`--from N+1`, with `--workspace` when an extract step switched the active workspace). Every
action goes through its own checks and feature switches. A runbook's parameters can carry an
action's own answers (capture's `confirmed`, cleanup's `op: apply`, extract's `onExisting:
replace`): they are written in the runbook by its author, and each step's row shows its
parameters before it runs. Each action's answer (a plan, a report) is shown with its step (the
UI's ANSWER, the CLI's stderr and `done`), so the step you do next can read it.

**Saving.** `POST /api/runbooks/save {runbook}` validates and writes the user's file that holds
that id, else `<data>/runbooks/<id>.json` (through `safe_member` and `inside`); saving a shipped
id keeps the user's tweaked copy, which replaces the shipped one; `POST /api/runbooks/delete
{id}` removes only the user's file holding that id (a shipped runbook comes back when its
tweaked copy is deleted).

**Entry points.** `viwo runbook` lists them, `viwo runbook ID` prints the steps, `viwo runbook
ID --run --workspace W [--set name=value]... [--from N]` runs them (a `--set` name the runbook
does not have is said; a `--from` outside its steps is refused). API: `GET /api/runbooks` ->
`{runbooks: [{id, title, summary, inputs, steps, source}], problems, kinds}`; `POST
/api/runbooks/step {id, step, values}` runs one action step (step counted from 0) -> the job's
answer plus `step`. UI: RUNBOOKS in the global strip: the list; a runbook's inputs (the game
from the top bar, the active workspace), its steps with their state, RUN, RUN FROM HERE, DONE,
CONTINUE, STOP, each step's job linked to JOBS; EDIT shows the runbook as JSON to change and
save (a shipped one is saved as the user's copy), DELETE removes the user's copy.

Code: `viwo/core/guides.py` (the files of 19.1 and 19.2), `viwo/core/runbooks.py`,
`viwo/data/runbooks/`, `viwo/api/handlers_runbooks.py`, `viwo/cli_guides.py`,
`viwo/web/js/views/runbooks.js`.

## 19.3 Workflows

ViWo records what the user does, with pause and continue; the recording is saved as a runbook
whose action steps carry what they answered. On replay, a step whose answer is the same as the
recording proceeds to the next by itself; a step whose answer differs stops, says what changed
and asks whether to continue. Meant for repeatable patching across game updates.

**Recording.** One recording at a time, held by the server, so the actions of every view are
caught: started with a title and the game, which is required (`POST /api/recording {action:
start, title, game}`),
then `pause`, `continue`, `note {title, text}` (adds a step you do: what you did in a child
tool), `stop` (saves) or `discard`; `GET /api/recording` -> `{recording: {title, game, paused,
steps} | null}`. While it runs and is not paused, every action route that answers success adds
a step: extract, survey, repack, patch, mod, capture, analysis run, cleanup plan/apply/undo and
the runtime kinds (dump, trace, hook, profile, agent, record), as `{title, do, with, expect}` with the
same parameters the route got. Whether an action is recorded is decided when it starts (a
pause or stop meanwhile does not drop or add it); `stop` is refused (`busy`) while a recorded
action is still running. A failed action is not added (the recording replays what worked); a
step that names another game folder than the recording's is kept and said (`warnings`); the
top bar's REC chip and the RUNBOOKS recording panel show every step it holds.

**Portable parameters.** In the recorded parameters the game folder becomes `{game}` and the
active workspace `{workspace}`, only where a path ends (`Foobar` is not `{game}bar`); an
extract recorded with `onExisting` ask is saved with `new` (a replay extracts beside a used
workspace and never replaces one unless the user chose it). An id or token an earlier step
answered (a cleanup plan's `planId`, an apply's `undoToken`) becomes `{step<N>_<key>}`: a replay
sends the one its own step N answered (runners carry every action's top-level answer values
forward; a step run on its own refuses the missing value, named). A process id is never
recorded: the image name stays, else `{pid}` becomes an input asked at each run. A secret (a
plugin option its plugin declares of kind `secret`, as run records mask them, doc 3; every
option of a plugin this runtime does not know) is never written: it becomes a secret input
`{secret_<n>}` of the workflow (`inputs: [{name, label, secret: true}]`), asked for at each run
(the CLI asks at a terminal without echo); the UI does not keep a secret input's value.

**Expectations.** `expect: {digest, facts}` on an action step: the SHA-256 of the answer with
its volatile parts dropped (keys ending in Id or Token, times, stamps, durations, seconds, event
counts, `success`, `jobId`, a process id, a survey's numbered report path, a run record, log
lines, a mod's `made` and `viwo` version, the record `context` with ViWo's version) and the game
and workspace paths replaced by their `{name}`. Capture and the runtime kinds (dump, trace,
hook, profile, agent, record) carry no expectation: what a running game does differs on every run,
so they proceed; `facts` are its scalar values (dotted
keys, three levels, a list as its length, at most 60) to name what changed. On replay
(`/api/runbooks/step`, `viwo runbook --run`) a step with `expect` answers `differs: [what
changed]`, empty when the digest is the same. The UI then pauses on that step (YOUR CALL,
CONTINUE or STOP); the CLI asks at a terminal and otherwise stops with `--from N+1`.

**Saving.** `stop` writes the recording as the user's runbook (doc 19.2; the id from the title,
`-2`, `-3`... when taken); an empty recording is refused, named. The saved workflow is a runbook
like any other: edit it, add steps you do, run it from any step.

Code: `viwo/core/workflows.py` (expectations, portable parameters), `viwo/api/recording.py`
(the recorder and its route wrapper), `viwo/web/js/views/recording.js`.

## 19.4 Embedded child GUIs (dropped)

Dropped by the owner (2026-11-05): the child GUIs (x64dbg, Ghidra, Cheat Engine, qrenderdoc)
stay native, in their own windows, started by ViWo as tracked children (doc 8.3a). ViWo does
not embed, stream or drive their windows; workbooks (19.1) teach them beside the tool, and what
the user does inside them is a step the user records as a note (19.3). The number stays so the
section numbers keep their meaning.
