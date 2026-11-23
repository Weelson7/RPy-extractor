# ViWo — to do

Two lists: the defects the SQC rebuild found (2026-11-23), and the capability gaps parked earlier.
Nothing here is started unless it says so. The owner decides what to take.

## A. SQC findings (2026-11-23)

Found by rewriting the whole SQC suite and running every check that needs neither eyes nor a
commercial game, on v1.36.0 plus search and APK (now v1.39.0 and v1.40.0). Each line
names the check that failed; the check's row in `sqc/` holds the exact output. Not fixed.

### A1. Safety rules broken
- [ ] **SQC-SAFE-10 — writes into a game ViWo already knows.** After extracting a game,
  `extract --workspace <game>\out` and `repack --out <game>\copy` both run. With a game path on
  the run, the guard compares only against that run's game, never `games.json`
  (`core/pipeline/guard.py` 32-40).
- [ ] **SQC-SAFE-06 — cleanup ignores the workspace lock.** `sanitize <ws> --apply` runs while
  another extraction holds `.extraction_metadata\lock` (a second `extract` is refused `busy`).
- [ ] **SQC-CLEAN-03 — a stale plan is applied.** A file changed after planning; apply still
  trashed two files "as duplicates of" it.
- [ ] **SQC-EXT-05 — the Ren'Py spare reader drops a hostile member silently.** With
  `--slot unarchive.rpa=unrpa,rpa-safe`, `../escape.txt` is dropped with no warning; the default
  reader says it.
- [ ] **SQC-SEC-08 / SQC-CLI-10 — two servers on one port.** A second `viwo serve --port N`
  starts while the first listens: `QuietServer` keeps `allow_reuse_address`, which on Windows
  lets another process bind a port in use (`viwo/api/server.py` 235-248).

### A2. Does not work
- [ ] **SQC-RT-16 — a user keystore cannot be used for APK signing.** `[options.android]
  keystore` / `key_alias` are refused as "secrets are not allowed in the ini" (the secret-word
  filter matches "key": `core/wiring/ini.py` 17, 143); `viwo repack` has no `--option` and
  `POST /api/repack` takes no options. The debug key is always used.
- [ ] **SQC-DEP-10 — the APK signer cannot be installed.** `viwo install uber-apk-signer`:
  `unknown dependency id(s)`; no backend declares the dependency (`plugins/android/sign.py` 15),
  so the startup installer skips it too, yet the "left UNSIGNED" note tells the user to run it.
- [ ] **SQC-RT-15 — a Defold encrypted edit fails its round trip.** `Verify game.arci: 1
  member(s) FAILED`; re-extracting the copy: `1 encrypted resource(s) not decrypted`.
