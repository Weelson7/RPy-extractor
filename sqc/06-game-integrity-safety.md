# 06 Game integrity and data safety

Area code `SAFE`. These are engineering properties (how the features work), not policy: the
game folder is copied from and never written to; only folders carrying the marker
`.viwo-workspace` are ever cleared; names from archives cannot escape the workspace.

Hash helper (PowerShell), run before and after each check:
```powershell
function Snap($p) { Get-ChildItem $p -Recurse -File | Get-FileHash -Algorithm SHA256 | Sort-Object Path | ForEach-Object { "$($_.Path)=$($_.Hash)" } }
$before = Snap C:\sqc\renpy\game
# ... run the check ...
Compare-Object $before (Snap C:\sqc\renpy\game)      # must print nothing
```

## SQC-SAFE-01 (P0) Game folder byte-identical after extraction, survey, repack and capture

Steps: snapshot `C:\sqc\renpy\game`; run SQC-EXT-04, SQC-SUR-03 (on that folder), SQC-RT-02
(game copy of that folder) and SQC-CAP-02; snapshot again.

Expected: `Compare-Object` prints nothing each time; the folder has no new files (no
`.viwo-workspace`, no `.extraction_metadata`, no `.trash`, no temp files); file timestamps are
unchanged (`Get-ChildItem -Recurse | Select LastWriteTime` identical).

## SQC-SAFE-02 (P0) Workspace or temp inside the game folder is refused

Steps:
1. `viwo extract C:\sqc\renpy\game --workspace C:\sqc\renpy\game\out`
2. `viwo extract C:\sqc\renpy\game --workspace C:\sqc\renpy`
3. UI: top bar `WORKSPACE > SWITCH`, enter `C:\sqc\renpy\game`, `OPEN`, then extract that game.

Expected: 1 and 2: `viwo: refused: ...inside the game folder...`, exit 3, nothing created. 3:
the error box `REFUSED FOR SAFETY` with `NEXT ViWo only writes into an empty folder or one it
created, never into a game folder. Pick another folder.`

## SQC-SAFE-03 (P0) Hostile archive names are contained

Steps: `viwo extract C:\sqc\hostile-names\game --workspace C:\sqc\_ws\hostile --on-existing replace`,
then `Get-ChildItem C:\sqc\_ws\hostile -Recurse -Force` and `Get-ChildItem C:\sqc -Filter *escape* -Recurse`,
`Test-Path C:\drive-abs.txt`, `Test-Path C:\Windows\win.ini` content unchanged.

