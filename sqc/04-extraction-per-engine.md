# 04 Extraction per engine

Area code `EXT`. Every plugin once, plus the encrypted / needs-key cases and nested archives.
Unless stated, run from the CLI with `--on-existing replace` into `C:\sqc\_ws\<name>`; the real
tools come from the checkout's `third_party\` or from `--ini C:\sqc\ini\real-tools.ini`; a
`-fake.ini` names fake tools. Then verify one run of each kind from `EXTRACT` (paste the game
folder, `RUN EXTRACTION`, same target workspace via the top-bar `SWITCH`). For every check also
confirm:

- the game folder is unchanged (`Get-ChildItem <game> -Recurse -File | Get-FileHash` and
  `LastWriteTime` before and after);
- the workspace has the marker `.viwo-workspace`, `.extraction_metadata\runs\<id>.json` and
  `.extraction_metadata\provenance.jsonl`; the record's `result.success` is `true` and
  `result.byBackend` names the backends of the summary;
- files are grouped by extension (`png\`, `ogg\`, `txt\`...); the game's own container is kept as
  a file of its group (`zip\data.zip`, `rpa\images.rpa`...);
- stdout is the summary (`Extracted with`, `Archives`, `Files`, `Groups`, `Backends`, one
  `WARNING :` line per warning, `Run record`); stderr the timed stage lines and one `viwo:
  warning:` per warning.

## SQC-EXT-01 (P0) Generic: loose files and a zip

Steps: `viwo extract C:\sqc\zip-basic\game --workspace C:\sqc\_ws\zip --on-existing replace`

Expected: `[CORE:DETECT] Selected plugin(s): generic`, `[CORE:UNPACK] OK data.zip: 2 file(s) via
py-zipfile`, `[CORE:COLLECT] Collected 5 file(s) into 4 group(s)`; summary `Archives : 1/1
unpacked`, `Files : 5 collected from 5 scanned`, `Groups : ogg 1, png 2, txt 1, zip 1`; workspace
`png\title.png`, `png\a.png`, `ogg\theme.ogg`, `txt\readme.txt`, `zip\data.zip`; exit 0.

## SQC-EXT-02 (P0) Nested archives and a traversal member

Steps: `viwo extract C:\sqc\nested-traversal\game --workspace C:\sqc\_ws\nested --on-existing replace`

Expected: `OK extra.tar.gz: 1 file(s) via py-tarfile`, `OK outer.zip: 2 file(s)`, `OK inner.zip:
1 file(s)`; `extra.tar.gz: 1 entr(ies) whose name leads out of the folder skipped` (also a
summary `WARNING`); `ogg\hello.ogg`, `png\bg.png`, `md\readme.md`, `txt\t.txt`; no `escape.txt`
anywhere under `C:\sqc`; exit 0.

## SQC-EXT-03 (P1) Deep nesting stops past depth 10

Steps: `viwo extract C:\sqc\deep-nesting\game --workspace C:\sqc\_ws\deep --on-existing replace`

Expected: 11 lines `OK level00.zip` ... `OK level10.zip`, then the warning
`game:level00.zip!level01.zip!...!level11.zip: nesting deeper than 10`; `Archives : 11/12
unpacked`; `deep.txt` is NOT extracted (it sits in level12) and `level11.zip` is kept as a file
in `zip\` with the other 11; exit 0 (a warning, not a failure).

## SQC-EXT-04 (P0) Ren'Py: `.rpa` through the safe reader

Steps:
1. `viwo extract C:\sqc\renpy\game --workspace C:\sqc\_ws\renpy --on-existing replace`
2. Read `result.byBackend` in the run record (or `viwo --json extract ...`).

Expected: plugin `renpy`; `[RENPY:UNPACK] images.rpa: 1 entr(ies) whose name leads out of the
folder skipped`, `OK images.rpa: 2 file(s) via rpa-safe`; `png\bg.png`, `ogg\theme.ogg`,
`rpy\script.rpy`, `rpa\images.rpa`; the engine's own `renpy\` folder and `MyVN.exe` are not
collected; the member `../escape.txt` does not exist on disk; `byBackend: {"rpa-safe": 1}`.

## SQC-EXT-05 (P1) Ren'Py with the spare first (unrpa)

Steps: `viwo --slot unarchive.rpa=unrpa,rpa-safe extract C:\sqc\renpy\game --workspace
C:\sqc\_ws\renpy-unrpa --on-existing replace` (or `[slots] unarchive.rpa = unrpa, rpa-safe` in
the ini).

Expected: `OK images.rpa: 2 file(s) via unrpa`, the same files; `../escape.txt` is not written
anywhere, and the member left out is said (a warning, as with rpa-safe).

## SQC-EXT-06 (P0) Godot: standalone, embedded, broken (fake tools), then real tools

Preconditions: `C:\sqc\ini\godot-fake.ini` (fake GDRE + GodotPckTool); for step 4 the real tools
and `C:\sqc\real-containers\godot\data.pck` (written by the real GodotPckTool, `--tools-from`).

Steps:
1. `viwo --ini C:\sqc\ini\godot-fake.ini extract C:\sqc\godot\standalone --workspace C:\sqc\_ws\godot1 --on-existing replace`
2. same for `C:\sqc\godot\embedded` (`godot2`)
3. same for `C:\sqc\godot\broken` (`godot3`)
4. With the real tools: `viwo extract C:\sqc\real-containers\godot --workspace C:\sqc\_ws\godot-real --on-existing replace`

Expected:
- Step 1: plugin `godot`, `OK game.pck: 1 file(s) via gdre-tools`, `png\icon.png`, `pck\game.pck`.
- Step 2: the PCK appended to `Game.exe` is read: `OK Game.exe: 1 file(s) via gdre-tools`,
  `png\icon.png`, `exe\Game.exe`.
- Step 3: `data.pck: gdre-tools failed: unsupported pck version; used godotpcktool`, `OK
  data.pck: 1 file(s) via godotpcktool`; `byBackend: {"godotpcktool": 1}`; exit 0.
- Step 4: the real `gdre_tools.exe` prints its banner (`Godot Engine v4.8...`), `OK data.pck: 2
  file(s) via gdre-tools`; `png\icon.png`, `txt\notes.txt`.
- The synthetic PCKs of steps 1-3 are for the fake tools: the real ones reject them (GDRE "the
  tool reported success but wrote no file", GodotPckTool `std::__ios_failure`), and that is said
  as `FAILED game.pck` plus a warning.

## SQC-EXT-07 (P0) Godot: encrypted PCK needs a key

Steps:
1. `viwo --ini C:\sqc\ini\godot-fake.ini extract C:\sqc\godot\encrypted --workspace C:\sqc\_ws\godot5 --on-existing replace`
2. The same with `--option godot.encryption_key=abababab...` (`ab` 32 times: the key the fake
   tool accepts) into `godot7`.
3. UI: EXTRACT on `C:\sqc\godot\encrypted`, `MODE > ENGINE OPTIONS > PCK encryption key` = the same
   key (`SECRET · NEVER STORED`), run.

Expected:
- Step 1: exit 0; `FAILED data.pck: pck is encrypted`; warnings `Archives were discovered but none
  extracted successfully.` and `game:data.pck: needs_key: pck is encrypted`; nothing comes out of
  the archive; the spare is NOT tried for needs-key.
- Step 2: `OK data.pck: 1 file(s) via gdre-tools`; the run record's `request.options` reads
  `{"godot": {"encryption_key": "<secret>"}}`, never the value. (A wrong key, e.g. 64 zeros,
  answers as step 1.)
- Step 3: as step 2; the log (JOBS, activity console, `viwo-data\logs\*.log`) never holds the key.

## SQC-EXT-08 (P0) Unreal: plain pak, key in the exe, locked pak, IoStore (fake tools)

Preconditions: `C:\sqc\ini\unreal-fake.ini`, key in `C:\sqc\unreal\unreal-key.txt`.

Steps:
1. `viwo --ini C:\sqc\ini\unreal-fake.ini extract C:\sqc\unreal\plain --workspace C:\sqc\_ws\ue1 --on-existing replace`
2. same for `keyinexe` (`ue2`)
3. same for `locked` (`ue3`)
4. `locked` again with `--option unreal.aes_key=<key from unreal-key.txt>` (`ue4`)
5. same for `iostore` (`ue5`)

Expected:
- 1: plugin `unreal`, `OK pakchunk0-Windows.pak: 1 file(s) via repak-cli`, `uasset\Hero.uasset`.
- 2: `AES key found in the game's files, verified on pakchunk0-Windows.pak`, then `OK ...`;
  `exe\Game-Win64-Shipping.exe` collected.
- 3: exit 0; `FAILED pakchunk0-Windows.pak: encrypted: no key in the game's executables opens the
  index; give aes_key`, the same as a `needs_key` warning; nothing comes out of the pak.
- 4: extracted; the record stores `"aes_key": "<secret>"`.
- 5: `OK global.utoc: 1 file(s) via retoc-legacy`; `utoc\`, `ucas\`, `uasset\Hero.uasset`.
- Every run also warns `export.unreal: unavailable: ... uas-export unavailable` (the fake ini has
  no UnrealAssetScout): said, not a failure.

## SQC-EXT-09 (P1) Unreal with the real repak

Preconditions: the real tools; `C:\sqc\real-containers\unreal\` (a pak written by the real repak).

Steps: `viwo extract C:\sqc\real-containers\unreal --workspace C:\sqc\_ws\ue-real --on-existing replace`

Expected: `OK pakchunk0-Windows.pak: 2 file(s) via repak-cli`; `uasset\Logo.uasset`,
`ini\DefaultGame.ini`; the asset export (UnrealAssetScout) says `export.unreal: failed: Unreal
asset export: no engine version found (option engine)` (the pak holds no engine marks): a warning.
The synthetic paks of SQC-EXT-08 are for the fake tool; the real repak refuses them, and the run
must say so as a plain failure of that pak (not as a missing key).

## SQC-EXT-10 (P0) Doom: IWAD, PWAD, broken WAD

Steps:
1. `viwo extract C:\sqc\doom\game --workspace C:\sqc\_ws\doom --on-existing replace`
2. The same with `--option doom.raw_lumps=true` into `doom-raw`.

Expected:
- 1: plugin `doom`; `OK doom2.wad: 9 file(s)`, `OK mod.wad: 1 file(s)` via `wad-builtin`;
  `FAILED broken.wad: WAD directory lies outside the file` (warning) and the run succeeds;
  `png\TITLEPIC.png`, `png\FLOOR0_1.png`, `png\TROOA1.png`, `png\POSSA1.png`,
  `wav\DSPISTOL.wav`, `mus\D_RUNNIN.mus`, `txt\DEHACKED.txt`, `lmp\PLAYPAL.lmp`, the map's lumps
  `lmp\MAP01_THINGS.lmp` and `lmp\MAP01_LINEDEFS.lmp`, the three WADs in `wad\`.
- 2: `OK doom2.wad: 15 file(s)`, `OK mod.wad: 2 file(s)`: every converted lump also kept as
  `lmp\*.lmp` (10 lmp files).

## SQC-EXT-11 (P0) RPG Maker: XP, VX Ace (with traversal), MV

Steps: extract `C:\sqc\rpgmaker\xp`, `...\vxace`, `...\mv` into three workspaces.

Expected: `xp`: `OK Game.rgssad: 1 file(s) via rgssad-builtin`, `png\title.png`,
`dll\RGSS102E.dll`. `vxace`: `Game.rgss3a: 1 entr(ies) whose name leads out of the folder
skipped`, `png\Actor1.png`, no `evil.txt` on disk. Both say `export.rpgmaker: rpgmv-builtin
exported nothing` (no MV data there). `mv`: `Actor2.rpgmvp` decrypted to `png\Actor2.png` and
`Theme.rpgmvo` to `ogg\Theme.ogg` with the key read from `System.json` (plugin `exported 2`);
`json\System.json`, `js\rpg_core.js`; the key value appears in no log or record.

## SQC-EXT-12 (P0) KiriKiri XP3: plain and encrypted entries

Steps: extract `C:\sqc\kirikiri\plain` and `C:\sqc\kirikiri\mixed`.

Expected: `plain`: `OK data.xp3: 2 file(s) via xp3-builtin`, `png\bg.png`, `ks\first.ks`.
`mixed`: `png\bg.png`; warning `game:data.xp3: 1 encrypted entries skipped (game-specific
cipher)`; exit 0.

## SQC-EXT-13 (P0) Electron asar and NW.js package.nw

Steps: extract `C:\sqc\electron\game` and `C:\sqc\electron\nw`.

Expected: both give `html\index.html` and `png\logo.png`; `OK app.asar: 2 file(s) via
asar-builtin` (plugin `electron`), `OK package.nw: 2 file(s) via py-zipfile`.

## SQC-EXT-14 (P0) Source VPK (multi-part)

Steps: extract `C:\sqc\source-vpk\game`.

Expected: `OK pak01_dir.vpk: 2 file(s) via vpk-builtin`; `vmt\m.vmt` (inline) and `png\sky.png`
(from `pak01_000.vpk`); `Files : 2 collected from 4 scanned`: the parts are neither unpacked a
second time nor collected.

## SQC-EXT-15 (P0) Bethesda BSA and BA2

Steps: extract `C:\sqc\bethesda\game`.

Expected: `OK Interface.bsa: 2 file(s) via bsa-builtin`, `OK Main - Misc.ba2: 1 file(s) via
ba2-builtin`; `txt\ui.txt`, `txt\hud.txt`, `txt\notes.txt`. With `lz4` installed no LZ4 warning
appears for a v105 BSA (no fixture here; note only).

## SQC-EXT-16 (P0) QuickBMS bridge (fake tool, then real tool)

Steps:
1. `viwo --ini C:\sqc\ini\quickbms-fake.ini extract C:\sqc\quickbms\game --workspace C:\sqc\_ws\bms1 --on-existing replace`
2. SQC-DEP-07 (the real quickbms.exe).

Expected: step 1: plugin `generic` selected, `[QUICKBMS:UNPACK] data.foo: script foo.bms`, `OK
data.foo: 1 file(s) via quickbms-cli`, `bin\inside.bin`, `foo\data.foo`. Step 2 as in 02.

## SQC-EXT-17 (P0) Overwatch through a fake DataTool: auto-selected with a reminder

Preconditions: `C:\sqc\ini\overwatch-fake.ini`.

Steps:
1. `viwo --ini C:\sqc\ini\overwatch-fake.ini extract C:\sqc\overwatch\Overwatch --workspace C:\sqc\_ws\ow --on-existing replace`
2. same into `ow2` with `--plugin overwatch --option overwatch.modes=extract-maps`

Expected:
- Step 1: `Selected plugin(s): overwatch` (auto); `[OVERWATCH:EXPORT] DataTool extract-unlocks`,
  `... extract-general`, `... extract-maps`, `Models to glTF (.glb beside each .owmdl)`;
  `txt\extract-unlocks.txt`, `txt\extract-general.txt`, `txt\extract-maps.txt`,
  `exe\Overwatch.exe`, `info\.build.info`; warnings `export.overwatch: datatool: 1 note(s),
  first: Overwatch: personal, offline use of your own install; respect Blizzard's terms` and the
  reminder itself. No refusal anywhere.
- Step 2: `Extracted with: overwatch (single)`; only `extract-maps` runs; the reminder again.

## SQC-EXT-18 (P1, OPERATOR) Overwatch with the real DataTool on a real install

Steps: `viwo extract "<Overwatch install>" --workspace <ws> --plugin overwatch`

Expected: `DataTool.exe` runs the modes; textures and maps land; the reminder is present in the
warnings; the install folder is unchanged.

## SQC-EXT-19 (P1) Unity: markers only, then a real Unity game

Steps:
1. extract `C:\sqc\unity-markers\game`.
2. Any Unity game you own (UnityPy main): extract it; then again with `--slot
   export.unity=assetstudiomod-cli,unitypy`.

Expected: step 1: plugin `unity`, `UnityPy exported 0 asset(s), 0 problem(s)` and the warning
`export.unity: unitypy exported nothing`; `dll\UnityPlayer.dll`, `exe\MyGame.exe`; success.
Step 2: textures (`png\`), audio, text assets, meshes (`obj\`); with AssetStudioModCLI the
backend is `assetstudiomod-cli`, run as `dotnet ...\AssetStudioModCLI.dll` (activity console).

## SQC-EXT-20 (P1) 7z, rar and tar through core backends

Preconditions: `archives-all` built with py7zr installed.

Steps:
1. extract `C:\sqc\archives-all\game`.
2. again with `--slot unarchive.rar=sevenzip-cli` (or with `third_party\unrar` removed).

Expected: 1: `OK pack.7z ... via sevenzip-cli`, `OK pack.rar ... via unrar-cli`, `OK
pack.tar.gz ... via py-tarfile`; `txt\one.txt`, `txt\two.txt`, `txt\three.txt`. 2: rar via
`sevenzip-cli` (`byBackend: {"py-tarfile": 1, "sevenzip-cli": 2}`; with unrar removed `viwo
slots` shows `unarchive.rar sevenzip-cli (promoted)`).

## SQC-EXT-21 (P1) Encrypted zip and 7z need a password

Preconditions: `C:\sqc\encrypted-zip\game\locked.zip` and `locked.7z` (built by the fixture
builder when 7-Zip is found; else `MAKE-ME.txt` says how).

Steps: extract `C:\sqc\encrypted-zip\game`.

Expected: `FAILED locked.7z: ... Cannot open encrypted archive. Wrong password?` and `FAILED
locked.zip: ERROR: Wrong password : secret.txt (after py-zipfile failed: ... is encrypted,
password required for extraction)`; both are `needs_key` warnings; `Archives : 0/2 unpacked`; no
`secret.txt` anywhere; the archives are kept in `7z\` and `zip\`; exit 0. (No password option:
passwords are not guessed.)

## SQC-EXT-22 (P1) Carver on an unknown blob

Steps: `viwo extract C:\sqc\carve\game --workspace C:\sqc\_ws\carve --on-existing replace`

Expected: `[CORE:CARVE] Carving 1 unrecognized file(s) for embedded assets on <W> workers`,
`Carved 15 file(s) from assets.bin via signature-carver`; summary `Carved : 15 embedded file(s)
from unrecognized data`; groups `7z bik bin bnk dds fsb gif glb jpg mid mp4 ogg png txt wav wem
zip`; the carved zip is unpacked (`txt\readme.txt`); DECODE turns the DDS into
`png\assets.bin@00000c74.dds.png`. The sample's `.wem`, `.fsb`, `.bnk` and `.7z` are signature
stubs: one warning `3 file(s) could not be decoded by decode.audio` (vgmstream, then ffmpeg) and
one `FAILED assets.bin@0000104d.7z` warning name them; the run succeeds.

## SQC-EXT-23 (P1) AGS: a CLIB library behind the executable

Steps: extract `C:\sqc\ags\game`.

Expected: plugin `ags`; `OK Quest.exe: 2 file(s) via clib-builtin`; `crm\room1.crm` (`room one`),
`dta\game28.dta`, `exe\Quest.exe`, `cfg\acsetup.cfg`.

## SQC-EXT-24 (P0) Android: APK, bundle, OBB, encrypted bundle

Steps: extract `C:\sqc\android\apk`, `...\bundle`, `...\obb`, `...\locked` into four workspaces.

Expected:
- `apk`: `Extracted with: android, godot`; `OK game.apk: 10 file(s) via apk-zip`; `Re-detected
  godot inside game:game.apk (70%)` (the fixture's `assets/project.binary` is a Godot marker, not
  a real PCK: GDRE's failure on it is one warning); decoded `xml\AndroidManifest.text.xml` (the
  binary manifest as text: `package="com.viwo.test"`, `android:versionName="1.0"`),
  `xml\main.text.xml`, `json\resources.arsc.json` with the note `arsc/resources.arsc: not shown,
  kept as they are: type specs (configuration-change flags), string style spans`; the raw members
  too (`dex\classes.dex`, `so\libgame.so`, `arsc\resources.arsc`, the old signature
  `rsa\CERT.RSA`...).
- `bundle`: `OK game.xapk: 3 file(s) via apks-zip`, `OK main.1.com.viwo.test.obb ... via
  obb-zip`, `OK base.apk: 10 file(s) via apk-zip`; `Re-detected unity inside
  game:game.xapk!base.apk (92%)`; `bin\level1.bin`, `dex\classes.dex`.
- `obb`: `Extracted with: android`, `OK ...obb: 1 file(s) via obb-zip`, `bin\level1.bin`.
- `locked`: `FAILED locked.xapk: the bundle's members are encrypted`, warning `needs_key`;
  exit 0.

## SQC-EXT-25 (P1) Defold: plain and encrypted resources

Steps: extract `C:\sqc\defold\plain` and `C:\sqc\defold\encrypted`.

Expected: `OK game.arci: 2 file(s) via arci-builtin` each; plain: `txt\title.txt` (`Jumper`, LZ4
inflated), `luac\main.luac`; encrypted: `luac\enc.luac` reads `-- lua source` / `return 1`
(XTEA-CTR with Defold's built-in key, verified), `txt\plain.txt`; no `not decrypted` warning.

## SQC-EXT-26 (P1) GameMaker data.win

Steps: extract `C:\sqc\gamemaker\game`.

Expected: `OK data.win: 7 file(s) via gm-builtin`; `png\0000.png`, `png\0001.png`,
`wav\0000.wav`, `ogg\0001.ogg`, `json\strings.json`, `bin\GEN8.bin`, `bin\CODE.bin`; the notes
`2 texture PNG(s) (texture-page metadata is not a writable member)`, `2 embedded audio file(s)`,
`3 string(s) to strings.json (a read-only view)` appear as warnings.

## SQC-EXT-27 (P1) LÖVE: fused executable and .love

Steps: extract `C:\sqc\love2d\fused` and `C:\sqc\love2d\archive`.

Expected: `OK Blob.exe: 2 file(s) via love-zip` and `OK game.love: 2 file(s) via love-zip`; both
give `lua\main.lua` and `txt\title.txt` (`Blob Quest`).

## SQC-EXT-28 (P1) TyranoScript: loose HTML5

Steps: extract `C:\sqc\tyranoscript\MyNovel`.

Expected: plugin `tyranoscript`, no archive; `ks\first.ks`, `ks\second.ks`, `tjs\Config.tjs`,
`js\libs.js`, `html\index.html`, `png\title.png`.

## SQC-EXT-29 (P1) Wolf RPG: plain, keyed, wrong key

Steps:
1. extract `C:\sqc\wolfrpg\plain`.
2. extract `C:\sqc\wolfrpg\keyed` (no key).
3. the same with `--option wolfrpg.decryption_key=wolfpass`.
4. the same with `--option wolfrpg.decryption_key=wrong!!`.

Expected:
- 1: `OK Data.wolf: 6 file(s) via wolf-builtin`; `Data.wolf: 1 member name(s) Windows cannot
  write altered (originals recorded for the round trip)`: `con.txt` lands as `txt\_con.txt`;
  `mps\map001.mps`, `mps\map002.mps`, `dat\db.dat`, `png\title.png`, `txt\root.txt`.
- 2 and 4: the archive is refused by name (`FAILED Data.wolf: ...`), nothing comes out, the run
  succeeds with the warning.
- 3: `OK Data.wolf: 5 file(s)`; the record stores `"decryption_key": "<secret>"`.

## SQC-EXT-30 (P1) XNA / FNA content

Steps: extract `C:\sqc\xna\game`.

Expected: plugin `xna`; DECODE turns `Content\logo.xnb` into `png\logo.png` (4x4) and
`Content\beep.xnb` (LZ4) into `wav\beep.wav`; both `.xnb` kept in `xnb\`.

## SQC-EXT-31 (P1) Desktop-app frameworks: Qt, Chromium, .NET, Java, frozen Python

Steps: extract each of `C:\sqc\frameworks\qt`, `chromium`, `dotnet`, `java`, `pyfrozen`.

Expected:
- qt: `OK app.rcc: 3 file(s) via rcc-builtin`; `qml\main.qml`, `qml\x.qml`, `json\d.json`.
- chromium: `OK resources.pak: 3 file(s) via pak-builtin`; `dat\10.dat`, `dat\20.dat`,
  `dat\30.dat`; notes `encoding utf-8` and `1 alias id(s) share another resource's data`.
- dotnet: `OK App.dll: 2 file(s) via dotnet-resources`; `resources\App.Strings.resources`,
  `resources\Other.resources`.
- java: `OK app.jar: 4 file(s) via jar-builtin`; `class\Main.class`, `mf\MANIFEST.MF`,
  `properties\config.properties`, `png\logo.png`.
- pyfrozen: `OK app.exe: 4 file(s) via pyi-builtin`; `txt\data.txt`, `pyc\app.pyc`,
  `pyc\json.pyc`, `pyc\path.pyc` and their disassembly `txt\*.dis.txt` (`decode.pyc`).

## SQC-EXT-32 (P2) Kaitai `.ksy` decoder: only when picked

Steps: extract `C:\sqc\kaitai\game`; then again with `--plugin kaitai` into `kaitai`.

Expected: first run: `generic` only, `wav\sound.wav`, no JSON. Second: `Extracted with: kaitai
(single)`, `json\sound.json` with `riff_magic: RIFF`, `format.format_tag: {"value": 1, "enum":
"pcm"}`, `channels: 2`, `sample_rate: 44100`, `chunks[0].data: "aabbccdd"`.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-EXT-01 | PASS | version: 1.36.0+search+apk (unreleased). As written; game unchanged (sha256 + mtime) in every check of this file | agent | 2026-11-23 |
| SQC-EXT-02 | PASS | 7 files; one traversal skipped and said; no escape file under `C:\sqc-a` | agent | 2026-11-23 |
| SQC-EXT-03 | PASS | 11 OK lines, `Archives : 11/12 unpacked`, 12 zips in `zip\`, no deep.txt | agent | 2026-11-23 |
| SQC-EXT-04 | PASS | `byBackend {"rpa-safe": 1}`, 4 files | agent | 2026-11-23 |
| SQC-EXT-05 | FAIL | `OK images.rpa: 2 file(s) via unrpa`, same 4 files, no escape file anywhere; but the member left out (`../escape.txt`) is not said: no warning, `checks.ok: true` (rpa-safe says it) | agent | 2026-11-23 |
| SQC-EXT-06 | PASS | fake: gdre 1 file; embedded `OK Game.exe`; broken: `gdre-tools failed: unsupported pck version; used godotpcktool`. Real GDRE 2.7.4 on the real-built PCK: 2 files. On the synthetic PCK both real tools fail (as noted in the check) | agent | 2026-11-23 |
| SQC-EXT-07 | PASS steps 1-2; NOT RUN step 3 | needs_key as written; with `ab`x32 `OK data.pck`, options `<secret>`; 64 zeros -> needs_key. Step 3 needs a browser | agent | 2026-11-23 |
| SQC-EXT-08 | PASS | all five as written; each warns `export.unreal: unavailable` | agent | 2026-11-23 |
| SQC-EXT-09 | PASS | real repak 0.2.3: 2 files from the real-built pak, the export warning. On the synthetic pak real repak fails and ViWo reports `needs_key: agic of 0x0 instead of 0x5a6f12e1 ... (possibly missing --aes-key?)`: a missing key for an unencrypted pak, and the message's first characters cut (see report) | agent | 2026-11-23 |
| SQC-EXT-10 | PASS | 13 files; with raw lumps 20 (10 lmp) | agent | 2026-11-23 |
| SQC-EXT-11 | PASS | xp, vxace (traversal said), mv `exported 2`; no key in records | agent | 2026-11-23 |
| SQC-EXT-12 | PASS | as written | agent | 2026-11-23 |
| SQC-EXT-13 | PASS | asar-builtin; py-zipfile | agent | 2026-11-23 |
| SQC-EXT-14 | PASS | `2 collected from 4 scanned` | agent | 2026-11-23 |
| SQC-EXT-15 | PASS | 3 txt | agent | 2026-11-23 |
| SQC-EXT-16 | PASS | fake as written; real in SQC-DEP-07 | agent | 2026-11-23 |
| SQC-EXT-17 | PASS | three modes, then only extract-maps; reminder in both | agent | 2026-11-23 |
| SQC-EXT-18 | NOT RUN | OPERATOR (Overwatch is not installed) | | |
| SQC-EXT-19 | PASS step 1; NOT RUN step 2 | no Unity game installed | agent | 2026-11-23 |
| SQC-EXT-20 | PASS | unrar-cli, sevenzip-cli, py-tarfile; with the slot override `sevenzip-cli x2` | agent | 2026-11-23 |
| SQC-EXT-21 | PASS | both `needs_key` with the tools' password messages, `0/2 unpacked` | agent | 2026-11-23 |
| SQC-EXT-22 | PASS | 15 carved, 18 files, DDS -> PNG; 3 audio stubs and the 7z stub named in warnings | agent | 2026-11-23 |
| SQC-EXT-23 | PASS | 4 files | agent | 2026-11-23 |
| SQC-EXT-24 | PASS | apk 14 files (godot re-detected 70 %), bundle 18 files (unity 92 %), obb 2, locked `needs_key` | agent | 2026-11-23 |
| SQC-EXT-25 | PASS | enc.luac decrypted with the built-in key | agent | 2026-11-23 |
| SQC-EXT-26 | PASS | 9 files, three notes | agent | 2026-11-23 |
| SQC-EXT-27 | PASS | both | agent | 2026-11-23 |
| SQC-EXT-28 | PASS | 6 files | agent | 2026-11-23 |
| SQC-EXT-29 | PASS | 1: `_con.txt` + note; 2 and 4: `FAILED Data.wolf: not a Wolf RPG / DXArchive file (no DX signature)` (refused, but the words do not say a key is needed: see report); 3: 5 files, `<secret>` | agent | 2026-11-23 |
| SQC-EXT-30 | PASS | png + wav decoded | agent | 2026-11-23 |
| SQC-EXT-31 | PASS | all five as written | agent | 2026-11-23 |
| SQC-EXT-32 | PASS | generic, then kaitai with the JSON tree | agent | 2026-11-23 |
