# 01 Install and first run (startup installer, landing screen)

Area code `INST`. Preconditions for the whole file: a clean checkout, no `third_party\` and no
`viwo-data\` next to `startup.ini` (delete both), internet access, browser closed.

## SQC-INST-01 (P0) Fresh install from a checkout

Preconditions: Python 3.11+ on PATH as `py` (Windows) or `python3` (Linux). No venv yet.

Steps:
1. `py -3.13 -m venv .venv; .venv\Scripts\Activate.ps1`
2. `pip install -e ".[unity,sevenzip,renpy,lz4,dev]"`
3. `viwo`
4. `viwo --json info`

Expected:
- Step 2 ends with `Successfully installed ... viwo-<version>` and no error.
- Step 3 prints the guide: lines starting with `viwo serve`, `viwo survey`, `viwo extract`,
  `viwo slots`, `viwo install --all`, then the philosophy paragraph ("A community tool for
  everyone who wants to look inside a game..."). Exit code 0.
- Step 4 prints a JSON envelope with `"ok": true`, `data.os` = `windows` or `linux`,
  `data.plugins` listing 13 ids (bethesda, doom, electron, generic, godot, kirikiri, overwatch,
  quickbms, renpy, rpgmaker, source, unity, unreal).

Cleanup: none.

## SQC-INST-02 (P0) `viwo slots` before any tool is installed

Steps:
1. `viwo slots`

Expected:
- Two tables. `SLOT / MAIN / SPARE`: `unarchive.zip py-zipfile sevenzip-cli`, `unarchive.rpa
  rpa-safe unrpa`, `export.unity unitypy`, `carve.signatures signature-carver`; slots whose tool
  is missing show `-- unbound --` (for example `unarchive.pck`, `unarchive.upak`, `unarchive.bms`,
  `capture.gpu`, `export.overwatch`).
- `DEPENDENCY / STATUS / WHERE`: `unitypy found`, `py7zr found`, `unrpa found`, `lz4 found`;
  tools not on PATH show `missing` with a one-line hint.
- Exit code 0.

## SQC-INST-03 (P1) `viwo config check` on the shipped ini files

Steps:
1. `viwo config check startup.ini distros\*.ini` (PowerShell expands the glob; on Linux use
   `distros/*.ini`)

Expected: `OK: <13 paths>` and exit code 0. Any problem line is a FAIL.

## SQC-INST-04 (P0) First `viwo serve`: landing screen driven by the real preflight

Preconditions: no `third_party\` folder. A browser that will open automatically.

Steps:
1. `viwo serve`
2. Watch the browser tab that opens. Start a stopwatch when the page appears.
3. Keep the terminal visible.

Expected:
- Terminal: `ViWo // Vidya Wormhole -> http://127.0.0.1:8081/` and `Workspace: <path>`.
- The page is covered by a full-screen landing: big `VIWO // VIDYA WORMHOLE` logo, a stage line
  (`STARTING`, then `CHECKING TOOLS`, then `INSTALLING`, then `READY`), a bar, a log box, a
  summary line, and the footer `LOCAL-FIRST // 127.0.0.1 // THE GAME FOLDER IS NEVER WRITTEN`.
- Log box: one line per check as it arrives, in the form `Checking <tool> (i/N): found <version>`
  or `Checking <tool> (i/N): missing`; N equals the number of DEPENDENCY rows of `viwo slots`.
- During the checks the bar is determinate and the counter at the right reads `i / N`.
- Then `Installing missing tools (i/M): <tool>` lines, each followed by `Downloading
  <file>, KB: x / y` lines; the bar advances inside each tool's slice and the counter shows
  `<file> · x / y KB`.
- Each installed tool ends with `Installed <tool>`.
- Summary line at the end: `<ready>/<total> tools ready, <k> installed.`; `ready` equals the
  found count plus `k`.
- The landing stays at least 1.2 s even on a fast machine, then fades out; 01 EXTRACT is
  underneath with the top bar `FORMATS a/b READY` chip updated to the new count without a reload.
- 04 JOBS shows one job of kind `STARTUP CHECK`, state `SUCCEEDED`.

Cleanup: none (keep `third_party\` for 02).

## SQC-INST-05 (P0) Tools landed in `third_party\` and nowhere else

Preconditions: SQC-INST-04 passed.

Steps:
1. `Get-ChildItem third_party`
2. `Get-ChildItem third_party -Recurse -Filter *.exe | Select-Object -First 30 FullName`
3. `viwo slots`

Expected:
- Step 1 lists exactly the ids that were missing in SQC-INST-02 and are pinned for this OS, from:
  `assetstudiomod datatool dotnet ffmpeg ffprobe gdre godotpcktool quickbms renderdoccmd repak
  retoc sevenzip unrar vgmstream python`. (`rdpython` has no folder: it lives in
  `renderdoccmd\`; `datatool` is Windows only; `python\` appears only if a Python package was
  missing.) No `.tmp` or `.<id>-xxxx` leftovers.
- Step 2: `third_party\repak\...\repak.exe`, `third_party\sevenzip\...\7z.exe`,
  `third_party\unrar\UnRAR.exe`, `third_party\quickbms\quickbms.exe`,
  `third_party\renderdoccmd\RenderDoc_1.47_64\renderdoccmd.exe` and `qrenderdoc.exe`,
  `third_party\dotnet\dotnet.exe`, `third_party\datatool\DataTool.exe`.
- Nothing was written to `C:\Program Files`, `%LOCALAPPDATA%` or the user profile by ViWo
  (compare timestamps if in doubt).
- Step 3: every pinned dependency is `found` with a `third_party\...` path; `assetstudiomod`
  shows the dll path; `rdpython` shows `...\qrenderdoc.exe`. All of `unarchive.pck`,
  `unarchive.upak`, `unarchive.utoc`, `unarchive.rar`, `unarchive.bms`, `capture.gpu`,
  `export.overwatch` (Windows) are bound.
- `third_party\quickbms\scripts\` exists and is empty.

## SQC-INST-06 (P0) Landing is skipped on reload within the same tab

Steps:
1. In the tab of SQC-INST-04, press F5.
2. Open a new tab on `http://127.0.0.1:8081/`.

Expected:
- Step 1: no landing; the app appears directly on the last view.
- Step 2: the landing runs again (new tab = new session storage) and now shows every tool as
  `found`, summary `<total>/<total> tools ready, 0 installed.`, held about 1.2 s.

## SQC-INST-07 (P1) Landing with reduced motion

Preconditions: OS "reduce motion" on (Windows: Animation effects off).

Steps:
1. New tab on the app.

Expected: the landing appears and disappears without the fade and without the animated scan on
the bar; the bar still fills (determinate) and the lines still appear; the summary and hold are
unchanged.

## SQC-INST-08 (P1) Landing when the preflight fails

Preconditions: block outbound HTTPS for `python.exe` in the firewall, or unplug the network;
delete `third_party\repak`.

Steps:
1. New tab on the app.

Expected: the check lines run; `Installing missing tools (1/1): repak`; then a warn line
`Could not install repak: ...`; summary `<n>/<total> tools ready, 0 installed, 1 could not be
installed (see 05 SYSTEM).` The landing hands off normally; the app works; 05 SYSTEM shows
`repak` with an INSTALL button.

Cleanup: restore the network; 05 SYSTEM > INSTALL on repak.

## SQC-INST-09 (P1) `auto_install = off`

Steps:
1. In `startup.ini` set `auto_install = off`; delete `third_party\vgmstream`.
2. New tab on the app.

Expected: the landing lists `vgmstream ... missing` and installs nothing (no `Installing` lines);
summary `<n>/<total> tools ready, 0 installed.` 05 SYSTEM offers INSTALL for it.

Cleanup: `auto_install = on`, INSTALL vgmstream.

## SQC-INST-10 (P1) `strict_preflight = on`

Steps:
1. In `startup.ini` set `strict_preflight = on` and set `[tools] quickbms = C:\nowhere\quickbms.exe`.
2. `viwo serve --no-browser`; note the exit code (`$LASTEXITCODE`).
3. Remove the `[tools]` line, keep `strict_preflight = on`, run again.

Expected:
- Step 2: the preflight lines print in the terminal, then `viwo: strict_preflight is on and
  these formats have no tool:` followed by `plugin quickbms: unarchive.bms has no backend (tool
  missing)`; exit code 4; no server.
- Step 3: server starts normally (exit only on Ctrl+C).

Cleanup: `strict_preflight = off`.

## SQC-INST-11 (P2) `Start.py` behaves like `viwo serve`

Steps: `python Start.py --no-browser`

Expected: same two startup lines as `viwo serve`; Ctrl+C stops it with exit code 0.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-INST-01 | | version: | | |
| SQC-INST-02 | | | | |
| SQC-INST-03 | | | | |
| SQC-INST-04 | | | | |
| SQC-INST-05 | | | | |
| SQC-INST-06 | | | | |
| SQC-INST-07 | | | | |
| SQC-INST-08 | | | | |
| SQC-INST-09 | | | | |
| SQC-INST-10 | | | | |
| SQC-INST-11 | | | | |
