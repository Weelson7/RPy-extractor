# 18. Patching arm: round trip, patch sets, mods

Turning edits into something that runs. Every write goes into a **patched copy**: a full copy of
the game folder marked by a `.viwo-patched/` folder; the game folder is only read. CLI arm
`viwo patching`: `repack`, `patch`, `mod`. UI: PATCHED COPY, ASSETS, PATCHES + MODS.

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
  An edited **decoded** file (provenance `decode:<backend>:<source>:<output>`: a PNG, WAV,
  glTF, JSON or `.rpy` DECODE wrote) is part of it through its way back (18.3). Deletions are
  not part of an edit set; a member an encoder replaces (a `.rpyc` by its `.rpy`) is removed
  from the copy by the plan.
- **Mod strategy:** **override** (loose files in the copy; Unreal `*_P.pak` patch paks; Cyberpunk 2077
  `archive/pc/mod/!viwo_<archive>.archive`) or
  **rebuild** (the container rewritten with its edited members: RPA, PCK, Unity files, zip,
  RPG Maker MV). The run's **mode** picks between them where an engine has both (18.3).

## 18.3 Repack (`viwo/core/roundtrip.py`, job kind `repack`)

| Step | What happens |
|------|--------------|
| WARN | a `tos_sensitive` plugin among the owners adds a reminder; nothing is refused (D22) |
| RESOLVE | the edit set from workspace hashes vs the provenance map; an edit whose bytes no longer match the member's format is rejected (same-format rule, `roundtrip_edits.py`); each edited decoded file is traced to the member it was decoded from (`roundtrip_encode.py`, below) |
| PLAN | per container: override or the owning plugin's `pack_slot()`, as `mod` or `overwrite` (below); per edited decoded file the member it becomes, its encoder and the container's packer; shown before anything is written (`--plan`, PATCHED COPY, ASSETS) (`roundtrip_plan.py`) |
| COPY | the game-folder guard first (doc 3.1: the target is not the game, not inside it, does not hold it; also when it is a patched copy that is reused, whatever its marker); copy the game folder to the target; the target must be empty or already a patched copy; a file the OS refuses to read is left out and named |
| ENCODE | each edited decoded file is written in its member's format by the decoder that read it (`Decoder.encode`, doc 8.3), into the job's work folder; a failure is a failed result of its own (the file, the encoder, the reason) and the member is not packed |
| PACK | `pack.*` slots write inside the copy only |
| VERIFY | re-extract each packed container through its `unarchive.*` slot: edited members carry the edited hash (for a decoded file: the encoded bytes), untouched members their original hash, a removed member is absent. A packer with its own `verify` (Unity, RPG Maker MV: no unarchive route back) checks the edited members only and the report says "untouched members were not re-verified". An override packer (`override = True`: Unreal `_P.pak`, Cyberpunk `pack.archive`) writes a separate file holding the edits only; it is verified on the edits, the untouched members stay in the container it loads over |
| REPORT | `<copy>/.viwo-patched/report.json`: plan, edits, backends, verification, warnings; a changed game folder is a warning |

CLI `viwo repack WORKSPACE --plan | --out DIR [--mode mod|overwrite]`; API `POST /api/repack`
(`plan: true` answers the plan, otherwise a job; `mode`, default `mod`). The game is the one
recorded in the workspace's run records. The report's `plan` lists per item `container`,
`slot`, `members`, `drops` (members removed), `mode`, `why` and `ways` (`file`, `member`,
`encoder`, `backend`, `replaces`); `skipped` names every edited file that cannot go back, with
its reason.

**Mod or overwrite** (`--mode`, default `mod`). `mod` prefers what leaves the game's own files
untouched in the copy: an override packer (`Packer.override`), or loose files where the engine
loads them over a container (`EnginePlugin.loose_root`). `overwrite` rewrites the container in
the copy. Where an engine has only one form, the item says which one is used and why. Both
write only into the marked patched copy.

