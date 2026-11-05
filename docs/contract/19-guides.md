# 19. Guides: workbooks, runbooks, workflows, embedded child GUIs

The owner's UI capabilities (doc 16.4), in the order they are built. All are OS-agnostic:
nothing may assume Windows or Linux. They follow one principle: **what a child tool can do
natively, it does natively**. ViWo teaches, sequences and records the child's own interface; it
does not reimplement what the child does.

| # | Capability | State |
|---|------------|-------|
| 19.1 | Workbooks: a guided how-to for a child tool's own interface | shipped 1.18.0 |
| 19.2 | Runbooks: named, editable, saved sequences of steps | open |
| 19.3 | Workflows: record, pause, continue; replay that stops only where the output differs | open |
| 19.4 | Embedded child GUIs inside ViWo's web surface, with faithful input forwarding | open |

## 19.1 Workbooks

A workbook explains, step by step, how to do one thing in a child tool's own interface: "patch a
byte in x64dbg", "find the code that uses a string in Ghidra". It is teaching text, never
automation: ViWo does not click or type in the tool. Overlays drawn over the tool's own window
need the embedded GUIs (19.4); until then a workbook is shown beside the tool.

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
view that opens the tool); a HOW TO button beside Continue in Ghidra (ANALYSIS) and beside the
x64dbg and Cheat Engine buttons (RUNTIME) opens the tool's workbooks.

Code: `viwo/core/workbooks.py`, `viwo/data/workbooks/`, `viwo/api/handlers_system.py`,
`viwo/web/js/views/workbooks.js`.

## 19.2 Runbooks (open)

A named sequence of steps a user runs, tweaks and saves: ViWo's own actions (a survey, an
extraction, an analysis, a patch set) and child steps (a workbook step the user does in the
tool). Shipped defaults plus the user's own, saved beside the user's workbooks.

## 19.3 Workflows (open)

ViWo records what the user does, with pause and continue. On replay, a step whose output is
identical to the recording proceeds to the next by itself; a step whose output differs stops
and asks whether to continue. Meant for repeatable patching across game updates.

## 19.4 Embedded child GUIs (open)

The child GUIs (x64dbg, Ghidra, Cheat Engine, qrenderdoc) run inside ViWo's web surface instead
of a separate OS window, each resizable and fullscreen, with the cursor, mouse and keyboard
forwarded faithfully to the native window: the matching mechanism per OS (X11 or Wayland on
Linux, the window system on Windows), behind the OS layer. Comes after workflows.
