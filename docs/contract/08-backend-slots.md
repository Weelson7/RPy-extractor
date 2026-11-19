# 8. Slots and backends (main + spare)

Every tool ViWo drives is reached through an **interface** and bound into a **slot**. A slot has
one **main** backend and, where it makes sense, one **spare**. No stage calls a tool directly; it
asks its slot (`viwo/contracts/slots.py`, `viwo/core/wiring/binder.py`,
`viwo/core/pipeline/failover.py`). Wiring is resolved at boot from the slot defaults and the
ini's `[slots]` section (doc 9).

```
 Stage --uses--> Slot "unarchive.7z"  (interface: Unarchiver)
                   main : sevenzip-cli   (7z / 7z.exe)
                   spare: py7zr          (pip package)
```

## 8.1 Concepts

```text
SlotDefinition
  slot_id        "<family>.<name>", e.g. "unarchive.rpa"
  family         unarchive | export | carve | decode | probe | media.encode | pack | patch
                 | analysis | handoff | attach | capture | runtime | keys
  owner          "core" or the plugin id that introduces it
  default_main, default_spare
  suffixes, magic, identify(path, head, tail) -> Match    how UNPACK and DECODE pick the slot

Backend
  backend_id, owner, families
  license (SPDX), isolation inprocess|subprocess, network none|download|any,
  parses_untrusted_in_process, self_check_args, requires: [DependencySpec]
  available(os) -> (ok, reason)        side-effect free
  self_check(os) -> (ok, reason)       `viwo slots --check`: available() plus a real run of
                                       every CLI tool (answers within 8 s)

SlotBinding { slot_id, main, spare, promoted, source: default|ini, reasons }
```

A backend may serve no slot and exist only to declare a dependency so preflight, SYSTEM and
`viwo install` see it: `frida-trace` (`viwo trace`, `viwo hook`) and `soundcard-loopback` (`viwo record`),
each the one tool for its job.

## 8.2 Failover and resolution

Three policies, per slot (`[slot_policy]`, doc 9.2). `failover` (default): run main; if the
outcome is retryable, run the spare on the same item. `main_only`: the spare is never bound,
so it is neither promoted when the main is missing (the slot is then unbound and says why)
nor run after the main failed. `supplement`: both run, the spare adding what the main left
(`pipeline/failover.py` `supplement`). When the main succeeded (not promoted, not cancelled),
its output folder is set aside, the spare runs into the same folder emptied, and every file
the spare wrote under a relative path the main did not write joins the main's output (the
main's bytes win; every name through `member_path`, no link followed); the added files'
entries in the spare's names record and export map are merged into the main's. The outcome
counts the added files and its notes say how many, or why the spare failed (the main's output
stands); a spare that adds nothing says nothing. A main that fails falls over to the spare as
under `failover`. Only the families that write a folder of files take it (`unarchive`,
`export`, `carve`, `decode`); on another slot (a packer writing one container, a probe) it is a
boot problem and `failover` is used. Outcome kinds (`OutcomeKind`): `ok`, `unavailable`
(retry), `failed` (retry; a backend exception counts as failed), `needs_key` (never retried).

**A fresh folder per attempt** (`run_with_failover(binding, backends, call, *, into, cancel)`,
both keywords required). `into` is the folder the call writes: it is emptied before every
attempt, so a spare never writes beside the truncated files and the export map a failed main
left, and nothing of a failed attempt is collected or mapped into provenance. Every stage
passes its own: UNPACK the archive's folder, EXPORT the plugin's staging, CARVE the blob's
folder, DECODE the file's or the batch's folder, analysis its `.analysis/<backend>/<key>/`,
capture its staging, the round trip its staging (and the re-extraction folder of VERIFY); a
pack attempt also removes the separate output file (an override, a patch archive) an earlier
attempt made in the copy, when it was not there before. Only a call that writes nothing (a
probe) passes `into=None`. **No spare after a cancel:** `cancel` is the job's token; when it is
set while the main runs, the spare never starts, in every stage.

Binding at boot:

1. An ini entry naming an unknown backend, or one that does not serve the slot's family, is a
   problem for that entry only; the default is used.