| Engine | `mod` | `overwrite` |
|--------|-------|-------------|
| Ren'Py | loose files under `game/`, which Ren'Py opens before its archives (unless the game sets `config.force_archives`) | the RPA rewritten |
| Unreal, REDengine, Source, KiriKiri, Warscape, Bethesda | the override (`_P.pak`, `!viwo_*.archive`, `custom/` VPK, patch XP3, movie pack, loose `Data/`) | not offered: the override is used, and said |
| Unity, Godot, RPG Maker, Genie, Doom, Electron, zip | not offered: the engine loads nothing over its container; the container is rewritten, and said | the container rewritten |
| loose game files | - | replaced in the copy (a file the game ships loose has no container) |

**The way back of a decoded file.** The provenance origin names the decoder's backend and the
file it read (a batch decoder names its slot: the file is the one whose name starts the
output's, `0000000000001234.xbm` for `0000000000001234.xbm.png`; a file SORT moved is found by
its name). The member it becomes is `Decoder.member_back(member)`, in the source's container
(or loose); the encoder is the backend that decoded it, else one bound in its slot that
encodes. It is skipped, with the reason, when its decoder is one way (`Decoder.one_way`) or
refuses that member (`Decoder.refuses`: a block-compressed DDS, an animated VTF), when
the file it came from came out of a nested container or a wrapper, is gone, or was edited too
(that edit is used), or when another edited file goes back into the same member. A member
`member_back` renames replaces the original: the original is removed from the copy (loose) or
from its archive (a packer with `drops`: `pack.rpa`), and the new file goes loose where the
engine reads it (`loose_root`).

| Decoder | Way back |
|---------|----------|
| `decode.vtf` | PNG to VTF: the original's header (version, flags, reflectivity, thumbnail, data-free resources) with the PNG's size; the image uncompressed, in the original's format when it is an 8-bit-per-channel one, else (DXT1/3/5) BGRA8888, the engine's native 32-bit layout; mipmaps rebuilt when it had them; the CRC resource dropped. An animated, cube or volume texture is refused by name |
| `decode.slp` | PNG sheet to SLP through the game's palette (exact colour, else the nearest): colour lists, player colour lists (palette 16-23), shadows and skips per row, no fills (no run-length optimisation); each frame keeps its size, hotspot and properties; paint outside the frames (the sheet's cells are as large as the largest one) is counted in the result, not kept. Outline pixels, drawn transparent, are not written back |
| `decode.loc` | the edited JSON to the table: version, order and flags kept, removed keys left out, new keys at the end with the table's most common flag |
| `decode.rpyc` | the edited `.rpy` itself, as `<name>.rpy` beside where the `.rpyc` was (an archived one: loose under `game/`); the stale `.rpyc` is removed from the copy or its RPA, so Ren'Py compiles the script on start and the old one neither wins nor loads twice |
| `decode.cr2w` | WolvenKit's console: an edited PNG, DDS, TGA or glTF with `import --keep` beside a copy of the original resource, an edited JSON with `convert deserialize`; capped like the export |
| `decode.image` | PNG to DDS when the original is uncompressed (8-bit channels at 24 or 32 bits in any byte order, 8-bit luminance, DX10 R8G8B8A8/B8G8R8A8): its header with the PNG's size, mipmaps rebuilt. A block-compressed original (BC1-BC7) needs an encoder ViWo does not ship; a cube map, volume or array texture holds several images: both skipped with that reason |
| `decode.audio`, `decode.video`, `decode.bink2` | one way: Wwise, FMOD, CRI, XACT and Bink need their vendors' proprietary encoders |
| `decode.redscripts` | one way: the scripts go back as `.reds` files redscript compiles on start, not wired yet |

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

The formats ViWo reads itself are written back the way their engine loads changes, rebuilt
when the engine loads nothing over its archive, as an override where it does (each read back
after writing):