Expected: only `txt\normal.txt`, `txt\tar-normal.txt`, and the unicode file (renamed to a valid
name under `txt\`) exist; every traversal, absolute, drive-letter, device (`aux.txt`, `CON`),
trailing dot/space and ADS (`stream.txt:hidden`) member is skipped with a warning naming it; the
symlink and hardlink members are not created; nothing is written outside the workspace. The run
succeeds with warnings (exit 0).

## SQC-SAFE-04 (P0) Only marked folders are cleared

Steps:
1. Create `C:\sqc\_ws\mine` with a file `keep.txt`. `viwo extract C:\sqc\zip-basic\game --workspace C:\sqc\_ws\mine --on-existing replace`
2. UI: `WORKSPACE > SWITCH` to `C:\sqc\_ws\mine`; `WORKSPACE > CLEAR TRASH`.

Expected: 1: `refused: C:\sqc\_ws\mine is not empty and is not a ViWo workspace`, `keep.txt`
untouched. 2: the view explains the folder is not a ViWo workspace (`NOT A VIWO WORKSPACE` state
or the same refusal), nothing is deleted.

## SQC-SAFE-05 (P1) Zip bomb is bounded

Preconditions: `python sqc\fixtures\build_fixtures.py --out C:\sqc --only zip-bomb`.

Steps: extract `C:\sqc\zip-bomb\game` while watching memory (Task Manager) and free disk.

Expected: memory of `python.exe` stays under 300 MB; the member is streamed; either the 1 GiB file
lands in `bin\zeros.bin` (slow but bounded) or the size guard stops it with a warning; the run
never crashes. Cleanup: delete the workspace.

## SQC-SAFE-06 (P1) Concurrent job on the same workspace is `busy`

Steps: start a long extraction into `C:\sqc\_ws\busy` from the UI; while it runs, from the CLI
`viwo sanitize C:\sqc\_ws\busy`.

Expected: `viwo: busy: ...`, exit 1; in the UI, CLEANUP > SCAN on that workspace shows the
error box `WORKSPACE BUSY` with the link `Open JOBS →`.

## SQC-SAFE-07 (P1) Interrupted run leaves a consistent workspace

Steps: start an extraction from the CLI, kill the terminal (close the window) mid-run; then run
again with `--on-existing replace`.

Expected: the second run works; the staging leftovers under `viwo-data\tmp\viwo-*` are removed at
the next start (or listed as a note); the game folder is unchanged.

## SQC-SAFE-08 (P1) Secrets never on disk

Steps: run SQC-EXT-08 step 4 (AES key via `--option`), then
`Select-String -Path C:\sqc\_ws\ue4\.extraction_metadata\runs\*.json, viwo-data\logs\*.log -Pattern <key hex>`.

Expected: no match anywhere; the record shows `"aes_key": "<secret>"`.

## SQC-SAFE-09 (P0) Memory ceiling: ViWo's own process and its child tools

Steps 1-2 need no game (smoke subset); 3-4 need the real games named and are run from a worktree
at a committed version (`docs/HANDOFF.md`), with the ceiling ON.

Steps:
1. Shipped `startup.ini`: `viwo --verbose info`; then `viwo serve --no-browser` and read the
   first lines of the terminal and of the activity console.
2. A copy of the ini with `[startup] memory_limit = 0`: `viwo --ini <copy> --verbose info`.
3. Unity IL2CPP (Schedule I): `viwo extract <game> --workspace W`, watching the machine's memory.
4. Cyberpunk 2077 (the `ctf.json` subset): `viwo extract <game> --workspace W` with WolvenKit
   installed, watching the WolvenKit processes' memory.

Expected:
- 1: `memory ceiling for ViWo's own process: <n> GB (50 % of the machine)` on stderr (`[CLI]`)
  and as a `[SERVER]` line at start. Where the OS layer cannot set it the line reads `no memory
  ceiling: <why>`, without `--verbose` too (never silent when unprotected).
- 2: `memory ceiling off ([startup] memory_limit = 0)`.
- 3: the machine stays up and ViWo's process stays under the ceiling. A Unity script whose
  rebuilt layout does not fit its objects is counted and said once: `<n> script(s) have a rebuilt
  layout that does not fit their objects (it asked for the machine's memory): their
  MonoBehaviours are listed without fields, every other script keeps its fields`. Those
  MonoBehaviours are in the export without fields; MonoBehaviours of the other scripts still
  carry theirs (open one of each as JSON). The run ends with its assets out, not `internal`.
- 4: no WolvenKit process passes its cap (4 GB each); as many run at once as fit in ViWo's share
  of the machine (4 on a 32 GB machine); the decode says how many parts and how many at a time.
  A WolvenKit that reaches its cap fails by itself: that part is one counted failure in the
  slot's warning, the other parts and the run go on, the machine stays up. A cap that could not
  be set is said (`no memory cap on this tool: <why>`).

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-SAFE-01 | | version: | | |
| SQC-SAFE-02 | | | | |
| SQC-SAFE-03 | | | | |
| SQC-SAFE-04 | | | | |
| SQC-SAFE-05 | | | | |
| SQC-SAFE-06 | | | | |
| SQC-SAFE-07 | | | | |
| SQC-SAFE-08 | | | | |
| SQC-SAFE-09 | NOT RUN | added at 1.20.40 | | |
