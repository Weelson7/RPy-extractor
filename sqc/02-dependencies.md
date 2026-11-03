# 02 Dependencies (pinned tools, `viwo install`, 05 SYSTEM)

Area code `DEP`. Reference: `viwo\data\tools.json` (pins), `viwo\core\thirdparty.py`
(installer), `viwo\core\preflight.py` (check and install events).

Pinned tools (version / kind / how it runs), for the checks below:

| id | version | kind | notes |
|----|---------|------|-------|
| repak | 0.2.3 | zip | `repak.exe` |
| retoc | 0.1.5 | zip | `retoc.exe` |
| vgmstream | r2168 | zip | `vgmstream-cli.exe` |
| gdre | 2.7.4 | zip | `gdre_tools.exe` (+ its `.pck` next to it) |
| godotpcktool | 2.3 | raw | single exe |
| assetstudiomod | 0.20.0 | zip, needs `dotnet` | runs as `third_party\dotnet\dotnet.exe <dll>` |
| dotnet | 10.0.14 | zip (hidden) | .NET runtime, not a dependency of its own |
| sevenzip | 26.05 | msi (`msiexec /a`) | `7z.exe` |
| unrar | 7.30 beta 2 | sfx, needs `sevenzip` | `UnRAR.exe` pulled out of `unrarw64.exe` by 7-Zip |
| ffmpeg / ffprobe | 6.1.1 | gz | static builds |
| quickbms | 0.12.0 | zip | `quickbms.exe` + empty `scripts\` folder |
| datatool | 2.25.0.0+1151 | zip | Windows only, self-contained .NET |
| renderdoccmd | 1.47 | zip | `renderdoccmd.exe` |
| rdpython | 1.47 | alias of renderdoccmd | `qrenderdoc.exe --py` |
| ilspycmd | 11.2.0.10050 | zip (NuGet nupkg) | `tools\any\win-x64\ilspycmd.exe` |
| cpp2il | 2022.1.0-pre-release.21 | raw | `Cpp2IL.exe`, self-contained |
| unluac | 2025-12-23 | raw | `unluac.jar`, run as `java -jar` on the pinned JDK |
| keystone | 0.9.2 | zip | `kstool.exe` (GPL-2, run as a process) for `asm` patches |
| capstone | 5.0.9 | python | the disassembly in patch plans |
| die | 3.21 | zip | `diec.exe` (console) next to the GUI `die.exe` and the signature `db\` |
| unitypy, py7zr, unrpa, lz4 | pinned | python | `pip --target third_party\python` |

## SQC-DEP-01 (P0) Every pinned tool binds and answers

Preconditions: SQC-INST-05 passed (everything installed).

Steps:
1. `viwo slots`
2. `& third_party\repak\*\repak.exe --version`
3. `& third_party\sevenzip\*\7z.exe` (no args; path depends on the MSI layout: use
   `Get-ChildItem third_party\sevenzip -Recurse -Filter 7z.exe`)
4. `& third_party\unrar\UnRAR.exe`
5. `& third_party\dotnet\dotnet.exe third_party\assetstudiomod\AssetStudioModCLI.dll --help`
6. `& third_party\quickbms\quickbms.exe` (prints usage, exit non-zero is fine)
7. `& third_party\renderdoccmd\RenderDoc_1.47_64\renderdoccmd.exe --version`
8. `& third_party\vgmstream\vgmstream-cli.exe` (usage)
9. Windows: `& third_party\datatool\DataTool.exe` (usage)

Expected: step 1 shows `found` for all of them with the exact version from the table in the
`WHERE / HOW` column context (05 SYSTEM shows the version under the tool name); each command
prints its banner or usage and none fails with a missing DLL or runtime error. Step 5 prints
AssetStudioModCLI help (no "You must install .NET" message).

## SQC-DEP-02 (P0) `viwo install <id>` installs one tool, reinstalls over itself

Steps:
1. `Remove-Item -Recurse third_party\repak`
2. `viwo install repak`
3. `viwo install repak` again
4. `viwo install nosuchtool`

Expected:
- Step 2: stderr shows the 17 `[CORE:CHECK]` lines, then `[CORE:INSTALL] Installing repak into
  <repo>\third_party`, `Downloading repak_cli-...zip, KB: ...` lines, `Installed repak`;
  stdout `Installed: repak`; exit 0.
- Step 3: same, the folder is replaced (no duplicate files, no `.repak-xxxx` temp folder left).
- Step 4: `viwo: invalid_request: unknown dependency id(s): nosuchtool` and the hint
  `ids are listed by viwo slots`; exit code 2.

## SQC-DEP-03 (P0) `viwo install --all` is idempotent

Steps:
1. `viwo install --all` with everything installed.
2. `Remove-Item -Recurse third_party\unrar, third_party\sevenzip` then `viwo install --all`.

Expected:
- Step 1: `viwo: invalid_request: nothing to install: give ids or --all` is NOT shown; instead,
  since nothing is missing, the command reports `nothing to install` (exit 2) or `Installed:
  nothing` (exit 0): either is a PASS as long as no download happens.
- Step 2: both install; `unrar` pulls `sevenzip` first (the log shows `Downloading 7z2605-x64.msi`
  before `Downloading unrarw64.exe`); `third_party\unrar\UnRAR.exe` exists.

## SQC-DEP-04 (P0) Checksum mismatch is refused, nothing lands

Steps:
1. Edit `viwo\data\tools.json`: change one hex digit of `tools.repak.windows.sha256`.
2. `Remove-Item -Recurse third_party\repak`; `viwo install repak`
3. Restore the file (`git checkout viwo/data/tools.json`).

Expected: step 2 prints `FAILED repak: repak_cli-...zip: checksum mismatch, not installed`;
`third_party\repak` does not exist; no temp folder remains under `third_party\`.

## SQC-DEP-05 (P0) 05 SYSTEM: INSTALL per tool, INSTALL ALL MISSING, RE-CHECK

Preconditions: app running; delete `third_party\vgmstream` and `third_party\godotpcktool`, then
reload the page (F5).

Steps:
1. Open `05 SYSTEM`. Read the stats row and `05.A OPTIONAL TOOLS BY ENGINE`.
2. In the `vgmstream-cli` row click `INSTALL`.
3. Click `INSTALL ALL MISSING (1)`.
4. Click `RE-CHECK`.

Expected:
- Step 1: `TOOLS FOUND` stat = `(total-2)/total`; the two rows show the badge `NOT INSTALLED` and an
  `INSTALL` button with the note `pinned, checksum verified`; the panel header button reads
  `INSTALL ALL MISSING (2)`.
- Step 2: a progress block appears above the table: `INSTALLING`, log lines `Installing
  vgmstream-cli into ...`, `Downloading vgmstream-win64.zip, KB: x / y` (counter `DOWNLOADED KB`
  climbs), `Installed vgmstream-cli`, ends `COMPLETE` with the toast `vgmstream-cli installed`.
  The table reloads: the row is `INSTALLED` with its `third_party\...` path and version `r2168`
  under the name; `FORMATS READY` and the top-bar `FORMATS` chip increase without a reload.
- Step 3: progress block `CHECKING`, rail `boot › check › install › ready`, counters `FOUND`,
  `MISSING`, `INSTALLED`; godotpcktool installs; toast `<total>/<total> tools ready, 1 installed`;
  button becomes `NOTHING TO INSTALL` (disabled).
- Step 4: `CHECKING` run with `INSTALLED 0`; toast `<total>/<total> tools ready, 0 installed`.
- 04 JOBS lists `TOOL INSTALL` and `STARTUP CHECK` jobs, all `SUCCEEDED`.

## SQC-DEP-06 (P1) Tool on PATH or in `[tools]` wins over `third_party\`

Steps:
1. With `third_party\ffmpeg\ffmpeg.exe` installed and a system ffmpeg on PATH: `viwo slots`.
2. Add `[tools] ffmpeg = C:\nowhere\ffmpeg.exe` to `startup.ini`; `viwo slots`.

Expected:
- Step 1: `ffmpeg found` with the PATH location? No: `third_party\` is injected as a config
  override and wins over PATH. The location shown is `third_party\ffmpeg\ffmpeg.exe`. (The ini
  `[tools]` entry is the only thing that beats `third_party\`.)
- Step 2: `ffmpeg missing` (the override path does not exist and the ini wins); `media.encode`
  unbound. Remove the line: back to `third_party\`.

## SQC-DEP-07 (P1) QuickBMS scripts folder is the default for `[options.quickbms]`

Steps:
1. Copy `C:\sqc\quickbms\scripts\foo.bms` into `third_party\quickbms\scripts\`.
2. `viwo --json info | Select-String bms`
3. `viwo extract C:\sqc\quickbms\game --workspace C:\sqc\_ws\bms --on-existing replace`

Expected: step 2 shows `unarchive.bms` bound to `quickbms-cli`; step 3 runs the real quickbms.exe
with `-o -Y <script> data.foo <dest>`; the fixture script logs the whole file as `inside.bin`,
so the workspace holds `bin\inside.bin` (or the extension group QuickBMS produced). Exit 0.

Cleanup: remove `foo.bms` from `third_party\quickbms\scripts\`.

## SQC-DEP-08 (P1) Linux: executables keep their exec bit, `dotnet` runs

Preconditions: Linux host.

Steps: `viwo install --all`; `ls -l third_party/repak/*/repak third_party/dotnet/dotnet
third_party/renderdoccmd/renderdoc_1.47/bin/renderdoccmd`; `viwo slots`.

Expected: all three are `-rwxr-xr-x`; every pinned Linux tool is `found`; `datatool` is listed
as `missing` with the hint (no Linux build) and is not offered for install.

## SQC-DEP-09 (P2) Frozen bundle: Python packages are not installable

Preconditions: 15-release-package built.

Steps: in the bundle folder `viwo.exe install unitypy`.

Expected: `viwo: unavailable: unitypy has no automatic install on this platform` (the bundle
already contains UnityPy; `viwo.exe slots` shows it `found`).

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-DEP-01 | | version: | | |
| SQC-DEP-02 | | | | |
| SQC-DEP-03 | | | | |
| SQC-DEP-04 | | | | |
| SQC-DEP-05 | | | | |
| SQC-DEP-06 | | | | |
| SQC-DEP-07 | | | | |
| SQC-DEP-08 | | | | |
| SQC-DEP-09 | | | | |
