# 01 Install and first run (startup installer, landing screen)

Area code `INST`. Preconditions for the whole file: a clean checkout, no `third_party\` and no
`viwo-data\` next to `startup.ini` (delete both), internet access, browser closed. A check that
needs no download can run from a copy of `startup.ini` in an empty folder of its own (`--ini
C:\sqc\home\startup.ini`): that folder then plays the clean checkout (`third_party\` and
`viwo-data\` are looked for next to the ini).

## SQC-INST-01 (P0) Fresh install from a checkout

Preconditions: Python 3.10 or newer on PATH as `py` (Windows) or `python3` (Linux). No venv yet.

Steps:
1. `py -3.10 -m venv .venv; .venv\Scripts\Activate.ps1` (any 3.10+ works)
2. `pip install -e ".[unity,sevenzip,renpy,lz4,dev]"`
3. `viwo`
4. `viwo --json info`

Expected:
- Step 2 ends with `Successfully installed ... viwo-<version>` and no error.
- Step 3 prints the guide: `ViWo // Vidya Wormhole - game reverse engineering, local only.`, then
  lines starting `viwo serve`, `viwo survey`, `viwo extract`, `viwo capture`, `viwo repack`,
  `viwo slots`, `viwo install --all | --game SLUG`, `viwo indexes update`, `viwo config check
  startup.ini`, `viwo diag`; the line naming the three arms (`viwo static`, `viwo dynamic`, `viwo
  patching`, `viwo system`); the philosophy paragraph (`A community tool for everyone who wants to
  look inside a game. No boundaries in the code; a disclaimer instead: ...`). Exit code 0.
- Step 4 prints a JSON envelope with `"ok": true`, `data.os` = `windows` or `linux` and
  `data.plugins` listing the 33 plugin ids: ags, android, bannerlord, bethesda, chromium,
  cyberpunk2077, defold, doom, dotnet, electron, gamemaker, generic, genie, godot, java, kaitai,
  kirikiri, love2d, overwatch, pyfrozen, qt, quickbms, redengine, renpy, rpgmaker, source,
  taleworlds, tyranoscript, unity, unreal, warscape, wolfrpg, xna.

## SQC-INST-02 (P0) `viwo slots` before any tool is installed

Steps:
1. `viwo slots` (or `viwo --ini C:\sqc\home\startup.ini slots`)

Expected:
- Two tables. `SLOT / MAIN / SPARE`: among others `unarchive.zip py-zipfile sevenzip-cli`,
  `unarchive.rpa rpa-safe unrpa`, `export.unity unitypy`, `carve.signatures signature-carver`,
  `unarchive.apk apk-zip`, `pack.apk apk-pack`, `decode.axml axml-builtin`, `decode.arsc
  arsc-builtin`, `unarchive.wolf wolf-builtin`, `unarchive.gamemaker gm-builtin`, `decode.xnb
  xnb-builtin`, `decode.kaitai_wav kaitai-wav`; slots whose tool is missing show `-- unbound --`
  (`unarchive.pck`, `unarchive.upak`, `unarchive.utoc`, `unarchive.bms`, `capture.gpu`,
  `export.overwatch`, `decode.rpyc`); a slot whose main is missing but whose spare is there shows
  the spare `(promoted)` (`unarchive.rar sevenzip-cli (promoted)` with 7-Zip on PATH).
- `DEPENDENCY / STATUS / VERSION / WHERE / LOCATION / HOW`: the Python packages `py7zr`,
  `unrpa`, `unitypy`, `lz4`, `pillow` are `found` (`python`); every pinned tool not on PATH is
  `missing` with `pinned: viwo install <id>` and a one-line hint; the last stdout line reads
  missing tools: `viwo install --all` (pinned, checksums verified) or SYSTEM.
- stderr: one `viwo: warning: <slot>: <backend> unavailable (<hint>)` line per unbound backend.
- Exit code 0.

## SQC-INST-03 (P1) `viwo config check` on the shipped ini files

Steps:
1. `viwo config check startup.ini distros\linux-custom.ini ... distros\windows-unreal.ini` (the
   12 distro files by name; PowerShell does not expand `distros\*.ini` for a native command:
   `viwo config check startup.ini (Get-ChildItem distros\*.ini).FullName`; Linux:
   `distros/*.ini`)

Expected: `OK: <13 paths>` and exit code 0. Any problem line is a FAIL.

## SQC-INST-04 (P0) First `viwo serve`: landing screen driven by the real preflight

Preconditions: no `third_party\` folder. A browser that will open automatically.

Steps:
1. `viwo serve`
2. Watch the browser tab that opens. Start a stopwatch when the page appears.
3. Keep the terminal visible.

Expected:
- Terminal: `ViWo // Vidya Wormhole -> http://127.0.0.1:8081/` and `Workspace: <path>   (Ctrl+C
  stops the server)`.
- The page is covered by a full-screen landing: the `VIWO // VIDYA WORMHOLE` logo, a stage line
  (`STARTING`, then `CHECKING TOOLS`, then `INSTALLING`, then `READY`), a bar, a log box, the
  summary line (`Checking the tools ViWo can use on this machine…` at first) and the footer
  `LOCAL-FIRST // 127.0.0.1 // THE GAME FOLDER IS NEVER WRITTEN`.
