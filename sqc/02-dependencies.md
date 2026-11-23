# 02 Dependencies (pinned tools, `viwo install`, SYSTEM)

Area code `DEP`. Reference: `viwo\data\tools.json` (pins), `viwo\data\dependencies.json` (labels,
env overrides, hints), `viwo\core\thirdparty.py` (installer), `viwo\core\preflight.py` (check
and install events). A tool is found in this order: `[tools] <id> = <path>` in the ini, the
`VIWO_<ID>` environment variable where `dependencies.json` names one, `third_party\` next to the
ini, PATH, known install folders.

Pinned tools (version / kind / how it runs), for the checks below:

| id | version | kind | notes |
|----|---------|------|-------|
| repak | 0.2.3 | zip | `repak.exe` |
| retoc | 0.1.5 | zip | `retoc.exe` |
| vgmstream | r2168 | zip | `vgmstream-cli.exe` |
| gdre | 2.7.4 | zip | `gdre_tools.exe` (+ its `.pck` next to it) |
| godotpcktool | 2.3 | raw | single exe |
| assetstudiomod | 0.20.0 | zip, needs `dotnet` | runs as `dotnet <AssetStudioModCLI.dll>` |
| dotnet | 10.0.14 | zip (hidden) | .NET runtime, installed for the tools that need it |
| sevenzip | 26.05 | msi (`msiexec /a`) | `Files\7-Zip\7z.exe` |
| unrar | 7.30 beta 2 (Windows), 7.23 (Linux) | sfx, needs `sevenzip` | `UnRAR.exe` pulled out of `unrarw64.exe` by 7-Zip |
| ffmpeg / ffprobe | 6.1.1 | gz | static builds |
| quickbms | 0.12.0 | zip | `quickbms.exe` + empty `scripts\` folder |
| datatool | 2.25.1.0+1153 | zip | Windows only, self-contained .NET |
| renderdoccmd | 1.47 | zip | `renderdoccmd.exe` |
| rdpython | 1.47 | alias of renderdoccmd | `qrenderdoc.exe --py` |
| unrpyc | 2.0.4 | zip | `.rpyc` to `.rpy` (run by ViWo's Python) |
| cp77-hashes | 95074158 | data | WolvenKit's Cyberpunk path list, pinned by commit (Windows) |
| wolvenkit | 9.1.0 | zip, needs `dotnet` | WolvenKit's console (GPL-3, a process), every run under a memory cap (SQC-SAFE-09) |
| redscript | 0.5.32 | raw | `redscript-cli.exe` (Windows) |
| uas | 0.5.0 | zip | `uas.exe`, UnrealAssetScout (`export.unreal`, Windows) |
| jdk | 25.0.5+8 | zip | Temurin JDK for Ghidra, unluac and uber-apk-signer |
| ghidra | 12.2 | zip, on demand | `viwo install ghidra` only, never by the preflight |
| qemu | 11.1.0 | sfx, on demand (Windows) | `qemu-system-x86_64.exe` (GPL-2, a process; isolation arm) |
| unicorn | 2.1.4 | worker | pip into `third_party\unicorn\`, never imported |
| angr | 9.2.223 | worker, on demand | pip into `third_party\angr\`, never imported |
| ilspycmd | 11.2.0.10050 | zip (NuGet nupkg) | `tools\any\win-x64\ilspycmd.exe` |
| cpp2il | 2022.1.0-pre-release.21 | raw | `Cpp2IL.exe`, self-contained (Windows) |
| unluac | 2025-12-23 (1.2.3.569) | raw | `unluac.jar`, run as `java -jar` on the pinned JDK |
| uber-apk-signer | 1.3.0 | raw, needs `jdk` | `uber-apk-signer.jar`, `java -jar` on the pinned JDK: aligns and signs a rebuilt APK |
| keystone | 0.9.2 | zip | `kstool.exe` (GPL-2, a process) for `asm` patches (Windows) |
| capstone | 5.0.9 | python | the disassembly in patch plans |
| x64dbg | 2026.05.27 | zip | `release\x64\x64dbg.exe` and `release\x32\x32dbg.exe` (GPL-3, a process) |
| cheatengine | 7.6 | sfx (Scoop's build), needs `sevenzip` | `cheatengine-x86_64.exe`; no installer, no elevation |
| scylla | 0.9.8 | sfx, needs `sevenzip` | `Scylla_x64.exe` (GPL-3, a process; Windows) |
| mitmproxy | 12.3.1 | zip | `mitmweb.exe` |
| frida-tools | 14.11.0 (+ frida 17.25.2) | python | `python -m frida_tools.tracer` |
| ue4ss | 3.0.1 | zip | `UE4SS.dll` + `dwmapi.dll` (installed into patched copies only) |
| bepinex | 6.0.0-be.785 | zip | `winhttp.dll` doorstop + `BepInEx\` (patched copies only) |
| soundcard | 0.4.6 (+ numpy 2.5.4) | python | loopback recording |
| die | 3.21 | zip | `diec.exe` (console) next to the GUI `die.exe` and the signature `db\` |
| rpfm-schema-<game> | 42290ba0 | raw, on demand | one Total War schema per game (`viwo install rpfm-schema-rom2`) |
| mermaid, pptxgenjs | 12.3.0, 4.0.1 | raw, on demand | presentation tools only |
| model-viewer | 4.0.0 | raw | the web UI's glTF viewer |
| unitypy, py7zr, unrpa, lz4 | 1.25.4, 1.1.4, 2.3.0, 4.4.5 | python | `pip --target third_party\python` from the hash locks |

`virtualbox` is a dependency row but never installed by ViWo (kernel driver).

## SQC-DEP-01 (P0) Every pinned tool binds and answers

Preconditions: SQC-INST-05 passed (everything installed). Or: another checkout's tools through
`C:\sqc\ini\real-tools.ini` (`build_fixtures.py --tools-from <checkout>`, 00-README).

Steps:
1. `viwo slots` (with `--ini C:\sqc\ini\real-tools.ini` for the second form)
2. `& third_party\repak\repak.exe --version`
3. `& third_party\sevenzip\Files\7-Zip\7z.exe` (no args)
4. `& third_party\unrar\UnRAR.exe`
5. `& third_party\dotnet\dotnet.exe (Get-ChildItem third_party\assetstudiomod -Recurse -Filter AssetStudioModCLI.dll).FullName --help`
6. `& third_party\quickbms\quickbms.exe` (prints usage)
7. `& third_party\renderdoccmd\RenderDoc_1.47_64\renderdoccmd.exe --version`
8. `& third_party\vgmstream\vgmstream-cli.exe` (usage)
9. Windows: `& third_party\datatool\DataTool.exe` (banner)
10. `& (Get-ChildItem third_party\jdk -Recurse -Filter java.exe).FullName -version`

Expected: step 1 shows `found` for every non-on-demand pin, `WHERE` = `third_party` and, for
tools under the ini's own `third_party\`, the pinned version in `VERSION` (a tool found through
`[tools]` shows the first line its version probe printed instead). Each command prints its banner
or usage and none fails with a missing DLL or runtime: `repak_cli 0.2.3`, `7-Zip 26.05 (x64)`,
`UNRAR 7.30 beta 2 x64`, `# AssetStudioModCLI [x64]` / `# Based on AssetStudioMod v0.20.0.0` (no
"You must install .NET"), QuickBMS `Usage: ...`, `renderdoccmd x64 v1.47`, `vgmstream CLI
decoder r2168` (after `missing input file(s)`, exit 1 is fine), `[Core] DataTool v2.25.1.0+1153`,
`openjdk version "25.0.5"`.