2. A default spare whose plugin is switched off is simply absent.
3. If the main is available it stays main; if not and the spare is, the spare is **promoted**
   (shown in `viwo slots` and SYSTEM); if neither is, the slot is **unbound** and stages that
   need it report `unavailable` with the install hint. The app does not crash.

**Never silent (owner's rule):** when the spare runs, the outcome carries `fallback` ("<main>
<kind>: <error>; used <spare>"); when both fail, the error names both. Every stage turns it into
a warn event (CLI stderr, also with `--json`; the GUI job log) and, where it keeps warnings, into
the result. An export that is `ok` but wrote nothing, or returned notes, says so too.
An unpacker counts every entry it skips by reason (an unsafe name, a missing part file, an
archive cut short) and returns the counts as notes; the unpack stage logs each note as a warning
and lists it among the run's warnings. A declared size of 0 never means "inflate without a
limit", and a stored segment past the end of its archive fails rather than writing a stub.

Every result records which backend produced it: `byBackend` (unpack) and
`plugins[].exportedByTool` (export).

## 8.3 Interfaces

```text
Unarchiver   (unarchive)    extract(archive, dest, ctx) -> Outcome
Exporter     (export)       export(ctx) -> Outcome                  into ctx.staging
Carver       (carve)        carve(path, dest, ctx) -> Outcome       never decrypts
Decoder      (decode)       decode(path, dest, ctx) -> Outcome      viewable copies
                            the way back (doc 18.3), optional:
                            encodes: bool; one_way: the reason given when it does not
                            encode(edited, original, out, ctx) -> Outcome   `out` in the
                              format of `original` (the file decode read) with the content
                              of `edited` (a file decode wrote, then the user changed)
                            refuses(original) -> reason | ""   a cheap look (the header): the
                              plan names such a member as skipped (a BC7 DDS)
                            member_back(member, out) -> member   the same, or the one the
                              engine reads instead (`.rpyc` -> `.rpy`), which then replaces
                              it; `out`: the edited file's path in the decoder's output
                            adds: bool   member_back names a new loose file beside the member,
                              which stays (redscript sources); back_note: said in the plan
                            lossless: bool (default true)   what decode writes holds all it
                              read; false for a re-encode (Bink to MP4): the sanitizer's
                              open-format copies use only lossless ones (doc 5.1)
Prober       (probe)        probe(path, ctx) -> Outcome             facts in notes ("format=png")
MediaEncoder (media.encode) the merger's ffmpeg builds and the sanitizer's transcodes (doc
                            5.1 phase 3); honours max_command_length
Packer       (pack)         pack(container, members, ctx); output_for(container); verify(...);
                            override (a separate file), drops (None removes a member)
Patcher      (patch)        byte writes, Keystone assembly, capstone disassembly (doc 18.8)
Analyzer     (analysis)     analyze(target, ctx)                    doc 6
Handoff      (handoff,      prepare(target, ctx) -> LaunchSpec | Outcome      8.3a
              attach)       the same interface; `attach` runs on the live game (doc 11.2)
capture      (capture)      RenderDoc capture and harvest           doc 11
RuntimeAgent (runtime)      accepts, install, finished, outputs     doc 11.2
KeyFinder    (keys)         candidates(game_root, ctx) -> [bytes]   doc 14.2 #4: in memory only;
                            the plugin verifies each before use (D18); reached as ctx.keys(slot)
```

## 8.3a Interactive handoff: "continue in &lt;tool&gt;"

GUI-first tools are not driven headless; ViWo prepares the target and hands off
(`viwo/contracts/analysis.py` `Handoff`, `LaunchSpec { argv, cwd, env }`).

| Slot | Backend | Label | Accepts | What `prepare` does |
|------|---------|-------|---------|---------------------|
| `handoff.native` | `ghidra-gui` | Continue in Ghidra | `native_binary` | opens the project of the headless run, JVM started directly |
| `attach.debug` | `x64dbg-gui` | Continue in x64dbg | `native_binary` | attaches x64dbg (x32dbg for 32-bit PEs) to the game's running process (`-p PID`), or starts the game's own executable under it, stopping at the system breakpoint |
| `attach.memory` | `cheatengine-gui` | Continue in Cheat Engine | `native_binary` | writes a ViWo table that attaches to the game's process when it runs, then opens Cheat Engine |

Rules:

- The tool runs as a **tracked child** (`ProcessRunner.launch`, `core/handoff.py`): it is killed
  when ViWo exits; the CLI waits for it (`viwo analyze --open`, `viwo attach`).
- Every first-run question of the tool is pre-answered off screen before launch (Ghidra user
  agreement and tips, x64dbg release notes, Cheat Engine CEShare and table-Lua prompts), only when
  the user has not answered it; a value that cannot be written is said.
- `handoff.*` slots are the static arm's (ANALYSIS) and never run the game; `attach.*` slots work
  on the game itself and are the dynamic arm's (RUNTIME, doc 11.2). Both are declared and
  overridable like any backend.

## 8.4 Default slot table

`viwo slots` prints the effective table; `viwo config generate` writes it into the distros.

**Unarchive** (UNPACK picks by identifier, then longest suffix, then magic, then a `fallback`
slot's identifier; doc 2.5):

| Slot | Owner | Main | Spare | Notes |
|------|-------|------|-------|-------|
| `unarchive.zip` | core | `py-zipfile` | `sevenzip-cli` | `.zip`, `.nw` |
| `unarchive.tar` | core | `py-tarfile` | `sevenzip-cli` | `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz`, `.tbz2`, `.tar.xz`, `.txz` |
| `unarchive.7z` | core | `sevenzip-cli` | `py7zr` | |
| `unarchive.rar` | core | `unrar-cli` | `sevenzip-cli` | |
| `unarchive.rpa` | renpy | `rpa-safe` | `unrpa` (GPL-3.0, subprocess) | restricted unpickler (D11) |
| `unarchive.unitypackage` | unity | `py-tarfile` | `sevenzip-cli` | |
| `unarchive.pck` | godot | `gdre-tools` | `godotpcktool` | `GDPC` head or exe trailer; embedded PCKs carved first |
| `unarchive.upak` | unreal | `repak-cli` | `quickbms-cli` (when the quickbms plugin is on and a `.pak` script exists) | AES per D18 |
| `unarchive.utoc` | unreal | `retoc-legacy` | `retoc-unpack` | IoStore `.utoc`/`.ucas` |
| `unarchive.wad` | doom | `wad-builtin` | - | |
| `unarchive.rgssad` | rpgmaker | `rgssad-builtin` | - | `.rgssad`, `.rgss2a`, `.rgss3a` |
| `unarchive.wolf` | wolfrpg | `wolf-builtin` | - | `DX` head; `.wolf` (DXArchive v6); a key verified against the header |
| `unarchive.xp3` | kirikiri | `xp3-builtin` | - | |
| `unarchive.love` | love2d | `love-zip` | - | `.love` with a zip head; an `.exe` whose tail is a zip end record, `love.dll` beside it |
| `unarchive.clib` | ags | `clib-builtin` | - | `CLIB\x1a` head; an executable with the CLIB tail signature |
| `unarchive.arci` | defold | `arci-builtin` | - | `.arci`, with its `.arcd` and `.dmanifest`; LZ4 through the `lz4` pin |
| `unarchive.asar` | electron | `asar-builtin` | - | |
| `unarchive.vpk` | source | `vpk-builtin` | - | identifier for `_dir.vpk` sets |
| `unarchive.bsa`, `unarchive.ba2` | bethesda | `bsa-builtin`, `ba2-builtin` | - | LZ4 through the `lz4` pin |
| `unarchive.drs` | genie | `drs-builtin` | - | |
| `unarchive.pack` | warscape | `pack-builtin` | - | |
| `unarchive.archive` | redengine | `rdar-builtin` | - | |
| `unarchive.tpac` | taleworlds | `tpac-builtin` | - | |
| `unarchive.bms` | quickbms | `quickbms-cli` (GPL-2.0, subprocess) | - | suffixes from the scripts folder |
| `unarchive.rcc` | qt | `rcc-builtin` | - | `qres` head; `.rcc` (doc 13.8) |
| `unarchive.pak` | chromium | `pak-builtin` | - | DataPack version 4/5 head |
| `unarchive.pyi` | pyfrozen | `pyi-builtin` | - | identifier: the PyInstaller MEI cookie scanned near an exe's end |
| `unarchive.dotnet` | dotnet | `dotnet-resources` | - | identifier: a PE with a CLI header (managed assembly) |
| `unarchive.jar` | java | `jar-builtin` | - | `.jar`, `.war`, `.ear` |

**Export:** `export.unity` (`unitypy`, spare `assetstudiomod-cli`, D7; `unitypy` writes every
Mesh twice: UnityPy's own Wavefront `.obj`, and a lossless `.glb` through
`contracts/gltf.py` (`plugins/unity/meshes.py`): positions, normals, tangents, every UV set,
vertex colours as data (`_COLOR_0`), each sub-mesh a primitive with 16- or 32-bit indices, the
bind poses and bone weights, the bone names and tree of the SkinnedMeshRenderer loaded with the
mesh (else bones named by hash), the material's `_MainTex` embedded as PNG; X mirrored and every
triangle rewound from Unity's left-handed space, V turned. Blend shapes, more than four bone
weights a vertex, texture tiling and the other material slots are not in it. A mesh the `.glb`
cannot hold is counted with the first reason and keeps its `.obj`; untextured meshes and bones
named by hash are counted. The option `meshes = off` drops both; the spare writes `.obj` only),
`export.godot`
(`gdre-recover`, opt-in option `recover`), `export.rpgmaker` (`rpgmv-builtin`),
`export.overwatch` (`datatool`, declares `network = "download"`), `export.warscape` (`db-builtin`: every `db/` member of every pack to JSON with the
game's RPFM schema `rpfm-schema-<game>`; a table the schema lacks or misreads is counted and
named), `decode.loc` (`loc-builtin`, Total War localisation to JSON), `decode.locres`
(`locres-builtin`, unreal, in process: Unreal localization tables, versions 0 (legacy), 1
(compact), 2 (CRC32 keys) and 3 (CityHash64 keys), to `{namespace: {key: text}}` JSON; another
version is refused by name), `decode.xnb` (`xnb-builtin`, xna, in process: XNB format version 5,
uncompressed or LZ4 (MonoGame's raw block, through the `lz4` package); LZX (XNA's XMemCompress, the first-party `lzx.py`); a Texture2D in Color,
Bgr565, Bgra5551, Bgra4444, Alpha8 or DXT1/3/5 (ViWo's block decoders) to PNG, its largest
level, as stored (XNA premultiplies alpha by default); a SoundEffect to WAV with its own format
chunk (PCM, float, ADPCM as stored); XNA 3.x files, other content types and other
surface formats are counted failures, by name), `export.unreal` (`uas-export`:
UnrealAssetScout as its own process, every mode over every Paks folder with the engine version
read from the game's binaries, the AES key per D18 and the `.usmap` the RUNTIME agent wrote into
the workspace; packages that need mappings are counted and the way to get them named. The tool
draws compact progress and writes its per-file lines to a log in the scratch folder, which is
read back for the `[FAILED]` count and deleted. Its models are UEFormat (`.uemodel`), the only
format it writes; with the option `models = glb` (default) each also gets a `.glb` beside it
through `contracts/gltf.py` (`plugins/unreal/uemodel.py`, UEFormat version 10 as CUE4Parse
writes it, plain or gzip): LOD 0 (never the Nanite LOD), positions, normals, tangents, every
UV set, vertex colour sets as data (`_COLOR_n`), one primitive per material section with its
name (untextured), and for a skeletal mesh its bones in the reference pose and every weight; Y
and Z swap from Unreal's left-handed Z-up space (Unreal's own glTF exporter's choice), units
stay centimetres. A zstd-compressed file on a Python without `compression.zstd`, another
version, or a damaged file is counted with the first reason; a skeleton alone is counted and
kept as `.uemodel`; `models = uemodel` writes no `.glb`).

**Carve and decode:** `carve.signatures` (`signature-carver`); `decode.audio` (`vgmstream-cli`,
spare `ffmpeg-decode`; Wwise, FMOD, CRI, XACT and console audio to WAV); `decode.image`
(`ffmpeg-image`, DDS to PNG; spare `pillow-image`, in process: what the pinned ffmpeg does not
read, BC6H and BC7, which the main hands on without starting ffmpeg, and every DDS when ffmpeg is
missing; BC6H clamped to 0..1 in 8 bits, said per file); `decode.video` (`ffmpeg-video`, Bink to MP4, opt-in); `decode.bink2` (`bink-game`: Bink 2 to MP4
through the game's own `bink2w64.dll` in a helper process, frames piped into ffmpeg, opt-in with
video); `decode.cr2w` (`wolvenkit-export`, redengine: WolvenKit's console, GPL-3.0 as its own
process. A run takes up to 150 files, as many as are estimated to fit 2 GB: about 1.2 GB before
WolvenKit reads a file, then per byte of file 250 bytes for an animation and 15 for the rest
while it exports, 10 while it serializes (measured under caps on Cyberpunk 2077 2.x; a file
that does not fit runs alone, capped at its estimate; no run under 1.5 GB, below which
WolvenKit cannot start). Each run's cap is held out of the memory
budget (doc 9.2). What a run could not convert is run again once, ten files at a time with
twice the room; what then fails for want of memory gets ViWo's whole share, alone, six times
at most per call: `export` turns textures into PNG and meshes, morph
targets, cubemaps and animations into glTF, `convert serialize` turns every CR2W resource into
JSON; ViWo writes the export settings it needs into WolvenKit's `appsettings.json` off screen and
every file WolvenKit could not convert is counted; the core hands a batch backend 600 files per
call (`decode.PART`), several calls at once on the worker pool (doc 3.1), so the decode counter
moves as parts finish and a cancel starts no further part, and the parts' failures become one warning per slot: the first, and how many
other parts failed); `decode.redscripts` (`redscript-decompile`, redengine, option `decompile`:
redscript's console, MIT, Windows build, decompiles `final.redscripts` into one `.script` file per
stored script); `decode.rpyc`
(`unrpyc-cli`, renpy, option `decompile`); `decode.slp` (`slp-builtin`, genie);
`decode.ctex` (`ctex-builtin`, godot, in process: `.ctex`/`.stex` textures whose mipmaps are PNG
or WebP, uncompressed 8-bit, or VRAM-compressed S3TC, RGTC and BPTC, to PNG (BC1 to BC5 and
BC7 through ViWo's own block decoders in `backends/blocks/`, BC6H through Pillow, clamped and
said); an ETC, ETC2, ASTC, PVRTC or Basis texture is a counted failure, by name);
`decode.vtf` (`vtf-builtin`, source: VTF 7.0-7.5 to PNG); `decode.mdl` (`mdl-builtin`, source,
a batch backend: studio models, `.mdl` versions 44 to 49, into `.glb` through
`contracts/gltf.py` (`plugins/source/studio.py` reads, `models.py` writes). The `.vvd` and the
`.vtx` (`.dx90` first, then `.dx80`, `.sw`, plain) are found by name in the workspace's groups
and told apart by the checksum the three files share. LOD 0 of the default model of every
body part: positions, normals, UVs, the bones in their reference pose with poseToBone as the
inverse bind matrices, up to three weights a vertex, one primitive per mesh named after its
material (skin family 0), the material's `$basetexture` embedded as the PNG `decode.vtf` makes
when the `.vmt` and `.vtf` are in the run. Source's right-handed Z-up axes turn to glTF's
(x, y, z) = (y, z, x), and each triangle is rewound (the `.vtx` lists front faces clockwise).
The rest pose is the file's bind pose: a model whose data lies on its side (TF2's characters)
lies in the `.glb` too; the game stands it up through its animations. Flexes, animations,
eyeballs, attachments, other bodygroup choices and LODs are not in it. Each call says
how many models it wrote, how many hold no mesh (animation libraries) and how many materials
stayed untextured; a model that cannot be converted is counted with the first reason);
`decode.rigid_model_v2` (`rmv2-builtin`, warscape, a batch backend: Total War rigid models,
versions 5 (Rome II's older files: every string in UTF-16, so the skeleton name and the
material block's fields sit further on), 6 (Rome II, Attila, Thrones of Britannia; both read on
Rome II's packs) and 7 (Warhammer, version 6's layout with a 28-byte LOD header, tests only);
1, 3, 8 and others are refused by name. `plugins/warscape/rigid.py` reads, `models.py` writes.
LOD 0, each mesh group a primitive whose material is named after the group (else its colour
map or decal) and keeps the shader, the material type, the vertex layout and every texture
path as extras. The material type decides the block: the default block names a vertex format,
0 (static: position from the group's pivot, two UV sets, normal and directions stored B, G, R,
colour), 1 (collision: position and normal as floats), 3 (weighted: two bones, one stored
weight, the second weighing the rest), 4 (cinematic: four bones and weights) or 8 (water:
position, UV); types 29 and 30 are banners (static without the second UV), 22 a bow wave
(position, a second position and a float kept as data as stored, `_POSITION_1`, `_VALUE_0`,
UV), 67 and 87 a decal's projection box (four floats a vertex; drawn see-through, its decal
path in the extras). Flag placements (26) and lights and effects (45) hold no vertex data; they
and any other type or format are left out and counted with why, a file of only such groups is
refused with it, and a group whose vertices do not fit its type's layout is left out the same
way. Bone links are scaled to sum to one; with the skeleton the
header names in the run (`animations/skeletons/<name>.anim` version 5 for names and parents,
`<name>.bone_inv_trans_mats` for the bind matrices; the reference pose is their inverse; of
several files of that name, `name__1` included, the first pair that reads and agrees) they
form a glTF skin, without it (or when a vertex weighs on a bone past its last) they stay as
data (`_JOINTS_0`, `_WEIGHTS_0`) and the call says so with the reason; no pose is invented. Warscape is left-handed, Y up: X is mirrored on every
position, direction and matrix, every triangle is rewound, a tangent's handedness is taken
after the mirror. The colour map (texture type 0) is embedded as PNG through Pillow when its
`.dds` is in the run, found by name in the `dds/` group (the first of a name two folders
share) or by its game path above the model's folder); `decode.nif` (`nif-builtin`, bethesda,
a batch backend: NIF 20.2.0.7, user version 12, Bethesda stream 83 (Skyrim), 100 (Skyrim
SE), 130 (Fallout 4); others refused by name; tests only, no Bethesda game at hand.
`plugins/bethesda/nif.py` reads, `nifmodels.py` writes. Blocks read: the node kinds of
`nif.NODES`, NiTriShape and BSLODTriShape with NiTriShapeData, BSTriShape, BSMeshLODTriShape
and BSSubIndexTriShape with their own vertex data, NiSkinInstance, BSDismemberSkinInstance
and NiSkinData, NiSkinPartition (`partition.py`), BSSkin::Instance and BSSkin::BoneData,
BSLightingShaderProperty with its BSShaderTextureSet, BSEffectShaderProperty; a file holding
NiTriStrips, BSDynamicTriShape, BSSegmentedTriShape or NiTriShapeDynamic is refused naming the
type. A skinned Skyrim SE BSTriShape with data size 0 takes its vertices (BSTriShape's layout,
from the partition block's descriptor), its triangles (each partition's copy with the shape's
indices) and its links from its NiSkinPartition; so does a skin whose NiSkinData holds no
weights. Links from a partition are its own: each vertex's slots map through that partition's
bone list to the skin's bones, through its vertex map to the shape's vertex (a vertex two
partitions share takes the first); the weights the Skyrim SE vertex data repeats are not read.
A vertex in no partition, a partition without weights or bone indices, or an index past its
bones is refused by name. The partition is read as nif.xml describes it: no real NIF has been
read. The node tree becomes glTF nodes; each shape a node with a mesh of one primitive
(positions, normals, tangents, every UV set, colours as `_COLOR_0`, triangles as stored) and
its shader as the material (named after the shader, Fallout 4's `.bgsm` path, else its colour
map); a skin's inverse bind matrices are what Gamebryo skins with (bone^-1 * shape *
rootParentToSkin * rootParent^-1 * bone * skinToBone, skinToBone in a consistent file).
NIF is right-handed, Z up, Y forward: glTF's (x, y, z) is NIF's (-x, z, y), a rotation, so
winding is kept. Bethesda's array named tangents runs along V (as NifSkope and nifly write
it): TANGENT is the other one. Collision, particles, controllers and `.bgsm` materials are not
read. Both calls say how many models they wrote, how many hold no mesh, how many were refused
(the first reason) and how many materials stayed untextured). Desktop-app frameworks (doc 13.8):
`decode.qm` (`qm-builtin`, qt, in process: Qt compiled translations to JSON, one way),
`decode.pyc` (`pyc-builtin`, pyfrozen, in process: a `.pyc`'s bytecode disassembled when its
magic matches the running interpreter, else written out with the version named). Declarative
(doc 13.2a): `decode.kaitai_<id>` (`kaitai-<id>`, kaitai, in process: one slot per bundled
`.ksy`, a format parsed to a JSON tree by ViWo's own interpreter; one way; runs only when the
plugin is selected).