- Log box: first `Loaded <n> engine plugins, <m> formats`, then one line per check in the form
  `Checking <label> (i/N): found <version>` or `Checking <label> (i/N): missing`; N equals the
  number of DEPENDENCY rows of `viwo slots` (59 on Windows with the shipped ini).
- During the checks the bar is determinate and the counter at the right reads `i / N`.
- Then `Installing missing tools (i/M): <label>` lines, each followed by `Installing <label> into
  <home>\third_party` and `Downloading <file>, KB: x / y` lines; the counter shows `<file> · x /
  y KB`. The on-demand pins (Ghidra, QEMU, the RPFM schemas, mermaid, pptxgenjs) are never
  installed here.
- Each installed tool ends with `Installed <label>`; the last line is `Ready: <ready>/<total>
  tools available`.
- Summary at the end: `All <total> tools ready, <k> installed just now.` or `<ready>/<total> tools
  ready, <k> installed just now.` (`, <f> could not be installed (see SYSTEM)` appended when one
  failed).
- The landing stays at least 1.2 s, then fades out; EXTRACT is underneath and the top-bar
  `FORMATS a/b READY` chip shows the new count without a reload.
- JOBS shows one job of kind `STARTUP CHECK`, state `SUCCEEDED`.

Cleanup: none (keep `third_party\` for 02).

## SQC-INST-05 (P0) Tools landed in `third_party\` and nowhere else

Preconditions: SQC-INST-04 passed.

Steps:
1. `Get-ChildItem third_party`
2. `Get-ChildItem third_party -Recurse -Filter *.exe | Select-Object -First 40 FullName`
3. `viwo slots`

Expected:
- Step 1 lists exactly the ids that were missing in SQC-INST-02, are pinned for this OS and are
  not on demand, from: `assetstudiomod bepinex cheatengine cp77-hashes cpp2il datatool die
  ffmpeg ffprobe gdre godotpcktool ilspycmd jdk keystone mitmproxy quickbms redscript renderdoccmd
  repak retoc scylla sevenzip uas ue4ss unicorn unluac unrar unrpyc vgmstream wolvenkit x64dbg
  python`, plus `dotnet` (the .NET runtime) when no .NET is on PATH. (`model-viewer` is pinned
  but no dependency row names it.)
  (`rdpython` has no folder: it lives in `renderdoccmd\`; `bepinex`, `cheatengine`, `cp77-hashes`,
  `cpp2il`, `datatool`, `keystone`, `redscript`, `scylla`, `uas`, `ue4ss` and `x64dbg` are
  Windows only; `ghidra`, `qemu`, `angr`, the `rpfm-schema-*`, `mermaid` and `pptxgenjs` are on
  demand and never installed here; `uber-apk-signer` is pinned but no backend lists it, so the
  preflight never installs it (see SQC-DEP-10); `python\` appears only if a Python package was
  missing.) No `.tmp` or `.<id>-xxxx` leftovers.
- Step 2: `third_party\repak\repak.exe`, `third_party\sevenzip\Files\7-Zip\7z.exe`,
  `third_party\unrar\UnRAR.exe`, `third_party\quickbms\quickbms.exe`,
  `third_party\renderdoccmd\RenderDoc_1.47_64\renderdoccmd.exe` and `qrenderdoc.exe`,
  `third_party\dotnet\dotnet.exe`, `third_party\datatool\DataTool.exe`.
- Nothing was written to `C:\Program Files`, `%LOCALAPPDATA%` or the user profile by ViWo
  (compare timestamps if in doubt).
- Step 3: every pinned dependency except the on-demand ones is `found` with a `third_party\...`
  path and the pinned version in `VERSION`; `assetstudiomod` shows the dll; `rdpython` shows
  `...\qrenderdoc.exe`. `unarchive.pck`, `unarchive.upak`, `unarchive.utoc`, `unarchive.rar`,
  `unarchive.bms`, `capture.gpu`, `export.overwatch` (Windows) are bound.
- `third_party\quickbms\scripts\` exists and is empty.

## SQC-INST-06 (P0) Landing is skipped on reload within the same tab

Steps:
1. In the tab of SQC-INST-04, press F5.
2. Open a new tab on `http://127.0.0.1:8081/`.

Expected:
- Step 1: no landing; the app appears directly on the last view.
- Step 2: the landing runs again (new tab = new session storage) and now shows every tool as
  `found` except the on-demand ones; summary `<ready>/<total> tools ready.` (`All <total> tools
  ready.` when nothing is missing), held about 1.2 s.

## SQC-INST-07 (P1) Landing with reduced motion

Preconditions: OS "reduce motion" on (Windows: Animation effects off).

Steps:
1. New tab on the app.

Expected: the landing appears and disappears without the fade and without the animated scan on
the bar; the bar still fills (determinate) and the lines still appear; the summary and hold are
unchanged.

## SQC-INST-08 (P1) Landing when the preflight cannot install

Preconditions: block outbound HTTPS for `python.exe` in the firewall, or unplug the network;
delete `third_party\repak`.

Steps:
1. New tab on the app.

Expected: the check lines run; `Installing missing tools (1/1): repak`; then a warn line
`Could not install repak: ...`; summary `<n>/<total> tools ready, 1 could not be installed (see
SYSTEM).` The landing hands off normally; the app works; SYSTEM shows `repak` with `NOT
INSTALLED` and an `INSTALL` button.

Cleanup: restore the network; SYSTEM > INSTALL on repak.

## SQC-INST-09 (P1) `auto_install = off`

Steps:
1. In `startup.ini` set `auto_install = off`; delete `third_party\vgmstream`.
2. New tab on the app.
3. Without a browser: `POST /api/preflight` with the page's token (or the API helper of
   `00-README`).