## SQC-DEP-02 (P0) `viwo install <id>` installs one tool, reinstalls over itself

Steps:
1. `Remove-Item -Recurse third_party\repak`
2. `viwo install repak`
3. `viwo install repak` again
4. `viwo install nosuchtool`

Expected:
- Step 2: stderr shows one `[CORE:CHECK] Checking <label> (i/N): ...` line per DEPENDENCY row of
  `viwo slots`, then `[CORE:INSTALL] Installing repak into <repo>\third_party`, `Downloading
  repak_cli-...zip, KB: ...` lines, `Installed repak`; stdout `Installed: repak`; exit 0.
- Step 3: same, the folder is replaced (no duplicate files, no `.repak-xxxx` temp folder left).
- Step 4: the check lines, then `viwo: invalid_request: unknown dependency id(s): nosuchtool` and
  the hint "ids are listed by `viwo slots`"; exit code 2; nothing downloaded.

## SQC-DEP-03 (P0) `viwo install --all` is idempotent

Steps:
1. `viwo install --all` with everything installed.
2. `Remove-Item -Recurse third_party\unrar, third_party\sevenzip` then `viwo install --all`.
3. `viwo install` (no id, no `--all`).

Expected:
- Step 1: no download happens; the answer is `viwo: invalid_request: nothing to install: give
  ids or --all` (exit 2) or `Installed: nothing` (exit 0): either is a PASS.
