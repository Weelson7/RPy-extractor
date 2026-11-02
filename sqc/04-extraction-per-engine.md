# 04 Extraction per engine

Area code `EXT`. Every plugin once, plus the encrypted / needs-key cases and nested archives.
Unless stated, run from the CLI with `--on-existing replace` into `C:\sqc\_ws\<name>` and then
verify the same run from `01 EXTRACT` (paste the game folder, `RUN EXTRACTION`, same target
workspace via the top-bar `WORKSPACE > SWITCH`). For every check also confirm:

- the game folder hash set is unchanged (`Get-ChildItem <game> -Recurse -File | Get-FileHash`
  before and after; the run record also stores `gameUnchanged: true`);
- the workspace has the marker `.viwo-workspace`, `.extraction_metadata\runs\<id>.json` and
  `.extraction_metadata\provenance.jsonl`;
- files are grouped by extension (`png\`, `ogg\`, `txt\`...).

## SQC-EXT-01 (P0) Generic: loose files and a zip

Steps: `viwo extract C:\sqc\zip-basic\game --workspace C:\sqc\_ws\zip --on-existing replace`

Expected: stderr lines `[CORE:DETECT] Selected plugin(s): generic`, `[CORE:UNPACK] OK data.zip:
2 file(s)`, `[CORE:COLLECT] ...`; workspace `png\title.png`, `png\a.png`, `ogg\theme.ogg`,
`txt\readme.txt`; summary `4 files, 1 archive`; exit 0.

## SQC-EXT-02 (P0) Nested archives and a traversal member

Steps: `viwo extract C:\sqc\nested-traversal\game --workspace C:\sqc\_ws\nested --on-existing replace`

Expected: `outer.zip` then `nested/inner.zip` are unpacked (two `OK` lines), `voice/hello.ogg`
lands in `ogg\`; the tar's `../escape.txt` is skipped with a warning line, and no `escape.txt`
exists anywhere under `C:\sqc`. `bg.png` in `png\`.

## SQC-EXT-03 (P1) Deep nesting stops at depth 10

Steps: `viwo extract C:\sqc\deep-nesting\game --workspace C:\sqc\_ws\deep --on-existing replace`

Expected: 10 `OK levelNN.zip` lines, then a warning that the nesting limit (10) was reached;
`deep.txt` is NOT extracted (it sits at level 13) but `level11.zip` is kept as a file in `zip\`.
Exit 0 (warnings, not failure).

## SQC-EXT-04 (P0) Ren'Py: `.rpa` through the safe reader, spare unrpa

Steps:
1. `viwo extract C:\sqc\renpy\game --workspace C:\sqc\_ws\renpy --on-existing replace`
2. `viwo --json extract C:\sqc\renpy\game --workspace C:\sqc\_ws\renpy2 --on-existing replace`
   and read `data.runs[0].backend`.

Expected: plugin `renpy`; `images.rpa` unpacked by `rpa-safe` (step 2 shows `"backend":
"rpa-safe"`), `png\bg.png`, `ogg\theme.ogg`, `rpy\script.rpy` (source root copied); the member
`../escape.txt` is refused with a warning and does not exist on disk.

## SQC-EXT-05 (P1) Ren'Py: `.rpa` with the main backend disabled (unrpa spare)

Steps: in `startup.ini` add `[slots] unarchive.rpa = unrpa, rpa-safe`; run SQC-EXT-04 step 2.

Expected: `"backend": "unrpa"`, same files. Remove the line afterwards.

## SQC-EXT-06 (P0) Godot: standalone, embedded, broken (fake tools), then real tools

Preconditions: `C:\sqc\ini\godot-fake.ini` (fake GDRE + GodotPckTool).

Steps:
1. `viwo --ini C:\sqc\ini\godot-fake.ini extract C:\sqc\godot\standalone --workspace C:\sqc\_ws\godot1 --on-existing replace`
2. same for `C:\sqc\godot\embedded`
3. same for `C:\sqc\godot\broken`
4. With the real pinned tools (default ini): `viwo extract C:\sqc\godot\standalone --workspace C:\sqc\_ws\godot4 --on-existing replace`

Expected:
- Step 1: plugin `godot`, backend `gdre` (main), the PCK's files appear by extension.
- Step 2: the PCK embedded in `Game.exe` is carved (`[CORE:UNPACK] ... Game.exe (embedded pck)`)
  and unpacked to the same files.
- Step 3: `FAILED data.pck` from the main tool, then `OK data.pck` via the spare `godotpcktool`;
  the run record lists both attempts; exit 0.
- Step 4: real `gdre_tools.exe` from `third_party\gdre\` extracts the synthetic PCK (it is a
  valid v2 PCK); if real GDRE rejects the synthetic file, the spare GodotPckTool must succeed.
  Either way the files land and the run succeeds.

## SQC-EXT-07 (P0) Godot: encrypted PCK needs a key

Steps:
1. `viwo --ini C:\sqc\ini\godot-fake.ini extract C:\sqc\godot\encrypted --workspace C:\sqc\_ws\godot5 --on-existing replace`
2. UI: 01 EXTRACT on `C:\sqc\godot\encrypted`, `01.C MODE > ENGINE OPTIONS > PCK encryption key`
   = 64 zeros, run.

Expected:
- Step 1: the run ends with exit 0 and a `needs_key` warning (summary and run record) naming
  `godot.encryption_key`; nothing is extracted from that archive. The spare is NOT tried for
  needs-key.
- Step 2: the fake tool accepts any 64-hex key and the run succeeds; the run record shows
  `"encryption_key": "<secret>"`, never the value; the log (04 JOBS, activity console,
  `viwo-data\logs\*.log`) never contains the key.

## SQC-EXT-08 (P0) Unreal: plain pak, key in the exe, locked pak, IoStore (fake tools)

Preconditions: `C:\sqc\ini\unreal-fake.ini`, key in `C:\sqc\unreal\unreal-key.txt`.

Steps:
1. `viwo --ini C:\sqc\ini\unreal-fake.ini extract C:\sqc\unreal\plain --workspace C:\sqc\_ws\ue1 --on-existing replace`
2. same for `keyinexe`
3. same for `locked`
4. `locked` again with `--option unreal.aes_key=<key from unreal-key.txt>`
5. same for `iostore`

Expected:
- 1: plugin `unreal`, backend `repak`, the pak's files extracted.
- 2: log `AES key found in Game-Win64-Shipping.exe and verified on the pak index`; extracted.
- 3: exit 0 with a `needs_key` warning naming `unreal.aes_key`; nothing extracted from the pak.
- 4: extracted; run record stores `<secret>`.
- 5: `retoc` converts `global.utoc/.ucas` to legacy (`OK global.utoc`), then repak unpacks.

## SQC-EXT-09 (P1) Unreal with the real repak/retoc

Steps: SQC-EXT-08 steps 1 and 2 with the default ini (real `third_party\repak\...\repak.exe`).

Expected: real repak reads the synthetic pak (built with the same layout repak writes) and
extracts it; the key is found and verified on the real index.

## SQC-EXT-10 (P0) Doom: IWAD, PWAD, broken WAD

Steps: `viwo extract C:\sqc\doom\game --workspace C:\sqc\_ws\doom --on-existing replace`

Expected: plugin `doom`; from `doom2.wad`: `png\TITLEPIC.png`, `png\FLOOR0_1.png`, `png\TROOA1.png`,
`wav\DSPISTOL.wav`, `mus\D_RUNNIN.mus`, `txt\DEHACKED.txt`, map `MAP01` as a folder or json;
`mod.wad` gives `png\POSSA1.png`; `broken.wad` yields `FAILED broken.wad: bad directory` and the
run still succeeds. With `--option doom.raw_lumps=true` every lump is also kept as `lmp\*.lmp`.

## SQC-EXT-11 (P0) RPG Maker: XP, VX Ace (with traversal), MV

Steps: extract `C:\sqc\rpgmaker\xp`, `...\vxace`, `...\mv` into three workspaces.

Expected: `xp`: `png\title.png` from `Game.rgssad` (v1). `vxace`: `png\Actor1.png`; the entry
`..\evil.txt` is skipped with a warning and does not exist on disk. `mv`: `Actor2.rpgmvp`
decrypted to `png\Actor2.png` and `Theme.rpgmvo` to `ogg\Theme.ogg` with the key read from
`System.json` (log line `MV key from System.json`); the key value is not logged.

## SQC-EXT-12 (P0) KiriKiri XP3: plain and encrypted entries

Steps: extract `C:\sqc\kirikiri\plain` and `C:\sqc\kirikiri\mixed`.

Expected: `plain`: `png\bg.png`, `ks\first.ks`. `mixed`: `png\bg.png` extracted; `secret.png`
reported in a warning `1 encrypted entry (per-title cipher) skipped`; exit 0.

## SQC-EXT-13 (P0) Electron asar and NW.js package.nw

Steps: extract `C:\sqc\electron\game` and `C:\sqc\electron\nw`.

Expected: both give `html\index.html` and `png\logo.png`; backend `asar-builtin` for the first,
`py-zipfile` for `package.nw`.

## SQC-EXT-14 (P0) Source VPK (multi-part)

Steps: extract `C:\sqc\source-vpk\game`.

Expected: `vmt\m.vmt` (inline) and `png\sky.png` (from `pak01_000.vpk`); `pak01_000.vpk` is not
unpacked a second time as a standalone archive.

## SQC-EXT-15 (P0) Bethesda BSA and BA2

Steps: extract `C:\sqc\bethesda\game`.

Expected: `txt\ui.txt`, `txt\hud.txt` from `Interface.bsa`; `txt\notes.txt` from `Main - Misc.ba2`.
With `lz4` installed (SQC-INST-01) no LZ4 warning appears for a v105 BSA (no fixture here; note
only).

## SQC-EXT-16 (P0) QuickBMS bridge (fake tool, then real tool)

Steps:
1. `viwo --ini C:\sqc\ini\quickbms-fake.ini extract C:\sqc\quickbms\game --workspace C:\sqc\_ws\bms1 --on-existing replace`
2. SQC-DEP-07 (real quickbms.exe with the script copied into `third_party\quickbms\scripts\`).

Expected: step 1: plugin list contains `quickbms` (it serves every game), `data.foo` handled by
`quickbms-cli` with `script foo.bms` in the notes, `bin\inside.bin` present. Step 2 as in 02.

## SQC-EXT-17 (P0) Overwatch through a fake DataTool: auto-selected with a reminder

Preconditions: `C:\sqc\ini\overwatch-fake.ini`.

Steps:
1. `viwo --ini C:\sqc\ini\overwatch-fake.ini extract C:\sqc\overwatch\Overwatch --workspace C:\sqc\_ws\ow --on-existing replace`
2. same with `--plugin overwatch --option overwatch.modes=extract-maps`

Expected:
- Step 1: AUTO picks `overwatch` (log `Selected plugin(s): overwatch`); the fake tool runs the
  three default modes (`extract-unlocks`, `extract-general`, `extract-maps`), producing
  `txt\extract-unlocks.txt` etc.; the warnings contain `Overwatch: personal, offline use of your
  own install; respect Blizzard's terms`. No refusal anywhere.
- Step 2: only `extract-maps` runs.

## SQC-EXT-18 (P1, OPERATOR) Overwatch with the real DataTool on a real install

Steps: `viwo extract "<Overwatch install>" --workspace <ws> --plugin overwatch`

Expected: `third_party\datatool\DataTool.exe` runs the modes; textures and maps land; the reminder
is present in the warnings; the install folder is unchanged.

## SQC-EXT-19 (P1) Unity: markers only, then a real Unity game

Steps:
1. extract `C:\sqc\unity-markers\game`.
2. Any Unity game you own (UnityPy main): extract it; then set
   `[slots] export.unity = assetstudiomod-cli, unitypy` and extract again.

Expected: step 1: plugin `unity`, `globalgamemanagers` is reported as a corrupt container
(`FAILED ... not a Unity file`) and the run succeeds with 0 files. Step 2: textures (`png\`),
audio, text assets; with AssetStudioModCLI the backend id is `assetstudiomod-cli` and it runs as
`third_party\dotnet\dotnet.exe ...\AssetStudioModCLI.dll` (visible in the activity console).

## SQC-EXT-20 (P1) 7z, rar and tar through core backends

Preconditions: `archives-all` fixture built with py7zr installed.

Steps: extract `C:\sqc\archives-all\game`.

Expected: `txt\one.txt` (tar), `txt\two.txt` (rar via `unrar` from third_party), `txt\three.txt`
(7z via `sevenzip-cli`); the run record shows these backends. Remove `third_party\unrar` and run
again: rar is handled by the spare `sevenzip-cli` (binding `promoted`).

## SQC-EXT-21 (P1) Encrypted zip and 7z need a password

Preconditions: build `C:\sqc\encrypted-zip\game\locked.zip` and `locked.7z` as `MAKE-ME.txt`
says.

Steps: extract `C:\sqc\encrypted-zip\game`.

Expected: both archives end `FAILED ... password`, the run succeeds with warnings; no partial
`secret.txt`. (Passwords are not guessed; there is no password option in 1.0: note as expected.)

## SQC-EXT-22 (P1) Carver on an unknown blob

Steps: `viwo extract C:\sqc\carve\game --workspace C:\sqc\_ws\carve --on-existing replace`

Expected: `[CORE:CARVE] Carved 16 file(s) from assets.bin`; `png\`, `jpg\`, `gif\`, `wav\`,
`wem\`, `ogg\`, `mid\`, `mp4\`, `bik\`, `fsb\`, `bnk\`, `dds\`, `glb\`, `zip\`, `7z\` groups
exist; the DECODE stage then turns `dds` into `png` and `wem` into `wav` (vgmstream installed).

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-EXT-01 | | version: | | |
| SQC-EXT-02 | | | | |
| SQC-EXT-03 | | | | |
| SQC-EXT-04 | | | | |
| SQC-EXT-05 | | | | |
| SQC-EXT-06 | | | | |
| SQC-EXT-07 | | | | |
| SQC-EXT-08 | | | | |
| SQC-EXT-09 | | | | |
| SQC-EXT-10 | | | | |
| SQC-EXT-11 | | | | |
| SQC-EXT-12 | | | | |
| SQC-EXT-13 | | | | |
| SQC-EXT-14 | | | | |
| SQC-EXT-15 | | | | |
| SQC-EXT-16 | | | | |
| SQC-EXT-17 | | | | |
| SQC-EXT-18 | | OPERATOR | | |
| SQC-EXT-19 | | | | |
| SQC-EXT-20 | | | | |
| SQC-EXT-21 | | | | |
| SQC-EXT-22 | | | | |