| Slot | Backend | How |
|------|---------|-----|
| `pack.asar` | `asar-writer` | app.asar rebuilt, header tree kept, Electron's per-file integrity hashes recomputed; `unpacked` members written to `app.asar.unpacked/` |
| `pack.vpk` | `vpk-writer` | override: `<mod>/custom/!viwo_<set>.vpk`, a single-file VPK with the edits (the engine loads `custom/` first); the 30 GB set is never rebuilt |
| `pack.xp3` | `xp3-writer` | override: the next patch archive KiriKiri loads after its own (`patch.xp3`, `patch2.xp3`...; edits of several archives share ViWo's patch; a game's own patch is never rewritten). Each member goes in by its file name, since the engine searches a patch at its root; one name from two folders is said, and a file the game's scripts name with its folder is not changed by a patch |
| `pack.bsa`, `pack.ba2` | `loose-override` | override: loose files in `Data/`, which the engine loads over any archive (Fallout 4 and later need two ini lines; Oblivion, Fallout 3 and New Vegas, BSA 103/104, need archive invalidation: both said); a member whose name Windows cannot hold as a file is not written, and said |
| `pack.pack` | `movie-pack` | override: `data/viwo_<pack>.pack`, a pack of type movie Warscape loads over the release packs; PFH4 games; a PFH5/PFH6 game is refused by name until its layout is verified |
| `pack.rgssad` | `rgssad-writer` | RPG Maker XP/VX (v1) and VX Ace (v3) archives rebuilt, every entry under its own key |
| `pack.drs` | `drs-writer` | Genie DRS rebuilt, tables and entries in place |
| `pack.wad` | `wad-writer` | IWAD/PWAD rebuilt, lumps and markers in order; what the unpacker converted is converted back: a PNG to a Doom picture (grAb offsets kept; a PNG an editor saved without grAb keeps the lump's own) or a flat through the game's palette (the game root's, where extraction found it), a WAV to DMX sound; read back by decoding each new lump as extraction does and comparing it with the edit after the palette mapping |

Not written back yet: TaleWorlds TPAC packages.

## 18.5 Packer interface

```text
Packer (family pack)
  pack(container, members: {member path: edited file}, ctx) -> Outcome    container inside the copy
  output_for(container) -> Path                                           the file it writes
  verify(output, members, ctx) -> [bad members] | None                    None = re-extract
  override: bool       a separate file loaded over the container (the `mod` form)
  drops: bool          a member mapped to None is removed from the container (pack.rpa)
EnginePlugin.pack_slot(unarchive_slot) -> "pack.<...>" | ""
EnginePlugin.loose_root(container) -> game-relative folder | None   loose files loaded over it
Decoder.encodes, one_way, encode(edited, original, out, ctx), refuses(original),
  member_back(member)   doc 8.3
```

## 18.6 Rules

1. The game folder is never written; all writes go to a target that is empty or carries the
   patched-copy marker, and that the game-folder guard passed first (doc 3.1): a marker never
   lets the game itself through, so an install a patched copy was copied over is refused as
   a target of `repack`, `patch`, `mod apply` and the runtime agents; two builds into one
   target are serialized by the workspace lock. A pack attempt that fails leaves no file of
   its own for the next one (doc 8.2).
2. ViWo authors no integrity- or anti-tamper-defeating code (philosophy point 5). When a game
   verifies its data, the report says the copy may not load; working around it is the user's
   choice with third-party tools, under the disclaimer.
3. Same format, or through the decoder's way back (18.3): an edited decoded file is encoded
   into its member's own format first. Unity's exporter takes an edited PNG back into its
   Texture2D itself (`pack.unity`); Godot's `.ctex` from a PNG is open.
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
| RESOLVE | `offset` (file offset; the original bytes must be there), `rva` (through the PE section table), `pattern` (AOB, `??` = any byte; must match exactly once, overlapping matches counted, so `CC CC CC` in four bytes of int3 padding is two matches; it survives updates that move code) |
| PLAN | where each patch lands, its status (`ready`, `already`, `mismatch`, `missing`, `overlap`; the set applies only when every patch is `ready` or `already`), and the disassembly of the touched instructions before and after (capstone); `viwo patch --plan`. Once every patch is located (offset, RVA and AOB alike), two whose byte ranges in one file overlap (however the file's name is spelled) are both `overlap`, each naming both: "patches 1 (0x10-0x11) and 2 (0x11-0x11) write the same bytes" |
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