- Step 2: both install; `unrar` pulls `sevenzip` first (the log shows `Downloading 7z2605-x64.msi`
  before `Downloading unrarw64.exe`); `third_party\unrar\UnRAR.exe` exists.
- Step 3: `viwo: invalid_request: nothing to install: give ids or --all`, exit 2.

## SQC-DEP-04 (P0) Checksum mismatch is refused, nothing lands

Steps:
1. Edit `viwo\data\tools.json`: change one hex digit of `tools.repak.windows.sha256`.
2. `Remove-Item -Recurse third_party\repak`; `viwo install repak`
3. Restore the file (`git checkout viwo/data/tools.json`).

Expected: step 2 prints `FAILED repak: repak_cli-...zip: checksum mismatch, not installed` (in
the `failed` list, exit 0 with a warning); `third_party\repak` does not exist; no temp folder
remains under `third_party\`.

## SQC-DEP-05 (P0) SYSTEM: INSTALL per tool, INSTALL ALL MISSING, RE-CHECK

Preconditions: app running; delete `third_party\vgmstream` and `third_party\godotpcktool`, then
reload the page (F5).

Steps:
1. Open `SYSTEM`. Read the stats row and `OPTIONAL TOOLS BY ENGINE`.
2. In the `vgmstream-cli` row click `INSTALL`.
3. Click `INSTALL ALL MISSING (n)`.
4. Click `RE-CHECK`.

Expected:
- Step 1: stats `TOOLS FOUND`, `FORMATS READY`, `PLUGINS`, `STARTUP NOTES`; the two rows show
  `NOT INSTALLED` and an `INSTALL` button; the table columns read `TOOL`, `ENABLES`, `STATUS`,
  `WHERE / INSTALL`; the header button reads `INSTALL ALL MISSING (n)` with n the installable,
  non-on-demand missing count.
- Step 2: a progress block shows `Installing vgmstream-cli into ...`, `Downloading
  vgmstream-win64.zip, KB: x / y` lines, `Installed vgmstream-cli`, ends complete with the toast
  naming it. The row becomes `INSTALLED` with its `third_party\...` path and version `r2168`;
  `FORMATS READY` and the top-bar `FORMATS` chip increase without a reload.
- Step 3: godotpcktool installs; toast `<ready>/<total> tools ready, 1 installed`; the button
  becomes `NOTHING TO INSTALL` (disabled) when only on-demand tools are missing.
- Step 4: a check run with nothing installed; toast `<ready>/<total> tools ready, 0 installed`.
- JOBS lists `TOOL INSTALL` and `STARTUP CHECK` jobs, all `SUCCEEDED`.

## SQC-DEP-06 (P1) `[tools]` wins over `third_party\`, which wins over PATH

Steps:
1. With ffmpeg found through `third_party\` (or `[tools]` in `real-tools.ini`) and a system ffmpeg
   on PATH: `viwo slots`.
2. An ini whose `[tools] ffmpeg = C:\nowhere\ffmpeg.exe` (for example `[startup] base =
   real-tools.ini` plus that line): `viwo --ini <it> slots`.

Expected:
- Step 1: `ffmpeg found ... third_party ...\ffmpeg.exe`, not the PATH copy.
- Step 2: the `[tools]` path does not exist, so the locator falls back to the next sources (env,
  PATH, known folders): `ffmpeg found ... PATH or ini C:\Program Files\ffmpeg\ffmpeg.EXE` (or
  `missing` and `media.encode` unbound when no system ffmpeg exists). Never an error.

## SQC-DEP-07 (P1) QuickBMS through `[options.quickbms] scripts`, real tool

Steps:
1. An ini with `[options.quickbms] scripts = C:\sqc\quickbms\scripts` (base: the shipped ini or
   `real-tools.ini`); or copy `C:\sqc\quickbms\scripts\foo.bms` into
   `third_party\quickbms\scripts\` (the default folder).
2. `viwo --ini <it> --json info` and read `data.slots["unarchive.bms"]`.
3. `viwo --ini <it> extract C:\sqc\quickbms\game --workspace C:\sqc\_ws\bms --on-existing replace`

Expected: step 2: `main: quickbms-cli`. Step 3: the real `quickbms.exe` runs the script on
`data.foo`: `[QUICKBMS:UNPACK] data.foo: script foo.bms`, `OK data.foo: 1 file(s) via
quickbms-cli`; the workspace holds `bin\inside.bin` and `foo\data.foo`; the summary's `WARNING :
game:data.foo: script foo.bms` names the script (an information note); exit 0.

Cleanup: remove `foo.bms` from `third_party\quickbms\scripts\` if it was copied there.

## SQC-DEP-08 (P1) Linux: executables keep their exec bit, `dotnet` runs

Preconditions: Linux host.

Steps: `viwo install --all`; `ls -l third_party/repak/repak third_party/dotnet/dotnet
third_party/renderdoccmd/renderdoc_1.47/bin/renderdoccmd`; `viwo slots`.

Expected: all three are `-rwxr-xr-x`; every pinned Linux tool is `found`; the Windows-only pins
(`datatool`, `cpp2il`, `keystone`, `x64dbg`, `cheatengine`, `scylla`, `ue4ss`, `bepinex`,
`cp77-hashes`, `redscript`, `uas`, `qemu`) are `missing` with their hint and are not offered for
install.

## SQC-DEP-09 (P2) Frozen bundle: Python packages are not installable

Preconditions: 15-release-package built.

Steps: in the bundle folder `viwo.exe install unitypy`.

Expected: the `failed` list names `unitypy: unitypy has no automatic install on this platform`
(the bundle already contains UnityPy; `viwo.exe slots` shows it `found`).

## SQC-DEP-10 (P1) The APK signer can be installed by name

Steps:
1. `viwo slots` and look for an `uber-apk-signer` row.
2. `viwo install uber-apk-signer` (network).

Expected: step 1 lists `uber-apk-signer` (missing, `pinned: viwo install uber-apk-signer`); step 2
installs `third_party\uber-apk-signer\uber-apk-signer.jar` (the JDK first if it is missing) and
prints `Installed: uber-apk-signer`; afterwards a rebuilt APK is signed (SQC-RT-10). The hint
ViWo prints for an unsigned APK (`viwo install uber-apk-signer`) must work as written.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-DEP-01 | PASS (second form) | version: 1.36.0+search+apk (unreleased). The main checkout's tools through `C:\sqc-a\ini\real-tools.ini`: every installed pin `found`, WHERE `third_party`; not installed there, so `missing`: angr, capstone, frida-tools, scylla, soundcard, unicorn, 13 rpfm schemas. Banners: `repak_cli 0.2.3`, `7-Zip 26.05 (x64)`, `UNRAR 7.30 beta 2 x64`, `# Based on AssetStudioMod v0.20.0.0`, QuickBMS usage, `renderdoccmd x64 v1.47`, `vgmstream CLI decoder r2168`, `[Core] DataTool v2.25.1.0+1153+8b6cab09`, `openjdk version "25.0.5"`. VERSION shows the probe's first line for `[tools]` tools (`missing argume` for vgmstream, an ANSI `Error:` for the AssetStudio wrapper) | agent | 2026-11-23 |
| SQC-DEP-02 | NOT RUN steps 1-3; PASS step 4 | steps 1-3 download. Step 4: 59 check lines, `viwo: invalid_request: unknown dependency id(s): nosuchtool`, hint, exit 2 | agent | 2026-11-23 |
| SQC-DEP-03 | NOT RUN steps 1-2; PASS step 3 | steps 1-2 download (missing pins exist in the tool home used). Step 3: `nothing to install: give ids or --all`, exit 2 | agent | 2026-11-23 |
| SQC-DEP-04 | NOT RUN | downloads, and edits product data | | |
| SQC-DEP-05 | NOT RUN | needs a browser and the network | | |
| SQC-DEP-06 | PASS | step 1: `ffmpeg found ... third_party ...\Vidya Wormhole\third_party\ffmpeg\ffmpeg.exe` while `C:\Program Files\ffmpeg` is on PATH. Step 2: `ffmpeg found ... PATH or ini C:\Program Files\ffmpeg\ffmpeg.EXE`, `media.encode ffmpeg` still bound | agent | 2026-11-23 |
| SQC-DEP-07 | PASS (`[options.quickbms]` form) | `unarchive.bms` main `quickbms-cli`; real quickbms 0.12.0: `data.foo: script foo.bms`, `OK data.foo: 1 file(s)`, `bin\inside.bin` + `foo\data.foo`, exit 0 | agent | 2026-11-23 |
| SQC-DEP-08 | NOT RUN | needs a Linux host and the network | | |
| SQC-DEP-09 | NOT RUN | needs the frozen bundle (15) | | |
| SQC-DEP-10 | FAIL | `viwo slots` has no `uber-apk-signer` row (no backend lists it as a dependency; only the android plugin's manifest does); `viwo install uber-apk-signer` -> `viwo: invalid_request: unknown dependency id(s): uber-apk-signer`, exit 2, although `tools.json` pins it for Windows and Linux. The preflight never installs it either, so every rebuilt APK stays unsigned on a fresh install | agent | 2026-11-23 |
