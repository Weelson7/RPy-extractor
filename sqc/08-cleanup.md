# 08 Cleanup (sanitizer phase 1)

Area code `CLEAN`. Fixture: `dirty-workspace` (`C:\sqc\dirty-workspace\ws`, already a marked
workspace with: an empty file, `Thumbs.db`, a `.import` junk file, a PNG named `.jpg`, an exact
duplicate, a truncated PNG). Rules: `core.zero_byte`, `core.junk`, `core.extension`,
`core.duplicate` (trash or rename, lossless, undoable) and `core.health` (report only).

## SQC-CLEAN-01 (P0) Scan, findings by rule, apply selected, undo (UI)

Steps:
1. `WORKSPACE > SWITCH` to `C:\sqc\dirty-workspace\ws`.
2. `08 CLEANUP > 08.A SCAN`: recipe `Safe cleanup` (badges `LOSSLESS`, `NOTHING IS DELETED`),
   click `SCAN`.
3. In `08.B FINDINGS` untick the duplicate; click `APPLY SELECTED`.
4. `08.C LAST CLEANUP > UNDO THIS CLEANUP`.

Expected:
- 2: progress `READING + HASHING WORKSPACE FILES…`; findings grouped `EMPTY FILES (1)`, `ENGINE /
  OS JUNK (2)`, `WRONG EXTENSION (1, rename .jpg -> .png)`, `EXACT DUPLICATES (1)`, `HEALTH (1,
  REPORT ONLY: truncated PNG)`; stats `SCANNED n`, `SELECTED 5`; `WHAT EACH RULE DOES` explains
  each rule.
- 3: result `APPLIED 4` (`TO TRASH 3`, `RENAMED 1`), the duplicate stays; the trashed files are in
  `.trash\items\` (or `.trash\sanitizer\`), the renamed file is `*.png`; `provenance.jsonl` has
  the rename; the panel shows `UNDO AVAILABLE` with the token.
- 4: every file is back with its original name; a second scan finds the same 5 findings.

## SQC-CLEAN-02 (P0) CLI plan, apply, undo

Steps:
1. `viwo sanitize C:\sqc\dirty-workspace\ws`
2. `viwo sanitize C:\sqc\dirty-workspace\ws --apply`
3. `viwo sanitize C:\sqc\dirty-workspace\ws --undo <token printed by step 2>`
4. `viwo --json sanitize C:\sqc\dirty-workspace\ws`

Expected: 1: the plan with one line per finding (`rule`, path, message, action), `planId`, and
the note that nothing was changed. 2: `applied 5` (all safe actions, duplicate included),
`undo token: <token>`; the journal is under `<ws>\.sanitizer\`. 3: `restored 5`;
files back. 4: envelope with `data.findings` (list) and `data.planId`.

## SQC-CLEAN-03 (P1) Applying a stale plan is refused

Steps: `viwo sanitize <ws>` (plan A); change a file (`Add-Content <ws>\txt\x.txt "edit"`); apply
plan A's id via the API or `--apply` after a new scan with a different plan id.

Expected: the UI's `APPLY SELECTED` after a changed workspace reports `plan is stale: scan again`
(error box `CHECK YOUR INPUT`), nothing is moved; `SCAN AGAIN` then works.

## SQC-CLEAN-04 (P1) Health findings are never applied

Steps: scan; tick everything; apply.

Expected: the truncated PNG finding is listed under `HEALTH` with `REPORT ONLY` and has no
checkbox; it is not moved or renamed.

## SQC-CLEAN-05 (P1) Clean workspace and empty workspace

Steps: scan a freshly extracted `zip-basic` workspace; scan an empty marked workspace.

Expected: `WORKSPACE IS CLEAN` (0 findings, `APPLY SELECTED` disabled); `WORKSPACE EMPTY` with
`GO TO 01 EXTRACT`.

## SQC-CLEAN-06 (P1) Undo twice and undo of a partially restored journal

Steps: apply; delete one trashed file by hand from `.trash\`; undo.

Expected: undo restores what it can, reports `1 could not be restored (missing in trash)` as a
warning, does not fail entirely; a second undo of the same token reports `nothing to undo`.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-CLEAN-01 | | version: | | |
| SQC-CLEAN-02 | | | | |
| SQC-CLEAN-03 | | | | |
| SQC-CLEAN-04 | | | | |
| SQC-CLEAN-05 | | | | |
| SQC-CLEAN-06 | | | | |
