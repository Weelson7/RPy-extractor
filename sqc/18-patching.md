# 18 Patching arm: patch sets and mods (`viwo patch`, `viwo mod`, PATCHES + MODS)

Area code `PAT`. Contract doc 18.8 (patch sets, slot `patch.bytes` / `viwo-patcher`, its AOB
signature function `patch.sig`) and 18.9 (mods). Everything writes into a ViWo patched copy
(`.viwo-patched\` inside it); the game folder is only read. Live patching of the same set behind an
isolation boundary is in 22-isolation.

Game: `<repo>\Test-games\chocolate-doom\engine` (games.md: Chocolate Doom 3.1.0, a 32-bit PE,
image base `0x400000`, entry point RVA `0x13e0`). Tools: `viwo install keystone capstone`
(Keystone's `kstool` assembles, capstone disassembles). The patch set `C:\sqc\cd.patch.json`:

```json
{"schema": 1, "title": "sqc chocolate", "patches": [
 {"file": "chocolate-doom.exe", "offset": "0x7bf39", "original": "43 68", "patched": "58 58"},
 {"file": "chocolate-doom.exe", "pattern": "43 68 6F 63 6F 6C 61 74 65 20 44 6F 6F 6D 20 69", "at": 0, "patched": "59"},
 {"file": "chocolate-doom.exe", "rva": "0x13e0", "asm": "nop"}]}
```

(`0x7bf39` and the pattern are two `Chocolate Doom` strings found by `viwo search`, 21-search.)
Hash the game folder before and after every check (`Get-FileHash` of `chocolate-doom.exe`).

## SQC-PAT-01 (P0) A patch set: plan, apply, re-apply, refuse

Steps:
1. `viwo patch <game> C:\sqc\cd.patch.json --plan`
2. `viwo patch <game> C:\sqc\cd.patch.json --out C:\sqc\_ws\patched`
3. The same command again (`--json`).
4. `C:\sqc\bad.patch.json` = one entry `{"file": "chocolate-doom.exe", "offset": "0x7bf39", "original": "30 30", "patched": "31 31"}`; `viwo patch <game> C:\sqc\bad.patch.json --out C:\sqc\_ws\bad`

Expected:
- 1: three results `ready`: offset 507705 old `43 68` new `58 58`; offset 507765 (the pattern) old
  `43` new `59`; offset 2016 (RVA `0x13e0`) old `c7` new `90`; `ok: true`.
- 2: the same results with `written: true`, then `ok: true`, `notCopied: []`, `verified: true`;
  `C:\sqc\_ws\patched` is a full copy with `.viwo-patched\` holding `cd.patch.json`,
  `cd.diff.txt`, `cd.aob.patch.json` and `cd.patch.report.json`; the game's exe hash unchanged.
- 3: every status `already`, `verified: true` (the existing copy is patched in place).
- 4: `viwo: failed: the patch set does not fit this game: chocolate-doom.exe: mismatch (found 43 68
  at 0x7bf39)`, exit 1, `C:\sqc\_ws\bad` not created.

## SQC-PAT-02 (P1) Assembly and disassembly in a plan

Steps: read the third result of SQC-PAT-01 step 1.

Expected: `disasm.old` = `4013e0: mov dword ptr [0x4d6060], 1`, `disasm.new` = `4013e0: nop`
(assembled for the file's architecture, 32-bit here, by `kstool`); the first result's disassembly
reads the string bytes as code (`47e339: inc ebx`...), as capstone does. Without `kstool` an `asm`
entry answers `unavailable` with the install hint.

## SQC-PAT-03 (P0) Mods: pack, check, apply

Steps:
1. `viwo --json mod pack <game> C:\sqc\cd.zip --copy C:\sqc\_ws\patched --name cd`; list the zip.
2. `viwo --json mod check <game> C:\sqc\cd.zip`; the same on `C:\sqc\_ws\patched`.
3. `viwo --json mod apply <game> C:\sqc\cd.zip --copy C:\sqc\_ws\second`

Expected: 1: `files: 1`; the manifest: `name: cd`, `game: engine`, `viwo: 1.36.0`, `patches:
["cd.aob.patch.json"]`, the exe with its `original` and new `sha256`; the zip holds
`viwo-mod.json`, `files/chocolate-doom.exe`, `patches/cd.aob.patch.json`. 2: `fits: true`, state
`fits` on the game, `installed` on the copy. 3: `order: ["cd"]`, `applied: 1`; the second copy's exe
is byte-identical to the patched copy's.

## SQC-PAT-04 (P0) The update check: a mod on another game version

Steps: copy the game's exe to `C:\sqc\game-v2\` and flip its last byte (`python -c "import sys;p=sys.argv[1];d=bytearray(open(p,'rb').read());d[-1]^=0xFF;open(p,'wb').write(d)" C:\sqc\game-v2\chocolate-doom.exe`);
`viwo --json mod check C:\sqc\game-v2 C:\sqc\cd.zip`; `viwo --json mod apply C:\sqc\game-v2 C:\sqc\cd.zip --copy C:\sqc\_ws\v2copy`.

Expected: state `adapts`, `fits: true`; apply `applied: 1`: the copy has `XX` at `0x7bf39`, `Y` at
`0x7bf75`, `90` at `0x7e0` (the AOB patches resolved in the new version) and keeps v2's own last
byte.

## SQC-PAT-05 (P0) Load order, conflicts, requirements

Steps:
1. `C:\sqc\ww.patch.json` = `{"file": "chocolate-doom.exe", "offset": "0x7c0c8", "original": "43 68", "patched": "5A 5A"}` (another string of the same file); apply it into `C:\sqc\_ws\ww`; pack it as `ww.zip` (`--name ww`) and as `ww2.zip` (`--name ww2 --after cd`).
2. `viwo mod apply <game> C:\sqc\cd.zip C:\sqc\ww.zip --copy C:\sqc\_ws\sixth`
3. `viwo --json mod apply <game> C:\sqc\ww2.zip C:\sqc\cd.zip --copy C:\sqc\_ws\seventh`
4. Pack a mod with `--requires x` alone (`needx.zip`); apply it.

Expected: 2: `viwo: refused: mods conflict: chocolate-doom.exe: cd and ww`, exit 3, no copy made.
3: `order: ["cd", "ww2"]` (requirements and `after` first), `applied: 2`, states `fits`, `adapts`;
the copy has `XX` at `0x7bf39` and `ZZ` at `0x7c0c8`. 4: `viwo: invalid_request: mod needx requires
x, which is not in the list`, exit 2.

## SQC-PAT-06 (P0) Overlaps and ambiguous patterns are refused in the plan

Steps:
1. `C:\sqc\ov.patch.json`: `{"file": "chocolate-doom.exe", "offset": "0x7bf39", "original": "43 68", "patched": "58 58"}` and `{"file": "CHOCOLATE-DOOM.EXE", "offset": "0x7bf3a", "patched": "00"}`; `viwo --json patch <game> C:\sqc\ov.patch.json --plan`
2. `C:\sqc\many.patch.json`: `{"file": "chocolate-doom.exe", "pattern": "00 00 00", "at": 0, "patched": "01"}`; `--plan`

Expected: 1: both entries `overlap` with `patches 1 (0x7bf39-0x7bf3a) and 2 (0x7bf3a-0x7bf3a) write
the same bytes` (the file name's case does not matter), `ok: false`. 2: `mismatch` with `pattern
matches 127707 times (needs exactly one)`.

## SQC-PAT-07 (P1) PATCHES + MODS view

Preconditions: `viwo serve`.

Steps: PATCHING arm > PATCHES + MODS.
1. GAME FOLDER `<game>`, PATCH SET FILE `C:\sqc\cd.patch.json`, `CHECK`.
2. PATCHED COPY `C:\sqc\_ws\se-other` (a folder holding `mine.txt`), `APPLY`.
3. PATCH SET FILE `C:\sqc\bad.patch.json`, PATCHED COPY `C:\sqc\_ws\ui-bad`, `APPLY`.
4. MOD PACKAGE: switch `CHECK` / `PACK` / `APPLY` and read the labels.

Expected: 1: panel `PATCH CHECK` with `OK`, `TITLE sqc chocolate`, the table `FILE STATUS OFFSET
REASON OLD NEW` with the three `ready` rows. 2: error box `PATCH APPLY FAILED // REFUSED FOR SAFETY`,
`code: refused`, nothing written into the folder. 3: `PATCH APPLY FAILED // IT DID NOT WORK`, the
mismatch message, `code: failed`. 4: the labels follow the action (`MOD ZIP`, `MOD ZIP TO WRITE` +
`NAME`, `MOD ZIPS IN LOAD ORDER`).

## Results

| ID | Result | Version | Notes | Tester | Date |
|----|--------|---------|-------|--------|------|
| SQC-PAT-01 | PASS | 1.36.0+search+apk (unreleased) | Chocolate Doom 3.1.0; Keystone and capstone of the pinned set; game hash unchanged. The report file is `cd.patch.report.json`, doc 18.8 says `<set>.report.json` | agent | 2026-11-23 |
| SQC-PAT-02 | PASS | 1.36.0+search+apk (unreleased) | `nop` over a 10-byte `mov`: the plan's new disassembly shows only `nop`, not the bytes left behind | agent | 2026-11-23 |
| SQC-PAT-03 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-PAT-04 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-PAT-05 | PASS | 1.36.0+search+apk (unreleased) | Seen beyond the steps: two mods writing the same bytes with `--after` (zz2 after cd, both at `0x7bf39`) fail with `zz2 was made for another version: chocolate-doom.exe` after the copy was made and cd written into it: a half-applied copy is left | agent | 2026-11-23 |
| SQC-PAT-06 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-PAT-07 | PASS (steps 1-3) / NOT RUN (step 4) | 1.36.0+search+apk (unreleased) | steps 1-3 in headless Edge; step 4 needs eyes (labels only) | agent | 2026-11-23 |