Expected: the landing lists `Checking vgmstream-cli (i/N): missing` and installs nothing (no
`Installing` lines); summary `<n>/<total> tools ready.`; SYSTEM offers INSTALL for it. Step 3
answers `installed: []`, `failed: []`, `ready` = the `found` count, `total` = N.

Cleanup: `auto_install = on`, INSTALL vgmstream.

## SQC-INST-10 (P1) `strict_preflight = on`

Steps (offline: a copy of `startup.ini` in its own empty folder, so nothing is installed):
1. In the copy set `strict_preflight = on`, `auto_install = off` and `[server] port = 8191`.
2. `viwo --ini <copy> serve --no-browser`; note the exit code (`$LASTEXITCODE`).
3. With the tools installed (SQC-INST-05) and the shipped ini plus `strict_preflight = on`, run
   `viwo serve --no-browser` again.

Expected:
- Step 2: the `[CORE:CHECK] Checking <label> (i/59): ...` lines and `[CORE:READY] Ready:
  <n>/59 tools available` print in the terminal, then `viwo: strict_preflight is on and these
  formats have no tool:` followed by one `  plugin <id>: <slot> has no backend (tool missing)`
  line per unbound plugin slot (among them `plugin godot: unarchive.pck`, `plugin quickbms:
  unarchive.bms`, `plugin unreal: unarchive.upak`, `plugin overwatch: export.overwatch`);
  exit code 4; no server.
- Step 3: the server starts normally (exit only on Ctrl+C).

## SQC-INST-11 (P2) `Start.py` behaves like `viwo serve`

Steps: `python Start.py --port 8191 --no-browser`, then Ctrl+C in that console.

Expected: the same two startup lines as `viwo serve` (`ViWo // Vidya Wormhole ->
http://127.0.0.1:8191/`, `Workspace: ...`); the page answers; Ctrl+C stops it with exit code 0.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-INST-01 | PASS steps 3-4; NOT RUN steps 1-2 | version: 1.36.0+search+apk (unreleased). Steps 1-2 need a fresh venv and network (pip): not done; the existing 3.10.6 venv was used. Step 3: the guide as written, exit 0. Step 4: `ok: true`, `os: windows`, 33 plugins as listed | agent | 2026-11-23 |
| SQC-INST-02 | PASS | from an empty home (`--ini C:\sqc-a\home\startup.ini`): `unarchive.pck`, `unarchive.upak`, `unarchive.utoc`, `unarchive.bms`, `capture.gpu`, `export.overwatch`, `decode.rpyc` unbound; `unarchive.rar sevenzip-cli (promoted)` (system 7-Zip on PATH); 59 dependency rows, py7zr/unrpa/unitypy/lz4/pillow found; exit 0. `uber-apk-signer` has no row (SQC-DEP-10) | agent | 2026-11-23 |
| SQC-INST-03 | PASS | `OK:` with the 13 paths, exit 0 | agent | 2026-11-23 |
| SQC-INST-04 | NOT RUN | needs a browser, eyes and the network (the startup installer downloads) | | |
| SQC-INST-05 | NOT RUN | needs SQC-INST-04's install (download) | | |
| SQC-INST-06 | NOT RUN | needs a browser | | |
| SQC-INST-07 | NOT RUN | needs a browser and eyes | | |
| SQC-INST-08 | NOT RUN | needs a browser and a blocked network | | |
| SQC-INST-09 | NOT RUN steps 1-2; PASS step 3 | landing needs a browser. Step 3 (API, `auto_install = off`, the real-tools ini): `installed: []`, `failed: []`, `ready: 40`, `total: 59` | agent | 2026-11-23 |
| SQC-INST-10 | PASS step 2; NOT RUN step 3 | step 2: 59 check lines, `Ready: 11/59 tools available`, the strict list (17 plugin slots, godot/quickbms/unreal/overwatch among them), exit 4. Step 3 needs the installed tools in the checkout's own `third_party\` | agent | 2026-11-23 |
| SQC-INST-11 | PASS start; NOT RUN Ctrl+C | `python Start.py --port 8191 --no-browser`: both lines, the page answered. A console Ctrl+C cannot be sent from the harness (CTRL_BREAK gave 0xC000013A), so the exit code on Ctrl+C is not checked | agent | 2026-11-23 |