**Media:** `media.probe` (`ffprobe-probe`, spare `pillow-probe`), `media.encode` (`ffmpeg`).

**Keys (doc 14.2 #4):** `keys.unreal` (`unreal-exe-keys`: the 32-byte keys inlined in the
game's executables, candidates the unreal plugin verifies on an encrypted pak index).

**Pack (doc 18):** `pack.zip` (`zip-packer`), `pack.rpa` (`rpa-writer`), `pack.pck`
(`godotpcktool-pack`), `pack.upak` (`repak-patch`, `_P.pak`), `pack.archive` (`wolvenkit-pack`, override archive in `archive/pc/mod`), `pack.unity` (`unitypy-pack`),
`pack.rpgmaker` (`rpgmv-pack`), `pack.wolf` (`wolf-writer`, wolfrpg, in process: a DXArchive
version 6 rebuilt with the edits, stored raw), `pack.tpac` (`tpac-writer`, taleworlds, in process: a TPAC
rewritten member by member, doc 18.4); desktop-app frameworks (doc 13.8): `pack.rcc`
(`rcc-writer`, qt), `pack.pak` (`pak-writer`, chromium), `pack.pyi` (`pyi-writer`, pyfrozen),
`pack.resources` (`resources-writer`, dotnet, same-size in place), `pack.jar` (`jar-packer`,
java); the other writers ViWo owns are in doc 18.4. **Patch:** `patch.bytes` (`viwo-patcher`, owns the Keystone and
capstone dependencies).

**Analysis (doc 6):** `analysis.native`, `.memory`, `.dotnet`, `.il2cpp`, `.script`, `.python`,
`.gdscript`, `.protector`, `.emulate`, `.symbolic`. **Handoff:** `handoff.native` (8.3a).

**Dynamic (doc 11):** `capture.gpu` (`renderdoc`), `runtime.unreal` (`ue4ss-agent`),
`runtime.unity` (`bepinex-agent`), `attach.debug` (`x64dbg-gui`), `attach.memory`
(`cheatengine-gui`).

**Declarations:** every backend declares `license`; a GPL/AGPL backend has `isolation =
"subprocess"`; `network` is `none` unless the tool fetches (`datatool`, `bepinex-agent`:
`download`); in-process parsers of game bytes set `parses_untrusted_in_process` (L0 test).

## 8.5 How the stages use slots

| Stage or job | Interface | Slot lookup |
|--------------|-----------|-------------|
| DETECT | `EnginePlugin.detect` | - |
| UNPACK | Unarchiver | `unarchive.*` whose suffix, magic or identifier matches |
| EXPORT | Exporter | the plugin's `export_slot()` |
| CARVE | Carver | `carve.signatures` |
| COLLECT / DECODE | Decoder | `decode.*` by suffix: core slots on every game, a plugin's slots only when that plugin was chosen for the game |
| VERIFY | `EnginePlugin.verify_report` | - |
| merger | Prober, MediaEncoder | `media.probe`, `media.encode` |
| repack | Packer | the plugin's `pack_slot(unarchive slot)` |
| patch set | Patcher | `patch.bytes` |
| analyze | Analyzer | `analysis.<kind>` or the requested `--slot` |
| handoff | Handoff | every bound `handoff.*` accepting the kind |
| attach | Handoff | every bound `attach.*` accepting the kind |
| capture | capture | `capture.gpu` |
| agent | RuntimeAgent | `runtime.<engine>` of the detected plugin |

## 8.6 Slot conformance

- Slot ids are unique across core and plugins; a plugin owns the slots it introduces.
- Every default main and spare names a known backend whose `families` include the slot's family
  (a missing spare of a switched-off plugin is allowed).
- `available()` has no side effects; `self_check()` runs each CLI tool once.
- `needs_key` never reaches the spare.
- Binder states main up/down x spare up/down, promotion and unbound slots are tested with fakes
  (`tests/test_core_units.py`, `tests/test_config.py`).
- A plugin may add a backend to a slot it does not own; the ini then makes it main or spare.
