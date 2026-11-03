# 18 Patching arm (`viwo patch`, `viwo mod`)

Area code `PAT`. Everything writes into a ViWo patched copy (`.viwo-patched/` inside it); the game
folder is only read (check its hashes before and after).

## SQC-PAT-01 (P0) A patch set: plan, apply, re-apply, refuse
1. Write `hdr.patch.json`: `{"schema": 1, "patches": [{"file": "ULTRAKILL_Data/boot.config",
   "pattern": "<hex of hdr-display-enabled=0>", "at": 20, "patched": "31"}]}`.
2. `viwo patch Test-games\ultrakill-prelude hdr.patch.json --plan`: status `ready`, offset 60.
3. `viwo patch ... --out C:\sqc\_ws\patched`: `verified: true`; the copy reads
   `hdr-display-enabled=1`, the install still `=0`; `.viwo-patched\hdr.diff.txt` and
   `hdr.aob.patch.json` exist.
4. The same command again: status `already` (nothing rewritten).
5. Change `patched` to `32` and `original` to `30` on an offset patch that does not match:
   `failed: the patch set does not fit this game`, no copy made.

## SQC-PAT-02 (P1) Assembly and disassembly in a plan
Preconditions: `viwo install keystone capstone`.
1. `{"file": "ULTRAKILL.exe", "rva": "0x1260", "asm": "int3"}` with `--plan`: offset `0x660`,
   new `cc`, `disasm.old` = `140001260: sub rsp, 0x28`, `disasm.new` = `140001260: int3`.

## SQC-PAT-03 (P0) Mods: pack, check, adapt, order, conflicts
1. `viwo mod pack Test-games\ultrakill-prelude hdr.zip --copy C:\sqc\_ws\patched --name hdr`:
   one file, `patches\hdr.aob.patch.json` inside the zip.
2. `viwo mod check Test-games\ultrakill-prelude hdr.zip`: `fits`; on the patched copy:
   `installed`.
3. `viwo mod apply Test-games\ultrakill-prelude hdr.zip --copy C:\sqc\_ws\second`: one file
   applied; the second copy launches (`viwo capture ... --auto 30` on it captures a frame).
4. Two mods writing one file differently: `refused: mods conflict`, until the later is packed
   with `--after <first>`. A mod packed with `--requires x` alone: `requires x, which is not in
   the list`.

| ID | Result | Version | Notes |
|----|--------|---------|-------|
| SQC-PAT-01 | PASS | 1.4.5 | agent, 2026-11-03 (ULTRAKILL boot.config) |
| SQC-PAT-02 | PASS | 1.4.6 | agent, 2026-11-03 (ULTRAKILL.exe entry point) |
| SQC-PAT-03 | PASS | 1.4.6 | agent, 2026-11-03: steps 1-3 on ULTRAKILL; step 4 by tests/test_mods.py |
