# 18. Patching arm: round trip, patch sets, mods

Turning edits into something that runs. Every write goes into a **patched copy**: a full copy of
the game folder marked by a `.viwo-patched/` folder; the game folder is only read. CLI arm
`viwo patching`: `repack`, `patch`, `mod`. UI: 09 PATCHED COPY, 14 PATCHES + MODS.

## 18.1 Round trip

```
game folder --extract--> workspace --user edits files--> edit set
     |                                                       |
     +--copy--> patched copy <--pack (plugin strategy)-------+
```

## 18.2 Concepts

- **Provenance map:** `.extraction_metadata/provenance.jsonl`, one line per workspace file: the
  container chain (game file -> archive -> nested archive), the member path, the producing
  backend and the original hash. COLLECT writes it; sort and sanitizer moves rewrite it; a
  damaged line never breaks a capture or a repack.
- **Edit set:** workspace files whose hash differs from their provenance hash (modified), plus
  files placed under `<workspace>/_added/<game-relative path>` (added, written as loose files).
  Deletions are not part of an edit set.
- **Mod strategy:** **override** (loose files in the copy; Unreal `*_P.pak` patch paks; Cyberpunk 2077
  `archive/pc/mod/!viwo_<archive>.archive`) or
  **rebuild** (the container rewritten with its edited members: RPA, PCK, Unity files, zip,
  RPG Maker MV).

## 18.3 Repack (`viwo/core/roundtrip.py`, job kind `repack`)

| Step | What happens |
|------|--------------|
| WARN | a `tos_sensitive` plugin among the owners adds a reminder; nothing is refused (D22) |
| RESOLVE | the edit set from workspace hashes vs the provenance map; an edit whose bytes no longer match the member's format is rejected (same-format rule, `roundtrip_edits.py`) |
| PLAN | per container: override or the owning plugin's `pack_slot()`; shown before anything is written (`--plan`, the 09 view) |
| COPY | copy the game folder to the target; the target must be empty or already a patched copy; a file the OS refuses to read is left out and named |
| PACK | `pack.*` slots write inside the copy only |
| VERIFY | re-extract each packed container through its `unarchive.*` slot: edited members carry the edited hash, untouched members their original hash. A packer with its own `verify` (Unity, RPG Maker MV: no unarchive route back) checks the edited members only and the report says "untouched members were not re-verified". An override packer (`override = True`: Unreal `_P.pak`, Cyberpunk `pack.archive`) writes a separate file holding the edits only; it is verified on the edits, the untouched members stay in the container it loads over |
| REPORT | `<copy>/.viwo-patched/report.json`: plan, edits, backends, verification, warnings; a changed game folder is a warning |

CLI `viwo repack WORKSPACE --plan | --out DIR`; API `POST /api/repack` (`plan: true` answers the
plan, otherwise a job). The game is the one recorded in the workspace's run records.

## 18.4 Pack slots