- [ ] **SQC-MERGE-04 — files the merger trashed are stuck.** "Trash after build" moves the
  inputs into `.trash\merger\`, but `/api/status` shows `trashed {}`, RESTORE finds nothing and
  CLEAR TRASH is disabled (`core/curation/trash.py` 38-45 counts only groups and items).
- [ ] **SQC-GUIDE-04 — a runbook's "you do" step crashes without a terminal.** stdin from NUL:
  `viwo: internal: EOFError`, exit 1 (`viwo/cli_guides.py` 91-93: `isatty()` is true for NUL on
  Windows and EOFError is not caught).
- [ ] **SQC-DYN-09 — the CPU profiler samples about 5 times a second, not 1000.** Each round
  lists the whole system's threads (`viwo/os/_win_probe.py` 77, `threads_of`: 170 ms a call).

- [ ] **`viwo mod apply --after` leaves a half-applied copy.** When two mods write the same
  bytes it fails with `zz2 was made for another version` (wrong: it is the same version) only
  after copying the game and writing the first mod (`viwo/core/mods.py` around 222).
- [ ] **`viwo install` exits 0 when the tool asked for was refused** (`Installed: nothing`,
  `FAILED repak: ...`).
- [ ] **Guide JSON files with a UTF-8 BOM are refused** (`viwo/core/guides.py`); PowerShell 5.1's
  `Set-Content -Encoding utf8` writes one.
- [ ] **`[tools]` takes one plain path only**, so six tools cannot be pointed at from an ini:
  RenderDoc's Python, Unicorn, angr, unluac, unrpyc, AssetStudioMod (they need a command prefix
  or a worker folder).

### A3. Never-silent rule broken
- [ ] **`record` hides its real cause.** It answers `unavailable: audio capture needs soundcard`
  while `viwo slots` lists soundcard as found; the cause was a numpy import error.
- [ ] **SQC-RT-14 — packer notes never reach the console.** "left UNSIGNED", "signed with a
  debug key" and ".NET resource whose size changed: not written" are in `report.json` only; the
  console says `verified`.
- [ ] **SQC-RT-08 — no Overwatch reminder on repack.** Plan and build print none and
  `report.json` has `warnings: []` (doc 18.3 says every run carries it).
- [ ] **SQC-SAFE-07 — temp left after a killed run.** A 1.0 GB staging folder under
  `viwo-data\tmp\` stays after the next run and nothing mentions it.
- [ ] **SQC-DYN-03 — an empty trace is not said, and dump/trace/profile show no progress.** An
  8 s trace answered `events: 0` with no warning; the three jobs write no log line at all.

### A4. UI
- [ ] **SQC-UI-09 / SQC-DYN-11 — the job chip opens the wrong job.** The running job's chip
  opens JOBS on the job that was latest when the page loaded, with CANCEL JOB hidden
  (`views/jobs.js` 47 picks the latest only when nothing is selected).
- [ ] **SQC-UI-02 — at 1024 px.** SETTINGS scrolls sideways; the arm switch in the 64 px rail
  clips its labels (`DYNAMI`, `PATCHIN`).
- [ ] **SQC-UI-16 — the home pages are out of date.** DYNAMIC HOME lists hooks and network as
  PLANNED though `viwo hook` and mitmproxy ship; PATCHING HOME has no isolation row
  (`views/home.js` 28-34).

### A4b. Isolation, as seen on v1.36.0 (check against the isolation work committed since)
- [ ] RUNTIME > ISOLATION PATCHER START sent no tier, memory, CPUs or headless and always asked
  for a snapshot, so with VirtualBox installed it would start a VirtualBox VM, 4096 MB, with a
  window (`views/runtime.js` 106; `core/isolation/session.py` 56-58 picks the first ready tier).
- [ ] The journal was not reconciled after `rollback`: an entry survived `stop` and the next
  session's `undo` reported `restored: 2, edits: 2`, one from the old session.
- [ ] The one-shot `viwo isolate EXE` printed `Isolation session is up; viwo isolate stop ...
  ends it` though it closes the guest by itself (`session.py` 94).

### A5. Docs and release
- [ ] `docs/contract/18-round-trip.md` 192 names the report `<set>.report.json`; the file is
  `<name>.patch.report.json`.
- [ ] `docs/contract/19-guides.md` 141-143 lists the recorded routes without `/api/search`
  (`viwo/api/recording.py` 26 records it).
- [ ] Doc 11.7 says the profiler samples "about every millisecond"; it does not (SQC-DYN-09).
- [ ] **SQC-REL-04 — `docs/release-notes.md` still says 1.6.0**; `viwo info` prints no version.
- [ ] Doc 03 line 15 on `--carve all` does not match `core/pipeline/carving.py` 47-55.

### A6. Smaller, seen on the way (no failing check of their own)
- [ ] Real repak on an unreadable, unencrypted pak is reported as `needs_key`, and the message
  starts mid-word (`agic of 0x0 instead of ...`).
- [ ] A Wolf RPG keyed archive with no or a wrong key reads "not a Wolf RPG / DXArchive file"
  instead of `needs_key` (`plugins/wolfrpg/wolf.py` 61).
- [ ] The fake GodotPckTool and repak of `tests/test_godot.py` / `tests/test_unreal.py` fail on
  the packers' arguments (`'--output' is not in list`).
- [ ] Console: a trailing `Time: 1 s: ` with nothing after it; a refused repack target still
  prints `Copying the game to <target>` first; a line break before `; used ffmpeg-decode`; the
  slots VERSION column shows raw probe output for `[tools]`-located tools; XP and VX Ace runs warn
  `rpgmv-builtin exported nothing`.

### A7. The SQC rebuild itself
- [ ] Wording seen on the way: attach-off says `runtime capture is off` where dump says `the
  dynamic arm is off`; attach asks `confirm before capturing`; `Collected 4100 file(s)` has no
  thousands separator; the `viwo workbook` table misaligns on the mitmproxy id; an `asm: nop`
  over a 10-byte `mov` shows only `nop` in the new disassembly.
- [ ] `22-isolation.md` covers v1.36.0 only; revise for the isolation work committed since.
- [ ] `Test-games/` holds only Freedoom and Chocolate Doom; Burning Snow and the Godot "MAD
  game" are gone (no recorded source), so the checks that need them are NOT RUN.

## B. Still to write
- On Linux a recorded pid of 0 counts as alive, so a gone QEMU session answers `busy` instead of
  "exited" (`core/isolation/qemu.py`, `reattach`; `tests/test_isolation_tiers.py` fails there).

## C. Capability gaps parked earlier (2026-11-19)

### "Find the thing I want to change"
- **[File-high] "Change it in the app, then show me what changed."** Snapshot files + registry
  (optionally memory), the user flips a setting in the running app, ViWo diffs and points at the
  file/key/offset that holds it. `viwo diff` only compares two static game versions, not an action.

### "Patch it and keep it working"
- **[File-medium] Intent -> location last mile.** Tie a user's words ("the connection limit") to
  the actual constant/instruction via string-xref (the analysis arm) feeding `patch.sig`. The
  machinery exists (`patch.bytes`/`patch.sig`/disasm); the glue from a name to the immediate is
  manual (the FDM last step). Analysis-heavy.
- **[File-medium] Patch portability and re-apply after update.** Export a patch as an AOB-signature
  recipe; when the app updates, re-locate by signature and re-apply, or warn that it moved.
  `signature()` exists but there is no user flow or update watch.

### "Reach more targets"
- Mobile: decided 2026-11-23, APK support yes, no mobile runtime; built at 1.40.0. Open inside it:
  no dex decompiler is pinned; no Android IL2CPP analysis target.

### "Understand / trust what happened"
- **[Maybe] A user-facing per-run report.** "Here's what I found, what is editable vs one-way,
  what is patchable, what hit a wall." Partly covered by `survey` + the ASSETS plan + run records,
  but not as one readable summary.

### Not gaps
Sharing patches and community scripts tie to the **indexes repo, which is owner/GitHub-blocked**
-> **[Skip]** until it exists.