`pack.rpa` (`rpa-writer`, ViWo writes the pickle index itself), `pack.pck`
(`godotpcktool-pack`; encrypted PCKs need the key), `pack.upak` (`repak-patch`, `_P.pak`;
signed paks may refuse to load: reported, not bypassed), `pack.unity` (`unitypy-pack`, same-format
replacement of TextAsset and Texture2D data), `pack.rpgmaker` (`rpgmv-pack`), `pack.zip`
(`zip-packer`), `pack.archive` (`wolvenkit-pack`, redengine: WolvenKit's console packs the edited
members into `archive/pc/mod/!viwo_<archive>.archive`, which the game loads over its own archives
and, by its name, before other mods; a member known only by its hash keeps it; the packer reads
the archive back through the game's Oodle and compares every edited member). Overwatch has no
packer.

## 18.5 Packer interface

```text
Packer (family pack)
  pack(container, members: {member path: edited file}, ctx) -> Outcome    container inside the copy
  output_for(container) -> Path                                           the file it writes
  verify(output, members, ctx) -> [bad members] | None                    None = re-extract
EnginePlugin.pack_slot(unarchive_slot) -> "pack.<...>" | ""
```

## 18.6 Rules

1. The game folder is never written; all writes go to a target that is empty or carries the
   patched-copy marker; two builds into one target are serialized by the workspace lock.
2. ViWo authors no integrity- or anti-tamper-defeating code (philosophy point 5). When a game
   verifies its data, the report says the copy may not load; working around it is the user's
   choice with third-party tools, under the disclaimer.
3. Same format only; converters (edited PNG back to a Texture2D or `.ctex`) are open.
4. A repack is verified before it is reported as successful.

## 18.8 Binary patch sets (`viwo/core/patchsets.py`, `viwo/core/patch_tools.py`, rung T1)

A patch set is JSON (`*.patch.json`), the user's content:

```json
{"schema": 1, "title": "...", "patches": [
  {"file": "Game.exe", "offset": "0x1a2b", "original": "74 05", "patched": "EB 05"},
  {"file": "Game.exe", "pattern": "74 ?? 8B 45 FC", "at": 0, "patched": "EB"},
  {"file": "Game.exe", "rva": "0x1010", "asm": "jmp 0x401020; nop"}]}
```

| Step | What happens |
|------|--------------|
| RESOLVE | `offset` (file offset; the original bytes must be there), `rva` (through the PE section table), `pattern` (AOB, `??` = any byte; must match exactly once, so it survives updates that move code) |
| PLAN | where each patch lands, its status (`ready`, `already`, `mismatch`, `missing`; the set applies only when every patch is `ready` or `already`), and the disassembly of the touched instructions before and after (capstone); `viwo patch --plan` |
| APPLY | `asm` is assembled at its address by Keystone's `kstool` (a separate process); bytes are written into a patched copy (an existing copy is patched in place, so edits, patches and mods stack); offsets are bounded: a patch never grows the file; bytes already patched are reported `already` |
| VERIFY | the whole file is re-read: every edited range has the new bytes, every other byte is unchanged; the game's binary is untouched |
| EXPORT | into `<copy>/.viwo-patched/`: `<set>.diff.txt` (byte diff), `<set>.aob.patch.json` (an AOB patch set whose patterns are grown until unique in this version), `<set>.report.json`, and the set itself |

Slot `patch.bytes` (`viwo-patcher`) owns the Keystone and capstone dependencies. CLI `viwo patch
GAME SET --plan | --out COPY`; API: job kind `patch` through `POST /api/jobs`.

## 18.9 Mod packages (`viwo/core/mods.py`, rung T2)

A mod is a zip of a patched copy's changed and added files plus `viwo-mod.json`:

```text
viwo-mod.json { schema: 1, name, game, made, viwo, requires[], after[], patches[] (the AOB patch
                sets the copy was built from), files[] { path, original (sha256; empty for an
                added file), sha256 } }
```

- `viwo mod pack GAME OUT.zip --copy COPY [--name N] [--requires A,B] [--after A,B]`.
- `viwo mod check GAME MOD.zip`: per file `fits` (the original matches), `new`, `installed`,
  `adapts` (another game version, but the mod's AOB patches resolve: the update check) or
  `differs`; the mod fits when no file differs.
- `viwo mod apply GAME MOD.zip... --copy COPY`: several mods, ordered with requirements first;
  cycles, missing requirements, duplicate names and two mods writing one file differently (unless
  the later declares `after`) are refused; `adapts` files get the AOB patches, read back.
- API: job kind `mod` through `POST /api/jobs` (`{action, gamePath, mod | mods, copy, name}`).

The in-game half of a mod framework (loader, hook API, overlay, crash handler) is what the pinned
runtime loaders provide (UE4SS, BepInEx, doc 11); ViWo packages and checks, it does not author
hooks.
