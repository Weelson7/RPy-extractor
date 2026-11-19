# Changelog

Versions follow `va.b.c` (`tools/version.py`): `a` product release, `b` feature, `c` every
commit. Each tag's commit message carries the full list; this file keeps what changed for a user
or a maintainer. Newest first.

## 1.32.0 (2026-11-19)
- The patcher / isolation arm is finished across all three tiers (doc 11.8, rung T4); ViWo
  authors no hypervisor, driver or evasion code — it orchestrates located third-party tools.
  - **QEMU (Tier 2)** runs the target out of the guest. The backend boots the user's own
    `qemu-system-x86_64` with its gdbstub (`-gdb tcp::PORT -S`) and a QMP control channel, uses
    **WHPX** acceleration when QEMU reports it else **TCG** (and says which), and reads/writes
    guest memory and suspends/resumes over the **GDB remote serial protocol** through a small
    first-party stdlib client (`gdb.py` — it speaks QEMU's own gdbstub, so no gdb binary is
    located); snapshots (savevm/loadvm) and a guest-memory dump go through QMP (`qmp.py`).
  - **DRAKVUF / LibVMI (Tier 3)** orchestrates a bare-metal Linux KVM/Xen host: it reads/dumps
    guest memory with `vmi-dump-memory` and pauses/resumes the domain with `virsh` (KVM) or `xl`
    (Xen). LibVMI ships no stock memory-write CLI, so a live `write_mem` is a `not_ready` wall
    that says a write helper is needed. On Windows and WSL2 the tier reports not-ready with the
    exact requirement, never silently.
  - **The cold+live bridge** (`live.py`): one patch recipe applies either way. The same located
    file offset the cold writer uses is turned into the virtual address it loads to (the PE's
    image base, or a given base when ASLR moved the module) and written into the live target
    under the atomic suspend -> write -> verify -> resume.
  - **`viwo isolate`** and **`GET`/`POST /api/runtime/isolation`** drive a session (list the
    tiers, start a target under one, patch it live, close); RUNTIME shows the tiers' readiness.
  - Unit-tested on fakes and in-process loopback gdbstub/QMP stubs. **Not yet proven on a real
    VM, QEMU or VMI host** (located-only tools; a person installs them and runs it on a machine).

## 1.31.3 (2026-11-19)
- Chromium `.pak` is identified by its DataPack header (version 4 or 5), not the `.pak` extension
  alone — `.pak` is also Unreal's and Quake's, so a non-Chromium `.pak` is no longer mis-claimed
  as a container (SURVEY counted it twice; fixes `test_survey`).

## 1.31.1 (2026-11-19)
- Overwatch owmdl now converts on Linux too: the material's path (a DataTool Windows path) is
  split on any OS, and the key/path pair is read in stream order (a refactor had reversed it,
  which misaligned the parse on every platform). Confirmed on the WSL Linux suite.

## 1.31.0 (2026-11-19)
- Five framework plugins for cold-patching desktop applications (doc 13.8), the same
  extract -> edit -> repack model the game engines use, first-party readers where the format is
  a container:
  - **Qt** (`qt`): `.rcc` resource collections (versions 1-3, zlib blobs; zstd reported) are
    read and rebuilt with the name and node trees kept, so an unchanged resource comes back byte
    for byte; `.qm` translations are read into JSON (one way); and QML/JS/QSS/SVG compiled into
    an exe or DLL are carved by `viwo qt-resources` (content, not the tree's names). Proven on
    Free Download Manager: its QML UI (258 QML + 365 SVG) comes out of `fdm.exe`. Its connection
    limit, though, is enforced in native code (the setting key `MaxConnectionsPerServerLimit`),
    not a resource, so raising it is a binary patch on the copy (doc 18.8), not a resource edit.
  - **Chromium `.pak`** (`chromium`): the DataPack format (versions 4 and 5, every resource id
    and version-5 alias) is extracted and rebuilt byte-faithfully. Covers Chrome, Edge, Brave,
    Steam, VS Code and other CEF/Electron apps.
  - **Frozen Python** (`pyfrozen`): a PyInstaller onefile exe (CArchive + inner PYZ) yields its
    data files, bundled binaries and every module as `.pyc`, and is rebuilt with edits (bootloader
    and cookie kept, unchanged byte for byte); py2exe/cx_Freeze `library.zip` goes through the
    core zip; `decode.pyc` disassembles a `.pyc` for the matching interpreter. Proven on a real
    PyInstaller 3.13 exe.
  - **.NET** (`dotnet`): embedded managed resources are listed and extracted by walking the
    ECMA-335 metadata to the ManifestResource table, and an edit is written back in place when
    its size is unchanged (a size change is refused by name); the C# static view is the pinned
    ILSpy handoff. Proven against real framework assemblies.
  - **Java** (`java`): `.jar`/`.war`/`.ear` extract and rebuild through the stdlib zip path; no
    class decompiler is pinned, so `.class` files stay bytecode (said).
  - Docs: contract 02, 08, 13.8, 18; CONFORMANCE engine matrix and rows; `loc_caps.ini` budgets;
    regenerated distros; `tests/test_qt.py`, `test_chromium.py`, `test_pyfrozen.py`,
    `test_dotnet.py`, `test_java.py`.

## 1.30.2 (2026-11-19)
- CHANGELOG: repaired em-dashes mangled into mojibake and an entry that landed above the title,
  both from editing the file through PowerShell's default (non-UTF-8) encoding.

## 1.30.1 (2026-11-19)
- HANDOFF records the first Linux suite run (WSL Ubuntu 22.04, Python 3.10.12): 826 tests, three
  modules left — a cross-platform owmdl path parse, the missing Linux-3.10 package locks, and a
  dev-venv needing `wheel` (and `Pillow` reached only via UnityPy, which should be declared).

## 1.30.0 (2026-11-19)
- Patcher / isolation foundation (doc 11.8, rung T4): a thin `PatcherBackend` contract
  (`viwo/contracts/patcher.py`) for cold and live patching that holds against self-checksums,
  anti-debug and fragile state, and meets TPM-gated local logic with a virtual TPM. One live
  edit is atomic — suspend, write, read back to verify, resume (`core/isolation/atomic_write`) —
  and when it cannot land the backend says which `Wall` it hit (server-side, VM-detected,
  remote-attestation, integrity-check, not-ready), never silently.
  - Scylla dump-to-patch (`attach.dump` / `scylla-gui`): "Continue in Scylla" attaches to the
    running game and dumps a reconstructed PE (IAT rebuilt) into the workspace for the cold-patch
    flow. Scylla is GUI-only, so it is a launch-and-guide handoff like the debugger, never a faked
    automation; pinned (NtQuery/Scylla 0.9.8, GPL-3.0). It rides `viwo attach` behind `capture`.
  - Tier 1 VirtualBox (`isolation.vbox`): ViWo drives `VBoxManage` to register a VM with a
    virtual TPM 2.0, boot the target, take and restore snapshots for patch retries, pause/resume
    it and dump its memory core to a patchable file; the in-guest debugger does the byte-level
    read/write. Unit-tested with a fake `VBoxManage`; no real VM has run. VirtualBox is located,
    not installed (a hypervisor needs a kernel driver and elevation — the minimal-prompts rule).
  - Tiers 2 (QEMU, out-of-guest gdbstub, WHPX/TCG) and 3 (DRAKVUF/LibVMI, a bare-metal Linux host)
    are declared backends that announce their requirement and refuse through `wall()`.
  - Open: a CLI/API surface to drive a session, and real in-VM proof.

## 1.29.0 (2026-11-19)
- Five engines of doc 13.7 get first-party readers, each with its way back (no tool installed):
  - Unreal localization: `decode.locres` turns `.locres` tables (versions 0 legacy, 1 compact,
    2 CRC32 keys, 3 CityHash64 keys) into `{namespace: {key: text}}` JSON and writes an edit
    back in the table's own version, every hash and each string's storage kept: an unchanged
    table comes back byte for byte. Another version, and a new key in a version 3 table (its
    CityHash64 is not computed), are refused by name.
  - LÃ–VE (`love2d`): the game's zip, alone (`.love`) or fused onto the executable (recognised
    by its zip end record and `love.dll` beside it), unpacks; `pack.love` rebuilds it, behind
    the executable's unchanged bytes when fused. LÃ–VE loads nothing loose from the game folder,
    so there is no mod form; the plan says so.
  - XNA/FNA/MonoGame (`xna`): `decode.xnb` turns Texture2D (Color, Bgr565, Bgra5551,
    Bgra4444, Alpha8, DXT1/3/5) into PNG and SoundEffect into WAV, uncompressed and LZ4 files,
    and writes an edited PNG or WAV back into the XNB in its format, mips rebuilt. LZX files,
    XNA 3.x files, other content types and surface formats are refused by name.
  - Adventure Game Studio (`ags`): CLIB packfiles in every version the engine reads (6, 10,
    11, 15, 20, 21, 30), alone or behind the game's executable, with the assets of their other
    parts; `pack.clib` rebuilds a library in its own version, offsets and sizes patched in
    place (an unchanged library comes back byte for byte).
  - Defold (`defold`): `game.arci`/`game.arcd` (index versions 4, 5, 6) unpack under the URLs
    `game.dmanifest` names, LZ4 resources through the `lz4` package, encrypted ones named;
    `pack.arci` rewrites data and index, every hash and the manifest kept.
- Checked on real data from the engines' own releases (AGS 3.6.3 templates, a Defold example
  bundle, LÃ–VE 11.5's `love.exe`, MonoGame's test XNB files), not on a game install.

## 1.28.0 (2026-11-19)
- Sanitizer phase 2 (doc 5.1): `phase2-convert` writes an open-format copy of each workspace
  file a bound lossless `decode.*` slot reads (the decoders an extraction runs, failover
  included; `Decoder.lossless`, false for the video decoders that re-encode), placed and
  recorded as DECODE does, so an edited copy goes back through the round trip;
  `phase2-replace` then moves the original to the workspace trash. Files a decoder already
  read are left out, and a plugin's slot when the run records name other plugins.
- Sanitizer phase 3, opt-in: `phase3-audio` (Opus in Ogg) and `phase3-video` (H.264/AAC MP4)
  through the pinned ffmpeg of `media.encode`, LOSSY: marked in the recipe and on each finding,
  never taken by `all-safe`, never ticked for you in CLEANUP; `phase3-renumber` gives a
  folder's numbered sequences contiguous zero-padded numbers in their order.
- Every file the sanitizer makes is journaled: undo removes it while it is unchanged and keeps
  (and names) one you edited. The apply report says per file what it became (`converted`).
- `viwo sanitize --recipe ID`; `GET /api/sanitizer/recipes` lists every recipe with `phase`,
  `lossy` and why it cannot act now; apply takes `accept: "all"`. CLEANUP has a recipe picker.
- `[hooks]` (doc 9.5): `before_<kind>`, `after_<kind>`, `before_any`, `after_any` run your own
  command around every job, in the CLI and the API, told the job in `VIWO_*` variables; its
  lines join the job's events; a failing, missing or slow hook (`timeout`, default 60 s) is a
  warning and the job goes on. The CLI runs every command that is a job kind as a job now.
- `ProcessRunner.shell_command` (doc 1.1): a user's command line through `cmd /d /s /c` or
  `/bin/sh -c`, as written.

## 1.27.5 (2026-11-19)
- Python 3.10 is enough (owner): `requires-python >= 3.10`, ruff's target `py310`, the CI matrix
  3.10 and 3.13, and the package locks built for 3.10 too (`tools/pin_python.py`). The one call
  3.10 lacks (`hashlib.file_digest`, in the REDengine way back) reads in chunks instead.

## 1.27.4 (2026-11-19)
- SORT: the held queue also keys on each folder's entry names, not only its mtime. On Windows a
  file dropped or renamed within the same clock tick does not always move the folder's mtime, so
  the queue could stay stale (a gone file still listed, a new one missing) until the next change.

## 1.27.3 (2026-11-19)
- The UI spacing check no longer flags the pinned action bar against content scrolling beneath
  it (SETTINGS' APPLY and BROWSE floated over the form below as the page scrolled).

## 1.27.2 (2026-11-19)
- The game loads the change on Doom too: Freedoom 2, run by Chocolate Doom 3.1.0, shows its
  repainted title picture from ViWo's rewritten `freedoom2.wad` (`sqc/proof/doom-freedoom.jpg`).
- `tools/game_shot.ps1 -Arguments`: the game's command line.

## 1.27.1 (2026-11-19)
- `tools/game_shot.ps1`: several keys separated by `|` (PowerShell's `-File` passes one string),
  the window looked for again for 30 s after the keys (a game swapping windows), and `-Screen`
  to copy the screen where printing a full-screen DirectX window gives black.

## 1.27.0 (2026-11-19)
- The game-folder guard without a game path (doc 3.1) knows games now. Every game ViWo is
  given is remembered in `viwo-data/games.json`; `dump`, `trace`, `hook`, `profile`, `record`,
  `sanitize`, `unpack --out` and `diff --out` refuse a folder that is such a game, lies in one
  (a new folder included) or holds one, whatever marker it carries, and the same for Steam
  libraries, Epic and GOG installs (their own marks) and patched copies. `unpack --out` and
  `diff --out` go through the guard too (a diff may rewrite its own two files). A dump or
  analysis folder inside a ViWo workspace is never remembered as a game.
- `[slot_policy] <slot> = supplement` (doc 8.2): after the main succeeds the spare runs too,
  and every file it wrote that the main did not joins the main's output (names record and
  export map entries follow); the added count, or why the spare failed, is said. Unarchive,
  export, carve and decode slots only; elsewhere it is a boot problem and failover is used.
- Completeness counts: Source keeps an inventory (every member its VPK directories list).
  Core counts `inventoryItems` / `collectedFromInventory` against what COLLECT recorded, by
  member, for the extensions the run selected, and names the members that did not come out
  in a verify warning.
- Sanitizer rules a plugin can ship: the rule types moved to `viwo/contracts/sanitizer.py`
  (a plugin could not reach them in core). Ren'Py ships `renpy.cache`: the `.rpyb` caches the
  engine rebuilds go to the trash in the safe recipe.
- `memory_image` targets (doc 6.5): the generic plugin proposes the Windows minidumps a folder
  holds (what `viwo dump` writes), and `analysis.memory` runs Ghidra headless on them through
  Ghidra's own dump loader (checked once on a real 14.6 MB minidump of `ping.exe`: 21,859
  functions in 47 min).
- `keys.*` slots (doc 14.2 #4): key finders are backends (`KeyFinder`); a plugin asks
  `ctx.keys(slot)` and verifies each candidate before use. `keys.unreal` = `unreal-exe-keys`.
- `[hooks]` stays open: no design yet.

## 1.26.0 (2026-11-19)
- Ways back: BC2, BC6H and BC7 DDS. `decode.image` writes BC2 (DXT3: 4-bit alpha, the
  nearest step of 17), BC7 (mode 6 only: one subset, RGBA endpoints of 7 bits plus a p-bit;
  an endpoint whose alpha is 0 or 255 keeps it exactly) and BC6H unsigned and signed (mode 11
  only: one region, 10-bit endpoints; each 8-bit value aimed at the middle of what Pillow shows
  as it). Pure Python, deterministic; a 1024x1024 texture takes about 3 s in BC2 and 7 to 12 s
  in BC7 or BC6H on a busy desktop. Every format is decoded again in the tests by ViWo's own
  decoders, a BC6H mode 11 decoder written per the specification and Pillow, within the
  format's bound. BC6H's loss (colour above 1.0, alpha) is said with each file the repack
  writes: an encoder's notes are now warnings of the repack. Still refused by name:
  premultiplied DXT2/DXT4, signed BC4/BC5, typeless BC6H.
- `decode.image` has a spare, `pillow-image` (in process): the pinned ffmpeg 6.1 reads no BC6H
  or BC7 DDS (it answers "Unsupported DXGI format"), so those were not decoded at all; the main
  now hands them on without starting ffmpeg, and Pillow decodes them (and every DDS when ffmpeg
  is missing). BC6H comes out clamped to 0..1 in 8 bits, said per file: a decoder's notes are
  now warnings of DECODE.
- The block codecs moved to `viwo/backends/blocks/` (the BC1-BC5 encoder from `core/`), where
  core and the plugins can both import them, with first-party decoders: BC1 to BC5 (byte for
  byte what the pinned ffmpeg shows, checked by hand on random blocks; BC5's blue is 0 where
  ffmpeg rebuilds a normal's z) and BC7, every mode, partition and anchor (block for block what
  Pillow shows, in the tests; a reserved block is transparent black as the specification says).
- Godot: VRAM-compressed `.ctex`/`.stex` textures decode to PNG and go back. DXT1, DXT3, DXT5,
  RGTC_R, RGTC_RG and BPTC_RGBA through ViWo's block decoders, BPTC_RGBF/RGBFU (BC6H) through
  Pillow, Godot 4's DXT5_RA_AS_RG (normal maps) with Godot's own swizzle; written back in the
  same block format, every mip level. ETC, ETC2, ASTC, PVRTC and Basis Universal stay refused
  by name. Tests only (no Godot game with PCK data here). A 1024x1024 BC7 texture takes 5 to
  9 s to decode in pure Python.
- Bannerlord: `pack.tpac` writes edits back into a TPAC package, every other byte kept. A
  segment entry's 12 unknown bytes were measured: the xxHash64 (seed 0) of its uncompressed
  data, then 4 bytes kept as they are; LZ4 segments are LZ4 HC level 12, so unchanged data
  compresses to the same bytes. An edited `<item>.<n>.bin` replaces its segment; an edited
  `<item>.dds` the texture's largest segment at the same size, mips and format (anything else
  is refused by name), and the segment holding the chain from mip 1 (Bannerlord keeps one per
  texture) follows it. New data goes in place when it fits and no other entry shares it, else
  at the end. An item's checksum is kept: what it hashes is unknown (not the metadata, not the
  data, not xxHash64, FNV-1a or MurmurHash64A of either), and mod packages whose checksums are
  all 0 load. Checked by hand, static, on a copy of one package (`ScarsExtra`'s
  `scar_nobl_g.tpac`, 740,848 bytes, a BC7 and a DXT5 texture, raw and LZ4 segments): every
  member given back unchanged gave the same file byte for byte; its BC7 texture repainted
  through PNG, `pillow-image` and the BC7 encoder (2.6 s with its mips) read back through the
  plugin's reader as written, the other texture unchanged, the mip-1 segment the new chain's
  tail, the bytes changed only the two entries' fields, the mip-1 data in place and the full
  chain appended (765,087 bytes). Bannerlord was not started on it.
- Budgets: `viwo/backends` 600 -> 720, `viwo/plugins/godot` 560 -> 640, `viwo/plugins/taleworlds`
  300 -> 460 (reasons in `loc_caps.ini`).

## 1.25.4 (2026-11-19)
- The game loads the change on Age of Empires too: Age of Empires II HD shows its marked main
  menu background from ViWo's patched copy (`sqc/proof/genie-aoe2hd.jpg`).
- `tools/game_shot.ps1`: `-Keys` sends keystrokes before the capture (a dialog in front of the
  menu), and the game's window is looked up again after waiting (a game that swaps its window
  while starting left the capture with no window).

## 1.25.3 (2026-11-19)
- MERGER: single files can be ticked again. 1.25.1 moved them into a list that could only be
  read, which took the merger away from a workspace of single files; they keep their own
  list after the groups (SINGLE FILES) and work as before.

## 1.25.2 (2026-11-19)
- Total War: `decode.rigid_model_v2` reads version 5 (Rome II's older files, every string in
  UTF-16) and the material layouts beside the default block: collision (format 1) and water
  (format 8) groups, banners, bow waves (their second position and float kept as data) and
  decal projection boxes (drawn see-through, the decal path kept). Each was checked on Rome II's
  own files: positions inside every group's bounding box, normals against the triangles, U
  and V directions against the UV gradients. Flag placements and lights hold no vertex data
  and are named when left out; a vertex weighing on a bone past its skeleton's last keeps the
  links as data with that reason instead of refusing the model.
- Bethesda: `decode.nif` reads skinned Skyrim SE shapes whose vertices, triangles and weights
  are in their NiSkinPartition, and skins whose NiSkinData holds no weights, each partition's
  bones mapped to the skin's. Tests only: no real NIF has been read.

## 1.25.1 (2026-11-19)
- UI review findings closed. ANALYSIS has the action bar of the other views: pick a target in
  TARGETS, ANALYZE in the bar runs it, disabled with the reason beside it (list the targets,
  analysis is off, no analyzer yet); the extra slots and CONTINUE IN GHIDRA stay on their row.
- Button spacing, in CSS once: a row of buttons right under a note, a field, a table or
  another row now stands 14 px clear of it (RUNTIME, PATCHES, RUNBOOKS, ANALYSIS and the
  notices with TURN ON had none), and a field row above a view's panels no longer touches them.
- MERGER: a name with one file is no longer shown as a group; those files are one NOTHING TO
  MERGE list with their count, each with its path and type. `/api/media-merger/list` answers
  the groups of several files first and counts the rest (`singleCount`); the GROUPS header
  says both.
- Arm homes: the steps one tab runs share its row (RUNTIME lists AGENTS, RECORD, DUMP + TRACE,
  DEBUGGER + MEMORY and CPU PROFILE under one D-code), so each code shows once per home.
- RUNBOOKS: each action step reads as what it runs (the job and its tab), its target and its
  options as key/value, with the run's value beside each `{name}`; the step's JSON is behind a
  JSON toggle.

## 1.25.0 (2026-11-19)
- Total War: `decode.rigid_model_v2` turns rigid models (versions 6 and 7; 5, 8 and others
  refused by name) into `.glb`: LOD 0, each mesh group a primitive with positions (from the
  group's pivot), normals, tangents, both UV sets of a static group, colours as data, a
  material named after the group with every texture path kept, the colour map embedded as PNG
  when its `.dds` is in the run. Weighted and cinematic groups carry their bone links; with
  the skeleton the model names in the run (`.anim` and `.bone_inv_trans_mats`) they form a skin
  in the bind pose, without it they stay as data (`_JOINTS_0`, `_WEIGHTS_0`) and that is said.
  Groups of other formats (decals, water) are left out and counted. X is mirrored, triangles
  rewound. No tool installed.
- Bethesda: `decode.nif` turns NIF models as Skyrim, Skyrim SE and Fallout 4 ship them
  (20.2.0.7, user version 12, streams 83, 100, 130) into `.glb`: the node tree as glTF nodes,
  NiTriShape and BSTriShape shapes with every channel, skins with Gamebryo's bind matrices,
  the shader as the material and its colour map as PNG. Other versions, NiTriStrips,
  BSDynamicTriShape and skinned Skyrim SE shapes whose vertices are in their skin partition
  are refused by name. Tests only: no Bethesda game at hand.
- The shared glTF writer gained unit normals, tangents with their handedness from a stored V
  direction, and bone links scaled to sum to one.

## 1.24.0 (2026-11-19)
- Block-compressed DDS go back (doc 18.3): an edited PNG of a BC1 (DXT1), BC3 (DXT5), BC4
  (ATI1, BC4U) or BC5 (ATI2, BC5U) texture, FourCC or DX10, is written in the original's
  format with its header and a rebuilt mip chain, through ViWo's own pure-Python encoder
  (`core/encode_bc.py`, range fit per 4x4 block, deterministic; a 2048x2048 texture with its
  mips takes 10 to 20 s in BC1/BC3, 3 to 9 s in BC4/BC5). ATI2 keeps the red/green order
  ffmpeg shows. BC2,
  premultiplied DXT2/DXT4, signed BC4/BC5, BC6H and BC7 are still skipped with the reason.
- Godot: `decode.ctex` turns imported textures (`.ctex` Godot 4, `.stex` Godot 3) into PNG in
  process when their mipmaps are PNG or WebP or uncompressed 8-bit, and writes an edited PNG
  back in the same form (header, tag and channels kept, lossless WebP for a WebP original,
  mips rebuilt). VRAM-compressed and Basis Universal textures are counted as not decoded, and
  skipped on the way back, with the reason; so is WebP when Pillow lacks it.
- Cyberpunk 2077: an edited decompiled script goes back the game's way, as
  `r6/scripts/<its path>.reds` added to the patched copy beside `final.redscripts`; the plan
  says it needs the redscript compiler installed in the copy (ViWo does not compile). Two
  scripts decompiled from the one cache both go back. Decoders can now add a file beside the
  member (`Decoder.adds`) and say what the copy needs (`Decoder.back_note`); `member_back`
  receives the edited file's path in the decoder's output.

## 1.23.2 (2026-11-19)
- SLP way back: paint outside a sprite's frames (the sheet's cells are as large as the
  largest frame) cannot be kept; it was dropped without a word and is now counted in the
  result, which also says that colours go through the game's palette.

## 1.23.1 (2026-11-19)
- The SLP way back read back on real files: an icon sheet of Age of Empires II HD, marked,
  re-encoded into `interfac.drs` and the game's loose copy of it, decodes again with the mark
  in every frame (CONFORMANCE 18.3).

## 1.23.0 (2026-11-19)
- Unreal: every model UnrealAssetScout exports (UEFormat `.uemodel`, the only model format the
  pinned tool writes: it has no glTF option) also comes out as a `.glb` beside it: LOD 0 (never
  the Nanite LOD), positions, normals, tangents, every UV set, the vertex colour sets as data,
  one primitive per material section with its name, and for a skeletal mesh its bones in the
  reference pose with every weight. Unreal's left-handed Z-up space swaps Y and Z, as Unreal's
  own glTF exporter does. Option `[options.unreal] models = uemodel` keeps the tool's files
  only. A file the converter cannot read (another UEFormat version, zstd on a Python without
  `compression.zstd`, damage) is counted with the first reason; a skeleton alone is counted.
- Unreal: the export's failures were never seen. UnrealAssetScout ran with compact progress and
  no log, so its `[FAILED]` lines went nowhere and a game whose packages all need mappings said
  only "exported nothing". The tool now writes its log into the scratch folder, read back and
  deleted: the two free UE5 test games now say "3622 package(s) need the game's mappings
  (.usmap)" and "815 package(s) ...". Every package of both is cooked unversioned: they need the
  `.usmap` the RUNTIME agent (UE4SS) dumps from the running game.
- Source: `decode.mdl` turns studio models (`.mdl` versions 44 to 49 with their `.vvd` and
  `.vtx`) into `.glb`: LOD 0 of the default model of every body part, positions, normals, UVs,
  the bones in their reference pose with the engine's bind matrices, up to three weights a
  vertex, one primitive per mesh named after its material, and the material's `$basetexture`
  embedded as the PNG `decode.vtf` makes when its `.vmt` and `.vtf` are in the run. Source's
  Z-up axes turn to glTF's Y-up and every triangle is rewound (the `.vtx` lists front faces
  clockwise). The `.vvd` and `.vtx` are matched by name and checksum, so models COLLECT renamed
  (`name__1`) keep their own. Models without a mesh, untextured materials and models that
  cannot be converted are counted. No tool installed.

## 1.22.6 (2026-11-19)
- PATCHED COPY uses the mod-or-overwrite choice made in ASSETS and names it in its summary
  line; it wrote with the default without saying so.

## 1.22.5 (2026-11-19)
- The way back of a decoded file is seen in a running game: Doki Doki Literature Club shows
  a line edited in its decompiled `splash.rpy`, compiled by the game from ViWo's patched copy
  (`sqc/proof/renpy-ddlc-script.jpg`).
- `tools/game_shot.ps1` captures the whole window on a scaled display (it measured in scaled
  pixels and cut the right and the bottom off).

## 1.22.4 (2026-11-19)
- Unity under `viwo serve`: the ceiling tightened around a doubtful read is the whole
  process's, so two jobs could lift each other's and a script could lose its fields for what
  another job held. Such reads now run one at a time, and a failed one is read a second time
  before its script is given up (doc 9.2).

## 1.22.3 (2026-11-19)
- The game loads the change on Unreal too: a UE5 test game starts with the window title set
  in its `DefaultGame.ini`, loaded from ViWo's `_P.pak` (`sqc/proof/unreal-voids-cave.jpg`).

## 1.22.2 (2026-11-19)
- The game loads the change on KiriKiri too: a test game shows its marked title background
  from ViWo's `patch.xp3` (`sqc/proof/kirikiri-ubu.jpg`).

## 1.22.1 (2026-11-19)
- KiriKiri: the patch archive holds each edited member by its file name. The engine searches
  `patch.xp3` at its root only, so members written with their folder were never found and the
  game kept showing its own files. One file name edited in two folders is said; a file the
  game's scripts name with its folder (`image/logo.png`) is read from the game's own archive
  and no patch changes it, which the outcome says.

## 1.22.0 (2026-11-19)
- Everything decoded goes back (doc 18.3): an edited decoded file (a PNG, glTF, JSON
  table or `.rpy` that DECODE wrote) is encoded into the format of the member it came from by
  the decoder that read it (`Decoder.encode`), then planned, packed and verified like any other
  edit; the plan says per file the member, the encoder and the container's packer, and every
  file that cannot go back is named with its reason (audio and video: proprietary encoders).
  First ways back: VTF (uncompressed), SLP (through the palette), Total War `.loc`, Ren'Py
  `.rpy` (the stale `.rpyc` removed so it cannot win), CR2W through WolvenKit's `import` and
  `convert deserialize`, DDS when the original is uncompressed. `viwo repack --mode
  mod|overwrite` and the API's `mode`: `mod` (default) keeps the game's own files untouched
  where the engine loads something over them, `overwrite` rewrites the container; Ren'Py
  changes by that default (edited archive members go loose under `game/`, which Ren'Py reads
  first; `--mode overwrite` rewrites the RPA as before). The ASSETS tab in PATCHING shows it
  all and writes it.

## 1.21.1 (2026-11-19)
- Overwatch: the character of each skin is named `... - (main) <id>.glb` and so listed first;
  a skin's dozens of props and effect shapes had the same kind of name, and nothing said
  which file was the hero.

## 1.21.0 (2026-11-18)
- Unity: every Mesh also comes out as a lossless `.glb` beside UnityPy's `.obj`: positions,
  normals, tangents, every UV set, vertex colours as data, each sub-mesh as a primitive (32-bit
  indices only when needed), and for a skinned mesh its bind poses, bone weights and the bone
  names and tree of its SkinnedMeshRenderer; the material's main texture is embedded. Unity's
  left-handed space is mirrored on X with every triangle rewound, so a model keeps its sides
  and its front faces. A mesh the `.glb` cannot hold keeps its `.obj` and is counted with the
  first reason; untextured meshes and bones named by hash are counted too. No tool installed.
- The glTF writer is shared (`viwo/contracts/gltf.py`) instead of living in the Overwatch
  plugin; Overwatch's `.glb` files are byte for byte what they were.

## 1.20.76 (2026-11-18)
- Patch sets: two patches that would write the same bytes of one file (offset, RVA or AOB,
  once located) are refused at plan time as `overlap`, each naming both; they used to corrupt
  each other, report `verified` and then refuse to apply again. An AOB pattern counts its
  overlapping matches (`CC CC CC` in four bytes of int3 padding is two), so it is never
  written where it is not unique.
- Downloads: an HTTP error answer is no longer taken for a dropped connection. A 4xx fails at
  once with its status and a hint ("the URL answers HTTP 404 Not Found: the release may have
  moved; report it"); a 5xx is tried again and named when it ends the download. Without a
  pinned size (indexes releases) a body that drops is resumed or fails by name; it was
  returned as if whole. The size the server gives also drives the progress line.
- Overwatch: `[options.overwatch] query` reaches only the mode it is for: an entry goes to
  `extract-unlocks`, `extract-maps: Rialto` to that mode, a `--flag` to every extract mode; an
  entry no running mode takes is said. It used to go to every extract mode.
- SORT: a 3D model packed with Draco, Basis (KTX2) or meshopt says under it that the viewer
  fetches its decoder from the internet.
- COLLECT: a file an antivirus takes between its hash and its copy is named among the
  unreadable files and the run goes on (it stopped the extraction); no half copy is left. A
  staging file whose copy landed but whose original stays held is collected.
- `.gitignore`: the entries of other projects (C.O.R.E., RPy Extractor) removed.

## 1.20.75 (2026-11-18)
- The game folder is read-only by construction: one guard (`pipeline/guard.py` `guarded`)
  hands every writer its folder and runs before any lock, claim, copy or work. `analyze`,
  `attach`, `agent`, `dump`, `trace`, `hook`, `profile`, `record` and `sanitize` never checked
  their workspace against the game from the CLI; a patched copy that was reused skipped the
  check, so an install a patched copy was copied over let `patch --out`, `mod apply` and
  `agent` write into the game itself. Now refused (exit 3), named, with a hint. Without a game
  path (a run on a process id, `record`, `sanitize`) a patched copy and a folder of files that
  is no ViWo workspace are refused, as the API already did for runs; what cannot be told there
  is listed in HANDOFF. `repack --out` is checked before it plans, also with nothing to pack.
- The workspace lock belongs to its live owner: a run past six hours (WolvenKit, DataTool) no
  longer loses its lock to a second run with `--on-existing replace`. The owner is checked
  first (pid and its start time, so a reused pid is told apart; host), the lock's time is
  refreshed every minute while it is held, and its age decides only for an owner on another
  machine. A kept lock names its file.
- Failover gives each attempt a fresh folder (UNPACK, EXPORT, CARVE, DECODE, analysis,
  capture, the round trip's pack and verify): a spare no longer writes beside the truncated
  files and export map a failed main left, which were collected as good. CARVE, DECODE,
  analysis, capture and the round trip no longer start the spare after a cancel.

## 1.20.74 (2026-11-18)
- SORT: a type pick (IMG, AUD, VID, 3D, TXT, BIN) lists that type over the whole workspace,
  from its first page; it filtered only the hundred files of the page on screen, so the
  models of a large workspace were hundreds of pages away.
- SORT is quick on a large workspace: the queue is kept between requests for as long as no
  folder of the workspace has changed (every page and pick walked all its files: 2.3 s a
  click on 24,800 files, now under 0.1 s). Only the answer to the latest pick is shown (an
  older, slower one could replace it and leave the queue empty).

## 1.20.73 (2026-11-18)
- Proven: the game loads the change. A patched copy of a Ren'Py, a Unity and an RPG Maker MV
  game each started and showed the edited image on its first screen (`sqc/proof/`,
  SQC-RT-LOAD). `tools/game_shot.ps1` starts a game, captures its own window and ends it.

## 1.20.72 (2026-11-18)
- Line budgets get headroom (owner): each package budget stands at about 125 % of its size
  today. The caps per function, file and line stay; the reclaim passes stop.

## 1.20.71 (2026-11-18)
- Security (review, 2026-11-18), four fixes:
  - a request's path is checked before it is joined or resolved: `/%5C%5Chost%5Cshare` on the
    static or preview route made Windows open an SMB connection (and send the login hash);
  - workspace files are served sandboxed and never sniffed, so a game's `.html` or `.svg`
    opened through `/preview/` can no longer run on ViWo's origin and read the API token;
    ViWo's page runs only its own scripts and cannot be framed;
  - a batch tool's arguments (Ghidra's `analyzeHeadless.bat`) are always quoted: a game file
    named `x&calc&.dll` ran `calc` during analysis;
  - a run record masks every option of an owner the runtime does not know (an AES key given
    to a misspelled or switched-off plugin was stored in clear).

## 1.20.70 (2026-11-18)
- Overwatch: every model DataTool writes (`.owmdl`) also comes out as a self-contained
  `.glb`: all submeshes with normals, tangents and UV sets, the skeleton in its reference
  pose with every bone weight, the colour and normal textures embedded as extracted (PNG
  bytes untouched), the vertex colour sets kept as data. No tool is installed for it; the
  file names say hero, event and skin. `[options.overwatch] models = owmdl` turns it off.
  Opens in SORT's 3D preview and in any glTF viewer.

## 1.20.69 (2026-11-18)
- SORT: the preview follows the window. Its size rules select on `data-kind`, which the
  page never set, so a video or a picture kept its own size; the figures now carry it.
- SORT: a 3D preview for `.glb` and `.gltf` (orbit, zoom) through the pinned `model-viewer`
  script, served by ViWo itself (`/vendor/`); "3D" is a type of its own in the filters.
- Reclaim pass, web UI: 119 counted lines fewer (5,400 to 5,281 before the viewer), the UI
  tests unchanged; dead style rules dropped.

## 1.20.68 (2026-11-18)
- COLLECT hashes with its own read loop again (owner): `hashlib.file_digest` needs Python
  3.11, and an extraction on 3.10 failed there.

## 1.20.67 (2026-11-18)
- Pinned downloads pick up where a dropped connection stopped (a Range request) and go on
  for as long as each try brings the file further; three tries in a row that bring nothing
  end it. They restarted from zero three times and gave up, which no 75 MB tool survived
  on a link that drops.

## 1.20.66 (2026-11-18)
- Overwatch: `[options.overwatch] query` (or `--option overwatch.query=...`) hands DataTool
  its own query, `;` between several (`Tracer|skin=*`), so a few heroes can be extracted
  instead of everything; the Steam layout of the install is detected; DataTool's lines are
  relayed to the console. DataTool pinned at 2.25.1.0 (the game's build 154905 needs it).

## 1.20.65 (2026-11-11)
- Docs: HANDOFF rewritten to half its length (how to work, real-game runs as a table, open
  work grouped by what it waits on); the per-engine matrix of CONFORMANCE in one-word cells
  with the proof of each `real` under it; the README's UI section as a list.
- SQC: results recorded for CLI-14 to 17, SAFE-09 and CTF-01 (51 of 51 flags on the eleven
  free titles with today's flag sets).

## 1.20.64 (2026-11-11)
- Reclaim pass, core sub-packages: 83 counted lines fewer (4,502 to 4,419), tests unchanged:
  one bounded copy loop for carving, the version diff's pairing in one helper, the
  dependency report in one walk.

## 1.20.63 (2026-11-11)
- Reclaim pass, core modules: 86 counted lines fewer (3,125 to 3,039), tests unchanged: one
  `read_json` for the files ViWo reads back, `tell` instead of repeated sink checks, the
  provenance rewrite through `write_atomic`. The budget's patience test no longer depends
  on timing.

## 1.20.62 (2026-11-11)
- UI review, more fixes: SYSTEM says what the tools not found are (on demand, not installable
  here) and its subtitles follow the numbers; a long stat value wraps instead of being cut; a
  path field shows its tail after editing; example text in fields is dimmed and italic;
  disabled buttons and off switches are easier to see; "1 FILE" in MERGER; the antivirus
  warning says the job goes on.

## 1.20.61 (2026-11-11)
- CONFORMANCE: edit, repack and read-back proven on real games for REDengine, Unity, Unreal
  (pak), Ren'Py, KiriKiri, Source, Genie and Warscape, beside Doom (deep passes at 1.20.56).
  The game loading a change stays open on every engine.

## 1.20.60 (2026-11-11)
- Reclaim pass, plugins: 186 counted lines fewer (4,814 to 4,628) with every test unchanged:
  BSA and BA2 extraction share one loop, the asar reader and writer one tree walk, Doom's
  lump naming one function, Unreal's key masking is the contract's; budgets lowered.

## 1.20.58 (2026-11-11)
- `viwo --ini <relative path>`: the tools under `third_party/` are found by absolute path (a
  tool started in another folder was not found).
- Deep pass: a binary file under a text name gets a changed byte, not an added line.

## 1.20.57 (2026-11-11)
- Repack: the edit set is hashed several files at once (`repack --plan` took 47 minutes on a
  183,000-file workspace, one file at a time).

## 1.20.56 (2026-11-10)
- Memory budget: a run that fits goes ahead of a larger one still waiting, for 15 s at most
  (parts of a timed run waited three times longer for memory than their tools ran, behind
  single large runs). WolvenKit's runs are capped at their estimate, 1.5 GB at least.

## 1.20.55 (2026-11-10)
- UI: example paths in the fields read as this machine writes paths (`C:\path\to\game` on
  Windows); the game folder field has one name on every view.

## 1.20.54 (2026-11-10)
- WolvenKit: only its first run goes alone (it was the whole first part of 600 files, twelve
  minutes of a timed run with one tool at work); each part says how many runs it took, their
  time and how long they waited for memory.

## 1.20.53 (2026-11-10)
- `[slot_policy] <slot> = main_only`: that slot's spare is never bound, promoted or run
  (`failover` stays the default). `viwo slots` and `viwo info` show it.

## 1.20.51 (2026-11-10)
- Deep pass: `--arms` runs part of it (for a repack proof: `static,patching`), `--workspace`
  reuses an extraction, and `tools/games_pass.ps1 -Deep <arms>` runs it on the copy of an
  installed game.

## 1.20.50 (2026-11-10)
- Rung D4, hook scripts: `viwo hook --pid|--name --script FILE --seconds S --workspace W` (and
  RUNTIME, RUN HOOK SCRIPT; `/api/runtime/hook`) runs your own Frida script in a running game
  through the pinned Frida's own command line, a tracked child. Frida loads the script again
  each time you save it; every line it prints shows in the console as it comes and is kept in
  `.runtime/hook/<pid>-<time>/hook.log`. ViWo ships no script and no loader, attaches only and
  asks for no elevation; a running anti-cheat service is said as a warning. Verified on a real
  process that is not a game.
- Rung D4, overlay: still open, with the reasons written down (doc 11.7). Special K is not
  pinned: by default it works around CAPCOM's copy protection, and it shows its licence screen
  inside the game. MangoHud's release tarball installs into `/usr` with `sudo`.

## 1.20.49 (2026-11-10)
- WolvenKit's runs are sized before they start: each is planned to fit 2 GB from the files'
  sizes (an animation unfolds about 250 times, measured), a large file runs alone under its
  own estimate, and what failed runs again once with twice the room. The memory budget
  serves in the order asked. (1.20.42's "start small, split on failure" made a timed
  extraction slower: a failing run took a minute to say so, and a retry under the whole
  share stopped every other run.)

## 1.20.48 (2026-11-10)
- `viwo --plugin <id>=on|off` and `viwo --slot <slot>=<main>[,<spare>]` (before the command,
  repeatable): a plugin or a slot's backends for one run, over the ini and the profile; the
  source reads `cli` in `viwo info`. A bad id is said and the default used.

## 1.20.47 (2026-11-10)
- The technical deck is built from the repository: `python tools/presentation/deck.py` writes
  the PowerPoint from the frames, the counts of the code and the CTF results; pptxgenjs is
  pinned as one file and installed by itself.

## 1.20.46 (2026-11-10)
- SQC suite brought up to the current build: view numbers dropped (codes are computed), stale
  lines fixed, new checks for guides, workspace conversion, SORT's group trash, the UI's
  failure lines, the memory ceiling, the console's stage lines and `attach.net`, each marked
  NOT RUN until an operator runs it; CTF flags rewritten so none passes on an empty result.

## 1.20.45 (2026-11-10)
- Rung D4, network: `attach.net` opens mitmproxy (pinned third-party tool, MIT, installed by
  itself into `third_party/`) as a tracked child from RUNTIME or `viwo attach`: a regular
  local proxy on this machine only, its flows saved under the target's folder in the
  workspace. ViWo says where to point the game and what HTTPS needs; nothing asks for
  elevation. A workbook walks through it.

## 1.20.44 (2026-11-10)
- Packaging: the build looks for packages in `viwo` only. It walked `viwo-data` too and failed
  when a running job's temporary folders changed under it.

## 1.20.43 (2026-11-10)
- UI review, first fixes: error toasts stay until dismissed; the closed log dock shows the
  last line; the top bar fits narrow windows (labels dropped up to 1500 px); buttons say what
  they are doing (CONVERTING…, SCANNING…); the workspace dialog answers an empty or unchanged
  folder in words; job durations read as times.

## 1.20.42 (2026-11-10)
- One memory budget for the tools that run at once (`ctx.memory`, doc 9.2): a capped tool
  holds its cap out of ViWo's share of the machine and waits while the share is out.
- WolvenKit's runs adapt: 150 files a run (ten animations count as a run), 2 GB to start;
  what failed for want of memory is run again beside fewer files, then alone with twice the
  room, up to the share; what WolvenKit cannot read is not run again. Decode was 86 % of a
  timed Cyberpunk extraction with fixed 20-file runs under 4 GB.

## 1.20.41 (2026-11-10)
- Unity IL2CPP: MonoBehaviour fields are kept. A rebuilt layout that does not fit no longer
  switches every rebuilt layout off: the one script is remembered and skipped, every other
  script keeps its fields, and the export says how many scripts were dropped. Each such read
  runs with the memory ceiling at what ViWo holds plus 1 GB (`OS.memory_room`), so a misfit
  fails at once instead of climbing to the ceiling first.

## 1.20.40 (2026-11-10)
- Fix: WolvenKit could take the machine's memory. Its `export` keeps everything it converts
  until the process ends: one batch of 150 animation files took 13 GB in 30 seconds (measured
  under a watchdog; a timed run was stopped at 20 GB with 1.6 GB left free). `export` now gets
  20 files a run, and every WolvenKit runs under a 4 GB cap.
- Child tools can be capped (`ProcessRunner.run_capped`): Windows, a job object per tool;
  Linux, the child's data limit (written, not yet run on Linux). A tool past its cap fails by
  itself and is counted; a cap that could not be set is said.
- The decode runs as many WolvenKit at once as fit in ViWo's share of the machine
  (`memory_limit`): 4 on a 32 GB machine, not 7. Docs 8 and 9.2.
- Checked: the parallel RDAR unpack writes the same bytes as the serial one (two real
  archives, 9,937 files, compared by sha256).

## 1.20.39 (2026-11-10)
- Always said (owner): a stage that ends says how long it took, and every extraction closes
  with its total and the time per stage. CLI progress lines carry the time of day. WolvenKit's
  own output lines are relayed live during the decode. Doc 3.1.

## 1.20.38 (2026-11-10)
- Games pass rerun: Schedule I passes 12 of 12 flags at 1.20.37 (7 of 12 on 2026-11-03),
  Age of Empires II HD 13 of 13 at 1.20.34, Approximately Up 9 of 10 at 1.20.36. CONFORMANCE:
  extract reads "real" for Unity and Age of Empires.

## 1.20.37 (2026-11-10)
- Fix: extracting Schedule I (Unity, IL2CPP) took the owner's machine down, twice. A
  MonoBehaviour read with a layout rebuilt from Cpp2IL's stand-ins did not fit its object; the
  reader took a garbage length for an array and asked for memory without end (1.2 GB to 15.5 GB
  in three seconds, measured under a watchdog).
- ViWo's own process now has a memory ceiling: `[startup] memory_limit`, default 50 % of the
  machine, 0 lifts it. Past it an allocation fails inside ViWo as a MemoryError, one counted
  failure, and the machine stays up. Windows: a job object that leaves child tools out; Linux:
  the soft data limit (written, not yet run on Linux). The console says at start whether it
  holds. Doc 9.2.
- The Unity export counts such a read, switches the rebuilt layouts off for the rest of the
  export and says so once. Schedule I now extracts in ten minutes: 9,663 assets, 1.2 million
  objects as JSON, 9,811 files (138 on 2026-11-03).

## 1.20.36 (2026-11-10)
- Fix: `viwo --json` could answer text before its JSON. On a Unity IL2CPP game UnityPy's
  native layout generator prints "Error generating tree nodes" straight to the process's
  stdout; the games pass then could not read the extraction's answer and recorded a failed
  step with no plugins and no warnings (Approximately Up, 2026-11-03 and 2026-11-10). While a
  `--json` command runs, the process's stdout is now pointed at stderr and restored for the
  one document. Doc 12.4.
- `tools/games_pass.ps1` writes its log as UTF-8 whatever the shell's default is.
- Games pass rerun at 1.20.34: Age of Empires II HD passes 13 of 13 flags (genie detected,
  3,923 SLP sprites as PNG).

## 1.20.35 (2026-11-10)
- CONFORMANCE corrected against the passes' own flags: Unity and Age of Empires were written
  as proven on a real game, but Schedule I passed 7 of 12 flags, Approximately Up 1 of 10 and
  AoE 0 of 1 (2026-11-03). They read "partial" with what was missed; "real" now requires every
  flag of the game's pass. The three passes are being rerun at 1.20.34.

## 1.20.34 (2026-11-10)
- COLLECT hashes its files several at once (the slow part of 160,000 files on the Cyberpunk
  demo subset); they are still placed one at a time, in order, so names and provenance are
  the same on every run.

## 1.20.33 (2026-11-10)
- Never silent: after the decode, the decoded files (73,000 on the Cyberpunk demo subset) were
  hashed and moved into the workspace without a line, for more than ten minutes. It is said,
  counted and summed up now.

## 1.20.32 (2026-11-10)
- CARVE runs on the worker pool: both the pass that finds which files nothing recognizes (a
  second silent pass over every extracted file, now announced and counted) and the carving
  itself. Carve folders are numbered in the files' order, so a run comes out the same.

## 1.20.31 (2026-11-10)
- RDAR archives unpack their members several at once and say where they are
  ("basegame_4_gamedata.archive: 31,200/57,033 members", every second; before, one line when
  the archive was done, minutes later). Measured on basegame_4_animation (5,648 members, the
  machine busy): 15.7 s on one worker, 9.2 s on sixteen. Plugins reach the worker pool through
  their context (`ctx.each`), never by importing the core; the pool holds at most twice its
  worker count of results, and starts nothing after a cancel. Doc 3.1.

## 1.20.30 (2026-11-10)
- Fix: trashing or renaming a large file in SORT failed ("in use"). For an audio file over
  20 MB the page fetched the file for its waveform, found it too large and left the download
  unread, so the server kept the file open and Windows refused the move. The page now aborts
  that download, and the server no longer depends on the page: every preview stream is closed
  before anything is written into the workspace (`App.release_previews`), so no open preview
  blocks a trash, a rename, a group move or a cleanup.
- Never silent (owner): every failure a route answers is a line in the log and the activity
  console, with its route, message and hint (`[FAILED] POST /api/sort-trash: ...`,
  `App.said`). Before, a refused or failed action showed only in its toast. The toast no longer
  points to JOBS for something JOBS did not hold.

## 1.20.29 (2026-11-10)
- The WolvenKit decode runs several parts at once (owner): one WolvenKit process used one
  core of twenty for 100 minutes on the Cyberpunk demo subset. The parts of 600 files now run
  on the worker pool, as many as the budget and the memory allow (4 GB kept per tool: 8 at once
  on a 32 GB machine), results in the parts' order; the run says how many parts and how many
  at a time, then each part as it finishes. The per-file decoders use the same budget (they
  were fixed at 8 threads). Docs 3.1 and 8.

## 1.20.28 (2026-11-10)
- The silent 20 to 38 minutes after UNPACK on Cyberpunk 2077 are found and gone: every
  extracted file (87,000) was checked for being a nested archive, one at a time, with no log
  line. The search now runs on a pool of workers and says what it does ("Looking for nested
  archives in N extracted file(s) on W workers", then a counter). First stage of the parallel
  pipeline (owner): `core/pipeline/pool.py` is the one worker budget, 80 % of the processors
  (`VIWO_WORKERS` overrides), results in order so every run comes out the same. Doc 3.1.

## 1.20.27 (2026-11-10)
- HANDOFF: the state at this version, the local `main` fast-forwarded to `makeover` (187
  commits), and what waits on GitHub (the push of both branches and their tags, the rename to
  ViWo).

## 1.20.26 (2026-11-10)
- The technical PDF ends with the CTF results (owner): the flags of every real-game pass (per
  game: engine, files out, flags passed and missed, the game folder unchanged) and the
  challenges run by hand, recorded as they come in `viwo-data/ctf/results.json`
  (`tools/presentation/ctf.py`). Its Quality section says what a commit now runs.

## 1.20.25 (2026-11-10)
- CONFORMANCE tracks what "done" means per engine (owner): extract, edit + repack, verify (read
  back) and the game loading the change, each cell either proven on a real game (named, with
  its date or version), covered by tests only, or open; plus a Linux column (the suite and the
  pinned Linux builds; no real game run on Linux yet). Extract is proven on eight engines;
  edit, repack and read-back only on Doom (Freedoom); no engine has the game loading a change
  proven yet. A row closes only when every cell reads real (doc 16.0c).

## 1.20.24 (2026-11-10)
- CONFORMANCE keeps no hand-written counts or version: its summary table said 166 implemented,
  5 partial, 16 open against 1.6.2, stale for a long time. The technical PDF counts the rows
  from the tables (`tools/presentation/reference.py`).

## 1.20.23 (2026-11-10)
- A commit never runs the whole suite by default (owner: it took most of the suite for a
  change deep in core). The selection is now the tests a change is close to: what a test
  imports and what those import, `tests.helpers`, `boot` and the registry reached but not
  passed through; a plugin change adds the tests that name the plugin and four plugin-wide
  checks; a change to the pipeline runs the pipeline's own tests; a file counts as named only
  by a string in code, never by a docstring or a comment. For the IL2CPP change of
  1.20.21 that is 6 test modules instead of 91. Only `pyproject.toml`, or `--full` before a
  merge or a tag, runs everything. Doc 17.

## 1.20.22 (2026-11-10)
- The plugin system is held sealed by a test (`tests/test_sealed.py`): a new engine plugin
  added as one package where discovery looks is discovered, loaded, bound to its slot, given
  its own distro profile, detected and its archive extracted, with no change to core. The only
  files outside `viwo/plugins/` that a new engine changes are the generated distro files.

## 1.20.21 (2026-11-10)
- Core knows no engine's file layout: an analysis target declares where a tool expects each of
  its paths (`AnalysisTarget.layout`, doc 6.1), and core rebuilds that folder from the copied
  inputs (`managed.laid_out`, every place through `safe_member` and `inside`). The Unity plugin
  declares its player's layout for Cpp2IL (`il2cpp_layout`); `core/analysis/managed.py` no
  longer names `GameAssembly.dll` or `il2cpp_data`. The analysis copy keeps every field of the
  target (`dataclasses.replace`).

## 1.20.20 (2026-11-10)
- After a server restart the open page reloads itself: the old page's API token is refused
  (`code: "token"` on the 403), so it fetches the new one instead of failing every poll with a
  SECURITY line in the log; at most once a minute, so a missing token cannot loop.

## 1.20.19 (2026-11-10)
- Faster commits (owner): the tests a commit runs go in parallel (`tools/run_tests.py`), one
  process per test module on a pool of 80 % of the logical processors (owner's cap, counted at
  the start of the run on any OS), the largest first; the few
  modules that bind a fixed port, drive the browser or time child processes run alone after the
  pool. Doc 17. CLAUDE.md and HANDOFF name it and no longer state a test count (they went
  stale: 567 and 611 against 612).

## 1.20.18 (2026-11-10)
- Fix: trashing or renaming in SORT the song its preview was playing failed with Windows error
  32 ("being used by another process"), named against the whole workspace folder. SORT now
  stops its preview and drops the source before the file moves, the move waits up to two
  seconds for the stream to let go (`sorting.move_released`), and a file still in use is named
  with what may hold it (`api.app.in_use`).

## 1.20.17 (2026-11-10)
- Fix: RESTORE and DELETE on a WORKSPACE group answered "No trashed folder" when the group's
  trashed files had been trashed one by one in SORT (`.trash/items/<ext>/`): the trashed count
  included them, the actions did not. RESTORE now brings back the newest trashed version of the
  group and every file of it trashed in SORT (each to its own place, its provenance entry
  following); DELETE removes everything of the group in the trash, as its confirmation says.

## 1.20.16 (2026-11-10)
- The top bar fits: JOBS leaves the strip (owner), the job chip (RUNNING or JOB IDLE) opens it;
  the strip is SYSTEM, WORKBOOKS, RUNBOOKS, SETTINGS (00 to 03). A global view registered with
  `strip: false` is routed but has no chip and no number; its panels carry its `tag` (JOB).

## 1.20.15 (2026-11-10)
- CONVERT INTO WORKSPACE (owner): the switch dialog turns a folder of your own files into a
  ViWo workspace. It says first what moves (files, groups by type), then moves every file into
  the group of its type with its original path, sha256 and size in the provenance (`kind:
  adopted`), removes the folders the moves emptied and writes the marker last. Nothing is
  deleted, duplicates included; a drive root or the home folder is refused. `core/adopt.py`,
  `POST /api/workspace/adopt`; the workspace handlers moved to `api/handlers_workspace.py`.
  Doc 4.3.

## 1.20.14 (2026-11-10)
- Core lists no engine for the distros: a built-in names its own distro profile in its manifest
  (`PluginManifest.profile`; renpy, unity, unreal and godot do), and `distros.py` reads the
  profiles from the plugins (`profiles()`, `own_profiles()`) instead of its fixed list. The
  twelve generated files are byte-identical. Docs 2 and 9.

## 1.20.13 (2026-11-10)
- README: "crackers, cheaters" taken out of the audience list (owner: legal exposure). The
  wording only: the tool does exactly what it did.

## 1.20.12 (2026-11-10)
- The suite on Linux without the optional extras: the seven tests that need UnityPy, lz4 or
  py7zr skip with the module named (`tests.helpers.needs`), as the others already did. Four
  tests that assumed Windows hold on both: the config boot test boots the host's own distros;
  the agent test's rewritten fake game keeps its shebang; the sort test's refused name is one no
  OS accepts (`bad/name`); the Ghidra and RenderDoc first-run tests put every config and data
  home, Windows and XDG, in a temporary folder (`tests.helpers.homes`; on Linux they wrote into
  the real home). The survey's Unity case binds its exporter for the fake UnityPy instead of
  relying on UnityPy being installed at boot.

## 1.20.11 (2026-11-10)
- A commit runs only the tests its change can affect (owner: no tests on code that has not
  changed). `tools/affected.py` builds the import graph of `viwo`, `tests`, `tools` and
  `packaging` and picks the test modules that reach a changed module, the changed tests, and
  the tests whose code names a changed file. A docs-only change runs no tests; a change to the
  pipeline or `pyproject.toml`, or `--full`, runs them all. Doc 17.

## 1.20.10 (2026-11-05)
- Presentation: the RUNTIME debugger frame scrolls to the DEBUGGER AND MEMORY panel by its
  title (a positional selector had matched another panel). The recapture at 1.20.9 came out
  whole otherwise: 183,621 files from the seven archives, the counter moving through the
  WolvenKit decode.
- CAPTURE says the frames are kept (they open in RenderDoc) with their textures; WORKBOOKS
  names a tool as its users know it (RENDERDOC, CHEAT ENGINE), not by its pin id.

## 1.20.9 (2026-11-05)
- Never silent: a batch decoder (WolvenKit's `decode.cr2w`) is called 600 files at a time
  (`decode.PART`), so the "Decoded files" counter moves between calls. On the Cyberpunk demo
  subset the counter had stood still for 98 minutes while WolvenKit converted 62,653 files in
  one call. A cancel stops after the part running; the parts' failures stay one warning per
  slot (the first, and how many other parts failed). Doc 08.
- Presentation: every view change waits until the view has finished loading (a skeleton
  reading a large workspace was captured as the WORKSPACE frame), and the walk waits up to four
  hours for the extraction (the demo subset takes about 2 h 20 min; the first capture ran out
  of its two hours during the decode).

## 1.20.8 (2026-11-05)
- A GPU capture keeps its frames: every RenderDoc capture (`.rdc`) is collected into the
  workspace (`rdc/`) beside the textures harvested from it, so the frame opens in qrenderdoc
  (doc 11.2). Before, only the textures were kept and the frame was deleted with the run's
  temporary folder.
- A fifth workbook, "Read a captured frame" (RenderDoc 1.47: draws, textures, meshes, shaders),
  with a HOW TO button on CAPTURE's target panel. `opens` stays optional: no handoff opens
  qrenderdoc.

## 1.20.7 (2026-11-05)
Reclaim, with the owner's approval:
- The tools ViWo's own backends need are described once, in `viwo/data/dependencies.json`
  (label, kind, executables, install folders, environment variable, hint); a definition is now
  `DependencySpec.of("x64dbg")` (40 definitions, 39 tools; every spec compared before and after:
  identical). Pillow and lz4 stay in code (their modules word them differently). A plugin of
  others still builds its own `DependencySpec`. `viwo` 16,920 -> 16,701 counted lines.
- Contract members nothing used are gone: the `Stage` enum (the runner's `_stages` is the
  order), `Unarchiver.supports_keys`, `DependencySpec.packages`. Kept: the OS layer's
  `long_path`, `case_sensitive` and `python_executable` (implemented and tested; `long_path` is
  Windows' long-path form, a capability rather than dead code).
- Not done: letting API handlers raise instead of answering failure dicts (their dicts are what
  tests, the jobs entry point and other handlers call; about 30 lines against many tests and
  changed HTTP statuses).
- Budgets lowered: `viwo` 16,750, `viwo/core` 7,275, `viwo/contracts` 860.

## 1.20.6 (2026-11-05)
- Genie and Warscape detect by their archive signatures only (DRS, PFH packs); their title
  executables are no longer evidence (doc 2.10, the fourth audit's last open point). Source's
  `hl2.exe` and `srcds.exe` are the engine's own launcher; Warscape's per-title RPFM schema
  table is data the DB format needs, no per-title code (doc 2.10 says so).
- Fix: `pack.asar` wrote an unpacked member into a subfolder of `app.asar.unpacked/` only when
  that folder existed, and dropped a member whose name led out of it without a word; the folder
  is made and such a member is said. (In 1.20.5 by accident, with its tests.)
- Coverage: the guides' CLI, routes and edge values, and the asar integrity blocks, as
  property tests (`tests/test_guides_more.py`, `tests/test_asar_pack.py`).
- Presentation: `frames.py` cancels and waits for any job still running before it exits (an
  interrupted Cyberpunk extraction had left 50 GB of staging); the walk waits up to two hours
  for the extraction; the demo runs on the games pass's Cyberpunk subset.

## 1.20.5 (2026-11-05)
- Embedded child GUIs dropped (owner): x64dbg, Ghidra, Cheat Engine and qrenderdoc stay native,
  in their own windows as tracked children. Doc 19.4 records the decision (its design removed),
  16.4 item 4 and CONFORMANCE follow; workbooks are shown beside the tool, and what is done in a
  child tool stays a note the user writes in a workflow.
- Presentation: a frames run on Cyberpunk 2077 showed the walk cannot wait for a full
  extraction (hours); HANDOFF records the two ways to stage the demo, for the owner to choose.

## 1.20.4 (2026-11-05)
- Presentation: the walk shows WORKBOOKS, RUNBOOKS with the workflow recorder, and RUNTIME's
  debugger and memory panel; the top bar's five tabs; the technical PDF gains "Guides for the
  child tools" (doc 19). `frames.py --features` turns switches on for the run only (the ini is
  not written) and the run's extraction workspace is deleted afterwards unless `--keep`.

## 1.20.3 (2026-11-05)
Reclaim pass (behaviour unchanged; budgets lowered in `loc_caps.ini`):
- `viwo/web` is back under its own 5,400-line budget: the rules both themes held byte for byte
  moved to `css/skin.css`, loaded between `base.css` and the theme (the cascade kept: a rule
  is shared only when no theme rule before it names the same selector; every view's screenshot
  compared before and after); empty rules dropped; the five views' CANCEL code is one
  `cancel()` on the progress block.
- `viwo` 17,187 -> 16,920 counted lines (budget 17,200 -> 16,950), `viwo/core` 7,469 -> 7,357
  (7,475 -> 7,375): the `from __future__ import annotations` no module needs on Python 3.11+
  (176 modules; `viwo/data/` keeps it, it runs in other interpreters), tool lookups as one
  walrus line, the built-in plugins' `PLUGIN` markers the registry does not need (it finds the
  module's one plugin class), data-like tuples and backend lists on a line or two.
- Not done, decisions for the owner (HANDOFF): moving the tools' `DependencySpec` metadata into
  `tools.json` (doc 2.6), dropping contract members nothing calls (`Stage`, `supports_keys`,
  `DependencySpec.packages`, the three OS methods of doc 1), letting API handlers raise (their
  HTTP statuses would change).

## 1.20.2 (2026-11-05)
Fourth audit (the work since 1.15.5; two independent reviews, every finding verified, each with
a property test in `tests/test_audit4.py` or beside its code):
- Fix: members whose names differ only in case (`Foo.txt`, `foo.txt`, one file on Windows)
  overwrote each other silently; the second gets a free name and is recorded. A member named
  like ViWo's own files (`.viwo-names.json`) is altered, so an archive cannot plant a names
  record; folders keep the spelling they were first written with, so the record matches disk.
- Fix: a patched copy whose container held a name Windows cannot hold (`what?.js`) was reported
  not verified: the read-back now follows the names record (round trip, the XP3 patch).
- Fix: a Doom PWAD in a subfolder could not be packed (the palette was looked for beside it,
  not at the game root where extraction found it); a PNG saved by an editor without its grAb
  chunk lost the sprite's offsets (the lump's own are kept); the WAD read-back decodes each new
  lump as extraction does instead of comparing the encoder with itself.
- Fix: VTF env maps before 7.5 carry a seventh face; their largest mipmap was read at the
  wrong offset.
- Fix: a game plugin whose engine plugin is off is no longer loaded (named in the problems).
- Bethesda overrides say that Oblivion, Fallout 3 and New Vegas (BSA 103/104) need archive
  invalidation, and why a member was not written (a name Windows cannot hold as a file, or one
  leading out of the folder). A REDengine name leading out of the folder, kept by its hash, is
  no longer counted as skipped.
- Fix: a feature's background install that failed showed as a succeeded job; each failure is a
  warning and the job fails, naming them.
- Fix: dump, trace, profile, agent, record and the attach tools wrote under a game folder (or a
  folder of the user's) opened as the workspace; they are refused there, and `viwo attach`
  refuses a workspace inside the game.
- Fix: a pid or seconds that is not a number (a workflow's `{pid}` input) answered a 500; it is
  named (`invalid_request`).
- Fix: the preview cookie carried the API token, and a browser sends a host's cookies to every
  port: it is now a token of its own, for `/preview/` only, named with the port, set only for a
  keyed LAN peer. Non-ASCII tokens, keys and cookies, a range number of thousands of digits and
  a preview file locked or gone answered no response and a traceback: refused, ignored or 404.
- Fix: two concurrent recording starts both won, and an action ending while a recording was
  stopped could lose its step; the recorder's state is changed under one lock.
- Open, recorded in CONFORMANCE (2.10, partial): `genie`, `warscape` and `source` still use
  title executables as detection evidence; the per-title data moves to game plugins.
- `contracts/paths.py` (walking without links) and `api/peers.py` (loopback, token comparison)
  split out to keep their modules under the caps.

## 1.20.1 (2026-11-05)
- Doc 19.4 (embedded child GUIs) designed: what faithful embedding must cover, two approaches
  (A: the child's own remote display through pinned tools, recommended, Linux first; B: ViWo's
  own capture and input), and the owner's decisions it waits for (approach, pins, Windows
  popups, the input route's exposure). Nothing is built yet.

## 1.20.0 (2026-11-05)
- Workflows (doc 19.3, the third UI capability of doc 16.4): record what you do in ViWo and
  replay it. While a recording runs (RUNBOOKS, RECORD A WORKFLOW; a REC chip in the status strip
  whatever view is open), every action route that succeeds adds a step: extract, survey,
  repack, patch, mod, capture, analysis, cleanup and the runtime kinds; PAUSE / CONTINUE, a
  note for what you did in a child tool, STOP AND SAVE writes it as your runbook. Each recorded
  action keeps what it answered (a digest without ids, times and stamps, the game and workspace
  as `{game}` and `{workspace}`, and the facts that name a change). A replay goes on by itself
  while every answer is the one recorded and stops where one differs, saying what changed (the
  UI's DIFFERS: YOUR CALL; the CLI asks at a terminal, else stops with `--from`).
- A secret plugin option (an AES or PCK key; every option of a plugin ViWo does not know) is
  never written into a recording: it becomes a secret input asked at each run (the CLI asks
  without echo), which the UI does not keep. An id an earlier step answered (a cleanup plan's
  `planId`) is recorded as `{step<N>_<key>}`, so a replayed apply sends its own replay's plan; a
  process id is never recorded. Capture and the runtime kinds carry no expectation. A recording
  needs the game; STOP waits for the actions still running; a step naming another game is said.
  A recorded extract that asked replays with `onExisting: new`. `GET|POST /api/recording`.

## 1.19.0 (2026-11-05)
- Runbooks (doc 19.2, the second UI capability of doc 16.4): named, editable, saved sequences
  of steps. An action step is a job kind with its parameters and runs through the handler
  `POST /api/jobs` uses (every action keeps its own checks and switches); a step you do pauses
  the run until DONE, CONTINUE (a workbook says how in the child tool). `{game}`, `{workspace}`
  and the runbook's inputs fill the parameters; an empty one is refused, named, before anything
  runs. A failed step stops the run where it is; RUN FROM HERE / `--from N` resumes. Three ship:
  "Extract a game and plan its cleanup", "Find a hardcoded value and patch it live", "Apply a
  patch set into a patched copy". EDIT shows a runbook as JSON; SAVE validates and writes your
  copy to `viwo-data/runbooks/` (a shipped id: your tweaked copy replaces it until deleted).
  RUNBOOKS in the global strip, `viwo runbook [ID] [--run --workspace W --set name=value --from
  N]` (without a terminal the run stops at a step you do and says `--from`), `GET
  /api/runbooks`, `POST /api/runbooks/step|save|delete`.
- Each action's answer (a plan, a report) is shown with its step (ANSWER in the UI; stderr and
  `done` on the CLI), so the step you do next can read it. The CLI says a `--set` name the
  runbook does not have, refuses a `--from` outside its steps, and names the workspace to resume
  in when an extract step switched it. A parameter that is one `{name}` alone with the value
  true or false becomes that boolean.
- `core/guides.py` holds what workbooks and runbooks share (the two folders, problems named, a
  file with a wrong type anywhere named and never a crash, save and delete of the user's file
  that holds the id through `safe_member` and `inside`); the CLI's guide commands moved to
  `cli_guides.py`. A runbook step can open its workbook directly.

## 1.18.0 (2026-11-05)
- Workbooks (doc 19.1, the first of the owner's UI capabilities of doc 16.4): step-by-step
  how-tos for a child tool's own interface, teaching text and never automation. Four ship,
  checked against the pinned versions: x64dbg "Patch a byte, live and into a file", Ghidra
  "Find the code that uses a string" and "Patch an instruction and export the program", Cheat
  Engine "Find a value, change it, find what writes it". The user's own go in
  `viwo-data/workbooks/` (one with a shipped id replaces it). A broken file is skipped and named;
  steps written for another version than the pin are marked stale. WORKBOOKS in the global strip
  (one step at a time, the step reached remembered, the view that opens the tool), HOW TO
  buttons in ANALYSIS and RUNTIME, `viwo workbook [ID]`, `GET /api/workbooks`.
- New contract doc 19 (Guides): workbooks, and the open runbooks, workflows and embedded child
  GUIs; 16.4 points to it.

## 1.17.0 (2026-11-05)
- Static and dynamic analysis separated (owner). Continue in x64dbg and Continue in Cheat Engine
  work on the game itself, so they left the static ANALYSIS view for the dynamic arm: RUNTIME,
  DEBUGGER AND MEMORY; `viwo attach GAME [--target KEY --tool ID --pid N --workspace W
  --confirm]`; `GET|POST /api/runtime/attach`. Their slots are renamed `handoff.debug` ->
  `attach.debug` and `handoff.memory` -> `attach.memory` (family `attach`); an ini naming the old
  ids needs the new ones. They need only the `capture` switch (with the once-per-game
  confirmation and the warnings), no longer `analysis` too. ANALYSIS and `viwo analyze --open`
  keep the static handoff (Continue in Ghidra); `analyze --confirm` is gone.
- x64dbg debugs the game's own process (owner: live patching needs it): it attaches to the one
  process running the target's executable (or the pid given) with `-p PID`, and starts the game's
  own executable when none runs. The `<workspace>.debug-copy` patched copy is no longer made.
  Several processes of that name answer `needs_decision` (give the pid).
- The Cheat Engine table moved from `.analysis/cheatengine-gui/` to `.runtime/cheatengine-gui/`.
- `core/handoff.py` holds what both arms share: the tracked launch, `wait_for`, the slot offer.
- The default `startup.ini` keeps `extraction, sorting, merger` (a local edit turning on
  `capture, analysis` was reverted, owner's call).
- Tests: the browser smoke waits for the browser's DevTools port before driving it (a cold Edge
  under the full suite's load refused the connection and all eight smoke tests failed).

## 1.16.8 (2026-11-05)
- Handoff: the state header (version) and the test count brought current.

## 1.16.7 (2026-11-05)
- Fix: a legacy API handler's refusal (a `ViwoError`) reaches the UI with its own message, code
  and status instead of a generic 500 "internal error". The dynamic "continue in Cheat Engine /
  x64dbg" handoffs refuse with "runtime capture is off" when `capture` is off in the feature
  switches, and the server's catch-all was swallowing that into "internal error".

## 1.16.6 (2026-11-05)
- Fix: the analysis arm copied a binary under its original name, and Ghidra's headless refuses a
  name with an apostrophe, a space and more ("Void's Cave.exe": "Please rename", found by the
  deep pass). The copy now gets a tool-safe name (the extension kept for format detection).
- Roadmap (doc 16): T3 records that interactive/live patching is the child's native job (x64dbg,
  Ghidra) and ViWo does not reimplement it; 16.4 records the planned, OS-agnostic UI features
  (workbooks, runbooks, workflows, embedded child GUIs with proper input forwarding); and a
  managed-vs-unmanaged tools distinction for the indexes and plugins. Verified by hand: ViWo's
  Ghidra analysis located Free Download Manager's hardcoded 20-connection per-server cap (one
  `cmp` byte), raised in a patched copy; connections rose from 20 to 47.

## 1.16.5 (2026-11-05)
- Unity IL2CPP builds: MonoBehaviour data comes out with its fields. The export runs Cpp2IL
  (pinned, its own process) once to rebuild stand-in assemblies from GameAssembly and the
  metadata, and gives them to UnityPy's layout generator; on Schedule I's resources.assets 270
  of 745 MonoBehaviours carry their fields (6 before). A missing Cpp2IL or an empty run is said.

## 1.16.4 (2026-11-05)
- `pack.wad`: Doom WADs are written back (found missing by the deep pass on Freedoom): edited
  pictures and flats go back through the game's palette (grAb offsets kept), sounds to DMX, every
  other lump as it was; verified on Freedoom (a repainted sprite comes back).
- `decode.vtf`: Source textures to PNG in process (the largest mipmap of the first frame; DXT1,
  DXT3, DXT5 and the 8-bit formats; VTF 7.0-7.5).

## 1.16.3 (2026-11-05)
The patching arm for the engines ViWo reads itself (from the deep pass: Doom had no packer,
nor had most of these): `pack.asar` (rebuilt, integrity hashes recomputed), `pack.vpk` (an
override VPK in `custom/`), `pack.xp3` (the next KiriKiri patch archive), `pack.bsa`/`pack.ba2`
(loose files in `Data/`), `pack.pack` (a Warscape movie pack; PFH5+ refused by name),
`pack.rgssad` (XP/VX/VX Ace rebuilt under their keys), `pack.drs` (rebuilt). Each override is
written where its engine loads changes over its own archives and read back.
- Fix: a DRS table with a four-letter type (`anib`, AoE's `bina`) lost a letter.
- Fix: headless Ghidra ran with its 2 GB default heap and died on a large executable
  (`OutOfMemoryError`, found by the deep pass on a Godot game); it now gets half the machine's
  memory (2 to 16 GB) unless the user set `GHIDRA_MAXMEM`. The OS layer says the machine's
  memory (`memory_bytes`).
- Deep pass: ViWo's own warnings are read from the envelope; emulate/symbolic, which need a
  routine address, are skipped and said.
- Fix: `viwo agent` lent Unity's agent (BepInEx) to any game whose engine has none (a Godot game
  got "a Mono build"); only a plugin that detected the game gives its agent, a game plugin's
  first, and the error names the engines found.

## 1.16.2 (2026-11-05)
- The presentation tooling (`tools/presentation/`): frames of every view driven through
  headless Edge on a real game; the technical PDF (architecture, the three arms and failover in
  mermaid charts, every view with its screenshot, reference tables generated from the code:
  plugins, slots, pinned tools, CLI, HTTP routes, conformance); the demo video (MP4, captions
  in a band under the frame, no voice) through the pinned ffmpeg. mermaid 12.3.0 is pinned
  (on demand). Deep pass: a companion read with its container (`.resS`, `.ucas`) counts as read.

## 1.16.1 (2026-11-05)
- `tools/deep_pass.py`: every capability on one real game, judged on its output (the accounting
  of every game byte and workspace file, decoded files opened by real readers, a contact sheet,
  cleanup undo, every analysis target, a real edit repacked and read back, an AOB patch set, a
  mod, and the dynamic arm with `--dynamic`). Verified on Freedoom: every byte read, 80 % of the
  workspace in open formats, every sampled PNG, WAV and text opens. Found there: Doom WADs have
  no packer yet (the patching arm does not reach them). `tools/status_pdf.py` is retired (the
  technical PDF replaces it).

## 1.16.0 (2026-11-05)
Game plugins (doc 2.10, owner's decision: plugins per engine, each engine with game plugins):
- An engine plugin keeps what holds for every game on its engine and detects by the engine's own
  file signatures; what one title adds lives in a game plugin under the engine
  (`viwo/plugins/<engine>/games/<game>/`), discovered with it, run only with it (a chosen game
  plugin brings its engine; a chosen engine brings the game plugins that detect their game),
  supplying the engine's backends through `ExtractionContext.games`.
- REDengine 4 is now engine-only (RDAR archives, CR2W through WolvenKit, the override pack, mod
  conflicts) and detects by its RDAR archives; the Cyberpunk 2077 game plugin holds the path list
  (`cp77-hashes`, read by the engine's reader through `name_lists`), redscript decompilation and
  its `decompile` option (now `[options.cyberpunk2077]`), and the title's executables.
- TaleWorlds detects by its TPAC packages; the Bannerlord game plugin names the title.
- SETTINGS shows a game plugin as "game plugin of <engine>". Contract 1.2 (optional fields).

## 1.15.6 (2026-11-04)
A backend quality review and a UX/UI review (independent, every finding verified):
- Member names Windows cannot write (`< > " | ? * :`, control characters, device names, a
  trailing dot or space) are no longer lost: every in-process unpacker (zip, tar, RPA, VPK, XP3,
  BSA, BA2, RGSSAD, ASAR, TPAC, PFH, RDAR) writes them under an altered name and records the
  original beside the files; provenance gives the original, so a repack writes the member back
  under it. One such name used to fail a whole archive.
- Fix: junctions were still followed by the UNPACK walk, the patched copy and plugin scans
  (Unreal keys and assets, RPG Maker MV, Total War DB, Godot, Doom, Bink, Unity): one walker
  (`contracts.workspace.files`) never enters a linked folder; the copy names the ones it skips.
- Fix: repack took its lock inside the game folder before refusing it; a mod zip could be
  written into the game folder. Both are refused first.
- Fix: a LAN peer could stream workspace files through `/preview/` without the token; it now
  needs the token's cookie. Attended capture (0 seconds) became a 30 s auto capture.
- Fix: a key cut across the 200-character output limit could show its first half; masking runs
  first. Godot's errors are masked; GDRE recovery gets the key and the game's main pack.
- Fix: QuickBMS scripts claimed formats a built-in reader knows; they are now a fallback.
- Fix: cancel was not honoured during UNPACK and EXPORT and a killed main started the spare.
- Fix: a file repeated across archives was decoded once per copy; decode and capture dropped the
  files the OS refused in their second collect; the probe's entry bound and the 500-script cap
  of Ren'Py and Godot analysis cut silently (bound raised and said; caps removed).
- Fix: the x64dbg and Cheat Engine handoffs edited the user's own installs; they pre-answer
  prompts only in ViWo's copy now. The job table is guarded by a lock.
- UX: EXTRACT's "replace" dialog defaults to NEW FOLDER and says REPLACE deletes edits too;
  the extension filter applies to what ends up in the workspace (IMAGES keeps the textures a
  decoder makes) and says what it left out; RESULT is brought into view after a run.
- UX: SURVEY no longer splits one game whose files sit in folders (Cyberpunk) into several;
  SORT keeps its progress across TRASH and remembers KEEP per workspace; SETTINGS keeps pending
  changes when you come back; EXTRACT, ANALYSIS and SURVEY follow the top bar's game.
- UX: tab codes in JOBS and MERGER come from the live numbering; the arm homes start with
  PICK A GAME FOLDER when none is set, drop roadmap codes and say when a step opens in another
  arm; PATCHES asks for the copy folder before APPLY and labels the mod fields per action;
  turning on ANALYSIS or CAPTURE installs what they need in the background (JOBS), and a CLI
  install hint points to SYSTEM.

## 1.15.5 (2026-11-04)
Third audit (hostile input, completeness, the walk; an independent review, every finding verified):
- Fix: unpackers skipped entries silently. VPK, XP3, BSA, BA2, RGSSAD, ASAR, TPAC and RPA now
  count every skip by reason (unsafe name, missing part file, cut short) and say it; the unpack
  stage logs every note as a warning and lists it among the run's warnings.
- Fix: a declared size of 0 let zlib and LZ4 inflate without a limit (XP3, BSA): bounded to 1.
- Fix: RPA member names went through a resolve check only; now `safe_member` + `inside` (NTFS
  streams, device names, links). A member shorter than its index says is written and said.
- Fix: a crafted SLP row or Doom column could replay one long command stream for every row:
  both are bounded by their width or height.
- Fix: RPG Maker MV took System.json's key unchecked; a key that does not open the images is
  replaced by the one the PNG signature gives (said), the packer checks the game's images, and
  a file without the RPGMV header is kept as it is (said) instead of dropped.
- Fix: a junction in a game folder was walked into (survey, probe, collect, the game snapshot,
  the capture policy): link-like folders are never entered.
- Fix: what the game writes into its own folder during a capture is said as a warning.
- Fix: an engine found inside a wrapper (an MV game in an Electron asar) mapped its exports to
  paths of the unpacked wrapper; they are now derived, never written back to a wrong container.
- Fix: unluac gave `main.lua` and `main.luac` one output name; both are kept.

## 1.15.4 (2026-11-04)
Second audit (writes, the API, installs; an independent review, every finding verified):
- Fix: a game folder (or any folder of the user's) opened as the workspace could be curated:
  KEEP ONLY SELECTED moved the game's folders to a `.trash` inside it and CLEAR TRASH deleted
  them; cleanup could rename game files. Every write into a folder that is neither a ViWo
  workspace nor a patched copy is now refused, and read-only calls there take no lock.
- Fix: "replace" could delete the game being extracted when the game sat inside the workspace,
  and could clear a default workspace folder holding the user's files. Both are refused.
- Fix: a merger build wrote a lock into the folder it read (a game folder, or a read-only one
  that answered 500); a mistyped working folder silently became the workspace; two candidates
  whose names reduce alike overwrote one video. Outputs now take a free name, a wrong folder is
  said, and a read-only error is named.
- Fix: repack and the analysis diff took relative paths (doc 4.1 rule 6); now absolute only.
- Fix: Python pins installed with `--upgrade`, and a pin bumped after a ViWo install is
  installed again (a marker records what ViWo installed; packages found elsewhere are left).
- Fix: a patch whose file the copy step could not copy failed the whole job; it now fails alone.
- Fix: on a LAN bind every peer could read the API token from the page; it goes to this
  machine, or to a LAN peer with the `?key=` link `viwo serve` prints (doc 4.1 rule 1).

## 1.15.3 (2026-11-04)
Audit of the 1.7-1.15 work (an independent review, every finding verified and fixed):
- Unity: the MonoBehaviour layout generator reached only the first group of files; later
  bundles were counted as "layout not in the build". It is now made once and given to every
  environment. A string UnityPy kept as escaped bytes broke the whole `.objects.json` (the
  separator was written before the entry failed); entries are serialised first and such
  strings written with JSON escapes. Dump files are closed after each group and reopened to
  append (thousands of bundles no longer exhaust the descriptors), and closed on any error.
- Unreal: the AES key on UnrealAssetScout's command line is masked in whatever the tool says
  (it could have reached the run record); retoc's per-container staging folder is removed once
  the tool ran (a copy across volumes kept every `.ucas` until the run ended).
- Cyberpunk: an edited REDmod archive (`mods/<name>/archives/`) gets its override in
  `archive/pc/mod`, where the game loads it; an archive under neither layout is refused with
  the reason instead of an override the game never reads, or one written outside the copy.
  WolvenKit's settings are only written into ViWo's own copy, never a user's install.
- Total War: a DB header whose row count cannot fit in the table is refused (a crafted pack
  could build billions of empty rows).
- Decode: the empty-file filter is linear. UI: hints name panels by title (BEFORE YOU START,
  TARGET FOLDER...), no longer by the fixed codes the live numbering replaced.

## 1.15.2 (2026-11-04)
- Tests: the mixed-mode pairwise test runs every plugin alone and 13 groups of six that cover
  every pair of the 17 plugins (a covering design, checked by its own test), instead of all 136
  pairs one by one: 257 s to 50 s with the same pairwise property.
- HANDOFF: the completeness findings kept for the open rows (Unity IL2CPP fields, Unreal glTF,
  REDengine TweakDB), the games this machine can verify, and the UX/UI review done at 1.12.0.

## 1.15.1 (2026-11-04)
- Fix: vgmstream (`decode.audio`) wrote nothing: its `?f` output wildcard is the whole input
  path, so `<dest>/?f_?s.wav` named a file inside a folder that does not exist, and the audio
  fell to ffmpeg (which cannot read Wwise, FMOD or Bink Audio) or failed. The output name is now
  the file's own stem (`<name>_<n>.wav`). FMOD Studio banks (`.bank`) join the audio decoded:
  verified on a Bannerlord bank, 344 streams to WAV in 4 s.
- Fix: a request the server refused before reading its body (403, 413, 415) could reach the
  client as a connection reset instead of the answer (Windows resets over unread data, about one
  run in eight): the server now answers with `Connection: close` and takes in what was sent.
- The decode stage skips empty files with one line (CLEANUP lists them; Rome II ships three
  empty `.dds`), and a decoder's failure is said by the tool's telling line ("Invalid data
  found...") instead of the end of a path it echoed. The Bink 2 decoder moved to
  `core/decode_bink.py`.

## 1.15.0 (2026-11-04)
- Completeness contract (doc 16.0c) on Total War, valid for every Warscape game: `.loc`
  localisation tables decode to JSON in ViWo's own code (`decode.loc`), and DB tables to JSON
  (`export.warscape`, one file per table under `db/`) read by ViWo with the game's RPFM schema
  (pinned per game, 14 games, MIT, installed when asked: `viwo install rpfm-schema-<game>`). A
  table whose version the schema lacks is tried against its other definitions (reading to the
  last byte is the check); tables the schema lacks or misreads are counted and named. Detection
  now knows every one of those games' executables. Verified on Rome II: 191 `.loc` tables
  (122,423 entries) and 611 DB tables with JSON out of the real packs.

## 1.14.0 (2026-11-04)
- Completeness contract (doc 16.0c) on Unreal, valid for every UE4/UE5 game: the new
  `export.unreal` slot runs UnrealAssetScout (pinned `uas` 0.5.0, MIT, CUE4Parse inside,
  self-contained Windows build): textures to PNG, models and animations (UEFormat), sounds and
  every package as JSON. The engine version is read from the game's own binaries (the
  `++UE5+Release-5.x` build string; option `engine` overrides); cooked UE5 assets need the
  game's mappings, taken from the `.usmap` the RUNTIME agent (UE4SS) wrote into the workspace
  (option `usmap`); without them the packages that need them are counted and the way to get
  them is named. Verified on a UE5.1 game: the agent's mappings, then 695 PNG, 122 models,
  3 animations, 23 sounds, 513 packages as JSON. Open: models to glTF; a Linux exporter.
- Bink Audio (`.binka`, Unreal) decodes to WAV through vgmstream. Fix: vgmstream's
  all-subsongs pass writes nothing for a file without subsongs and exits 0; such a file is now
  decoded as one stream (before, it fell to ffmpeg, which fails on Bink Audio).
- Fix: retoc converted one IoStore container at a time without `global.utoc`, so every package
  failed and the raw Zen packages came out instead (815 of 815 on the test game); a container
  now converts in a folder beside `global.utoc` (hard links, a copy across volumes): 815/815.
- Fix: an empty (or `auto`) tool path in `[tools]` pointed at the ini's own folder; it means
  automatic, as SETTINGS says. With it, the UE4SS agent copied a whole folder into itself.
  The agent now refuses a UE4SS folder that holds the copy.
- Fix: a workspace the dynamic arm had written to (`.runtime/` only) was refused as "not
  created by ViWo", then treated as "already holds an extraction". The dynamic arm claims a new
  or ViWo-only folder (never one with the user's files), and the other arms' dot-folders are no
  extraction to replace. Exporters get the run's workspace (`ExtractionContext.workspace`).

## 1.13.0 (2026-11-04)
- Completeness contract (doc 16.0c) on Unity, valid for every Unity game: besides textures,
  audio, text and meshes, the export now writes video clips in their own format, fonts
  (.ttf/.otf/.ttc) and shaders, and every other object (scenes, prefabs, materials, animations,
  game objects and their components, MonoBehaviour data) as JSON from its type tree, one file per
  serialized file (`data/<file>.objects.json`, streamed). MonoBehaviour layouts come from the
  game's managed assemblies (pinned `TypeTreeGeneratorAPI` 0.0.10, MIT, with UnityPy); one that
  has no layout is listed with the reason and counted. Unity option `objects` (default on).
  Verified on ULTRAKILL Prelude: 307,864 objects to JSON in 28 files, 89 shaders, 2 fonts and a
  video in 90 s. Open: MonoBehaviour fields on IL2CPP builds.

## 1.12.0 (2026-11-04)
- UI numbering is computed, never written (owner): `S0`… STATIC, `D0`… DYNAMIC, `P0`…
  PATCHING (each arm's home is 0), `00`, `01`, `02` for SYSTEM, JOBS, SETTINGS, from the arm and
  the place in it, so plugin views renumber everything by themselves. Panels are lettered A, B,
  C… in reading order over the visible ones. Home steps and NEXT buttons show the code of the
  tab they open; every message names a tab by its title only.
- UX pass from frames captured at the owner's window and zoom, and on a real extraction (DDLC):
  - the top bar no longer drops chips: OS and PLUGINS moved to SYSTEM, the game and workspace
    paths shorten first; FORMATS opens SYSTEM at its formats list (`#system@formats`, kept in
    place while the tables load);
  - toasts sit at the top right, no longer over the action bar's button;
  - ANALYSIS and CAPTURE named "–" as the active workspace although one was open;
  - an off feature (ANALYSIS, RUNTIME CAPTURE) says so with a TURN ON button that writes it to
    startup.ini at once; a notice's text no longer runs into its title;
  - a two-column view with nothing on the right yet uses the whole width; field labels have
    room above them; SETTINGS tool paths have BROWSE beside the field;
  - WORKSPACE: OPEN per file type, "(no extension)" for `noext`; SORT opens on what can be
    previewed (images, audio, video, text first); JOBS opens the latest job; PATCHED COPY
    proposes a target beside the workspace (`<data>/patched/<game>`);
  - SYSTEM says what every tool serves from the server's own data (the slots it backs, else
    its arm), not from a hand-kept list.

## 1.11.1 (2026-11-04)
- Fix: a plugin's decoders ran on every game. `decode.cr2w` claims `.json`, `.mesh`, `.ent` and
  the other CR2W suffixes, so with WolvenKit installed an RPG Maker MV game's data JSON or a
  Unity game's meshes were handed to WolvenKit and reported as failures. A plugin's decode
  slots now apply only when that plugin was chosen for the game (core decoders, such as audio
  and images, still run everywhere).

## 1.11.0 (2026-11-04)
- Completeness contract (doc 16.0c): every Cyberpunk 2077 extraction reports the installed mods'
  conflicts from the archive indexes alone: how many members of the game's archives the mods
  replace, how many members a later mod loses to an earlier one (first by name in
  `archive/pc/mod`, then REDmod's `mods/*/archives`; named from the path list when it loads),
  and any archive that cannot be read. Verified on a real install: 15 mod archives replace 63
  members, in 1.5 s.

## 1.10.0 (2026-11-04)
- Completeness contract (doc 16.0c), patching arm on Cyberpunk 2077: `repack` packs edited
  members into an override archive, `archive/pc/mod/!viwo_<archive>.archive` in the patched copy,
  through WolvenKit's console (new `pack.archive` slot, `wolvenkit-pack`). The game loads it over
  its own archives; the name sorts before other mods, so ViWo's edits come first. A member known
  only by its hash keeps that hash. The packer reads the archive back through the game's Oodle and
  compares every edited member. Verified: a texture of a real mod archive edited, packed by
  WolvenKit 9.1.0 and read back byte for byte.
- Fix: an Unreal repack of a pak with members left as they were reported those members as
  FAILED: the `_P.pak` override holds the edits only and the verify looked for every member in
  it. A packer now says it writes an override (`Packer.override`); its file is verified on the
  edits, and the untouched members stay in the pak it loads over (reproduced with the real repak
  on a two-member pak).

## 1.9.0 (2026-11-04)
- Completeness contract (doc 16.0c): Cyberpunk 2077's game scripts are decompiled. The new
  `decode.redscripts` slot (`redscript-decompile`) runs redscript's console (pinned `redscript`
  0.5.32, MIT, Windows; the 1.0 previews dropped the decompiler) on `r6/cache/final.redscripts`
  and writes one `.script` file per stored script (`[options.redengine] decompile = off` keeps
  the cache as shipped only). Verified on the game's own file: 1786 scripts in about a second.
- The `decode.cr2w` warning quotes WolvenKit's failure line from "Failed to" on.

## 1.8.0 (2026-11-04)
- Completeness contract (doc 16.0c): Cyberpunk 2077 resources are decoded. The new
  `decode.cr2w` slot (`wolvenkit-export`) runs WolvenKit's console (pinned `wolvenkit` 9.1.0,
  GPL-3.0, its own process on the pinned .NET runtime) once per batch of 150 extracted files:
  textures to PNG, meshes, morph targets, cubemaps and animations to glTF, and every CR2W
  resource to JSON (embedded buffers included). The settings ViWo needs (PNG, meshes without
  materials, which need an uncooked depot) are written into WolvenKit's own `appsettings.json`
  off screen. Every file WolvenKit could not convert is counted in one warning that names the
  first. Verified on four real mod archives: 345 resources, 51 PNG, 52 glTF, 336 JSON; 15
  animations WolvenKit itself cannot read are reported.
- Decode stage: a backend that takes a whole batch (`decode_many`) gets every file of its slot in
  one call; a partial batch is a warning in the run.

## 1.7.1 (2026-11-04)
- Fix: a Cyberpunk 2077 member comes out as the game's own file: the main segment inflated, then
  its buffer segments exactly as stored (the CR2W buffer table gives their on-disk sizes and the
  reader inflates them). The buffers were split off inflated into `<name>.<n>.buffer`, which no
  tool can read (WolvenKit failed on every texture with a buffer; verified: 8/8 textures of
  `basegame_1_engine.archive` now export to PNG). Buffer segments need no Oodle.

## 1.7.0 (2026-11-04)
- Completeness contract (doc 16.0c), first gap closed: Bink 2 video (`.bk2`, Cyberpunk 2077 and
  many other games) decodes to MP4 in the new `decode.bink2` slot (`bink-game`). ffmpeg has no
  Bink 2 decoder; the game ships one: a helper process (`viwo/data/bink/decode_bink.py`) decodes
  every frame with the game's own `bink2w64.dll` and pipes it into the pinned ffmpeg, so the
  game's code never runs inside ViWo. Opt-in with the other video (`core.decode_video=on`).
  Verified on Cyberpunk 2077's video archive (500x500, 299 frames at 30 fps). Video only: the
  audio track is not decoded yet (said in every note).
- `viwo` LoC budget 14200 -> 14600 for the completeness work (reason in `loc_caps.ini`).

## 1.6.24 (2026-11-04)
- Property tests: a settings change that would break the ini is refused and the ini stays as it
  was (no draft left); a file that is not a patch set is named, and an export without a unique
  signature says so per patch; TaleWorlds LZ4 segments inflate, or are skipped without the module
  or on bad data; DataTool names a missing tool and failed modes; the protector check names output
  it cannot read; a damaged export map is ignored; a capture names anti-cheat services running
  now; an unreachable network is reported as such.
- Coverage: 98.6 % line, 95.3 % branch overall (doc 17.5); 72 files still under 98/95 alone.

## 1.6.23 (2026-11-04)
- Property tests: mod load order over random dependency graphs puts every mod after what it
  requires or loads after, names a cycle with its path and a missing requirement, and every
  conflict it reports is real and undeclared; the plugin conformance check names a capability
  list without detect or unpack and a dependency declared twice; a raising detect scores zero
  with its reason; an extraction that needs a decision says so; GitHub's answers, missing
  releases and errors; a workspace that is a file, a taken sibling name and the process's own
  lock.

## 1.6.22 (2026-11-04)
- Property tests: duplicate cleaning never trashes the last copy of any content (random
  workspaces full of duplicates keep every content after plan and apply); damaged SLP sprites
  and palettes are named failures of the in-process decoder; plugin sanitizer rules count only
  under their own plugin id; QuickBMS names a missing scripts folder, tool or script and a run
  that wrote nothing; survey reports are found by id inside their folder only, damaged ones
  skipped; a backend that raises is a named failure and its spare runs; the carve stage says its
  failures, fallbacks and big files, and stops on cancel.

## 1.6.21 (2026-11-04)
- Property tests: a sanitizer plan acts only on the files it saw (a file changed since the scan
  refuses the plan, a bad id or a missing plan is named, a finding that cannot be carried out is
  listed while the rest go on, an undo that cannot bring a file back keeps it for a later
  undo); analysis names an unbound slot, a failed run, a fallback and a plugin whose target
  hook crashes, and stops waiting on a GUI tool on cancel; Skyrim SE BSAs (LZ4 frames, embedded
  names) read back byte for byte and are counted without lz4; the carver splits a stream of
  several files; `viwo analyze` names a missing game or workspace and waits for the tool it
  opened.

## 1.6.20 (2026-11-04)
- Property tests: the round trip plans every edit or names why not (no packer, an unbound pack
  slot, a plugin that is not loaded), takes the newest extraction run as the game (never a
  capture record or a damaged one), reports a container behind a link, a failed packer and a
  crashing verify per container, refuses traversal in loose files, reminds about terms-sensitive
  plugins and needs a target to build; small core edges: an unknown or foreign OS layer, a patch
  address outside every section, asm without Keystone or that it cannot assemble, a file with no
  unique signature, stale antivirus journals, a crashing job, the capture routes' bad input.

## 1.6.19 (2026-11-04)
- Property tests: any sequence of one-by-one keep, trash and rename, undone step by step, gives
  back the exact workspace (a refused rename records nothing; an undo with nothing left or of a
  vanished file is named; a restore never overwrites a newer file); every malformed drop-in
  plugin.json (no id, a bad or reserved slug, a missing module, a ui path outside, a too-new
  requirement, a class that is not a plugin or carries another id) disables only that plugin,
  with its reason, and the built-ins boot as before; slot and backend clashes are named.

## 1.6.18 (2026-11-04)
- Fix: "Continue in x64dbg" on a 32-bit game names a missing x32dbg (an x64dbg of the user's own
  may ship without it) instead of failing on its config file.
- Property tests: the carver finds samples of every format at their exact offset and size in
  noise, and damaged ones never crash it, overlap or run past the buffer; every analyzer and
  handoff names a missing tool and a run that wrote nothing; the first-run answers of x64dbg,
  Ghidra and Cheat Engine land once, keep every value the user set, change nothing the second
  time and say when they cannot be written.

## 1.6.17 (2026-11-04)
- Property tests: any RPA-2.0/3.0 archive (any key, prefixed chunks, byte or text names) reads
  back byte for byte and a repack keeps every member and carries every edit, a malformed index
  is named; a [slots] entry never binds a backend that cannot serve the slot and every bad entry
  is named; the 7-Zip, unrar and py7zr backends name a password, a failure and a missing tool;
  unsafe zip names are counted in a note; RPG Maker MV media decrypts with the game's key or
  one recovered from its images and repacks to what the game reads; the settings routes name an
  unreadable ini and a broken plugin; the unrpa and unrpyc processes name a run that wrote
  nothing.

## 1.6.16 (2026-11-04)
- Property tests for the Unity exporters' sources: containers found by name or by signature
  behind a custom header (a file an antivirus holds is skipped), the game's cache folders only
  from app.info and only when they exist, the source map follows an object through a bundle to
  its file on disk, the extension filter writes only what was selected, the cache is read only
  when asked for, a cancel stops; the AssetStudioModCLI spare names a missing tool and a failed
  run and asks for meshes only when they are on.

## 1.6.15 (2026-11-04)
- Fix: the XP3 reader (KiriKiri) bounds its index: a stored index past 256 MiB (a damaged
  64-bit size raised OverflowError) and a compressed one that inflates past it (a
  decompression bomb) are named "bad XP3" failures. XP3 joins the mutation fuzzer.
- Property tests: XP3 archives in every layout (version 1 and 2 headers, stored or compressed
  index and segments, files over several segments, foreign chunks) give back every plain file
  byte for byte; encrypted entries are counted and named, never guessed; traversal names are
  never written; a cancel stops.

## 1.6.14 (2026-11-04)
- Fix: `viwo survey` classifies encrypted or compressed blobs under 128 KiB as dense. Their
  "middle" sample started at offset 0, the same bytes twice compressed well, and they were
  reported as structured data ("try --deep") instead of needing a key or a decoder.
- Property tests: a survey of random games counts every file in exactly one category, reports
  the coverage its categories give, names every missing tool and exporter, counts a file an
  antivirus holds as unreadable, and stops on cancel; a decoder that reports success without
  output is a named failure; the probes report exactly the facts of the file.

## 1.6.13 (2026-11-04)
- Property tests: GDScript decompilation (the bytecode option wins, then the engine version, then
  GDRE's own listing for the header number; files in batches of at most 100; every failure
  named); the Unity packer writes TextAsset and Texture2D edits back, verifies them, and names a
  missing object or a type it cannot write; an OS layer without a capability says it cannot;
  the zip packer changes exactly the edited members and leaves a broken container untouched;
  one plugin's verify crash stays on its own entry; provenance keeps damaged lines.

## 1.6.12 (2026-11-04)
- Fix: every dump, trace and profile run gets a new folder and every recording a new WAV. Two
  runs on one process within one second shared `<pid>-<stamp>`, and a trace that wrote nothing
  reported the earlier run's log as its own; two recordings in one second overwrote each other.
- Fix: an Unreal patch pak counts the members it packed (an unsafe member name was skipped but
  counted).
- Property tests: the round-trip edit set over random provenance maps and user actions (every
  edit in the set or named with its reason); pak footers fuzzed; unpack failures classified
  (key or not) and the AES key never shown back; patch paks take the game's pak version; AES
  key spellings round-trip and every reason a key is missing is said; trace, dump, profile and
  agent waits over a faked OS layer.

## 1.6.11 (2026-11-04)
- Fix: `POST /api/open-folder` and the merger's `workingDir` take absolute paths only (a
  relative merger folder that existed beside the server was used as the merger's source).
- Property tests for the workspace routes over random workspaces: group trash, restore, delete
  and keep-selected never lose or invent a file and give the bytes back on restore; the asset
  window pages through every file once; save-remaining moves every remaining asset out byte
  for byte; the patch and mod routes do what the core does; the preflight and install jobs
  rebind what they installed.

## 1.6.10 (2026-11-04)
- Fix: a worker pin (Unicorn, angr) swaps in through `core/downloads.py` like every tool: a
  locked worker folder (Windows: a worker still running) is never half deleted.
- Fix: `POST /api/diag` takes an absolute `out` only (a relative one wrote into the server's
  folder), like every request path since 1.6.6.
- Contracts: `RuntimeAgent.install/finished/outputs`, `Analyzer.analyze` and `Handoff.prepare`
  are abstract (a backend missing one fails when it is built, not mid-run); the base classes
  of the CLI unpackers, decoders and Unreal unpackers lost their never-run `argv` stubs.
- Property tests: the loopback recorder writes exactly the clipped samples it heard; a worker
  pin swaps in whole or leaves the old one; the BepInEx agent (IL2CPP only, never a stale log,
  what it wrote); `python -m viwo`; the system routes; both A4 workers name every unusable
  request (unsupported PE or ELF machine, not a binary, a symbolic argument to the emulator, a
  heap overflow, a bad dump index, an unknown export, nothing to solve) and take every
  argument kind and address form.

## 1.6.9 (2026-11-04)
- Fix: damaged archives are named failures in every in-process reader. The Ren'Py reader
  raised on a cut-short header or a malformed index entry and inflated its index without a
  bound (a decompression bomb: now at most 256 MiB); the zip and tar readers raised on a damaged
  member name, a cut-short gzip stream or bad deflate data; TPAC raised when cut short.
- Hostile input: valid archives of ten formats, randomly damaged (bytes, runs, cuts), through
  their readers, as a property (`tests/test_untrusted_input.py`).
- `viwo` LoC budget 14100 -> 14200 for the 1.6.x hardening (reason in `loc_caps.ini`).

## 1.6.8 (2026-11-04)
- Fix: a damaged 64-bit offset in an RDAR index (Cyberpunk 2077) or a BA2/BSA (Bethesda) is a
  named "bad RDAR/BA2/BSA" failure; it reached `seek()` or an mmap slice and surfaced as a
  Python OverflowError.
- Hostile input as one property (doc 17.3): every built-in in-process reader, handed its own
  magic followed by random bytes, answers with an Outcome and never raises, and writes nothing
  outside its destination (`tests/test_untrusted_input.py`); corrupt RDAR archives fuzzed.
- REDengine tests: Kraken members inflate through the game's decompressor (faked) and are
  skipped and named without it; the Oodle bridge; every reason members keep their hashes is
  said (no path list, no Oodle, a list that is not KARK or does not inflate); a cancel stops
  before the first member.

## 1.6.7 (2026-11-04)
- Property tests: merger builds over random candidate sets with the encoder faked (one output
  per candidate, every failure named, partial flagged, settings clamped, long graphs to a file,
  overlay and refusals); the Windows OS layer (produced file names always legal, the long-path
  form exactly past the limit, PowerShell lists quote any path, Defender exclusions leave the
  user's own alone and say why when skipped, a failed dump leaves no file); the shared OS base
  (output lines in order whatever the relay does, timeout and cancel kill and say so, GUI
  children tracked and reaped, the locator's search order, pickers without a display).

## 1.6.6 (2026-11-04)
- Fix: no API request can name the server's own folder. An empty or relative game, folder,
  executable, patch set, mod, copy or workspace path resolved against the server's working
  directory (an empty `gamePath` detected, surveyed or analysed ViWo's folder; `/api/mod` without
  `copy` defaulted to "."); every route now takes absolute paths only (`api/app.py` `path_param`,
  `existing`; doc 4.1 security rule 6), checked as one property over every path-taking route.
- Property tests: the startup preflight over random dependency reports (exactly the missing
  self-installing tools, never on-demand ones, nothing with auto_install off, every failure a
  warning, an honest ready count); the 12 ANALYSIS API answers what the core answers.
- Doc 4.1 lists `/api/patch`, `/api/mod` and `/api/runtime/profile`.

## 1.6.5 (2026-11-04)
- Fix: the RenderDoc helpers (`rd_trigger.py`, `rd_harvest.py`) moved to `viwo/data/renderdoc/`:
  next to ViWo's own `core/capture/renderdoc.py`, `import renderdoc` found ViWo's module in any
  Python where RenderDoc's module is not built in (the documented `[tools] rdpython` path).
- Fix: a GDRE recovery that stops with an error after writing files is said as a note (it was
  an unexplained OK).
- Property tests: the RenderDoc helpers run as real processes against a fake `renderdoc` module
  (one PNG per texture, one disassembly per shader object of draws and dispatches, the newest
  target, every exit code); the RenderDoc backend's endings; Godot recover and pack over random
  folders and edit sets, PCK trailers and PE headers fuzzed; the Linux OS layer on any host
  against a fake `/proc` (memory dump layout, process list, module spans, perf).

## 1.6.4 (2026-11-04)
- The completeness contract (owner): ViWo gets everything out of every game, decoded, with the
  three arms on every engine (doc 16.0c, with the per-engine table of what is decoded today and
  what is open; CONFORMANCE row 16.0c, HANDOFF item 7).
- Never silent in text mode, as a property over real runs: unpack, survey, sanitize (plan,
  apply, undo), repack (plan, build), slots --check, config check/generate, install, replay,
  diag and indexes update say in text what the --json envelope carries, with the same exit code.
- An extraction replays into the same files whatever the mode and extension filter; a replay
  without its secret is refused and names the option to pass.
- The server: every UI file is served byte for byte, index.html carries the token and is never
  cached, nothing outside viwo/web is served; malformed bodies and a crashing route answer and
  the server keeps serving; `viwo serve` ends with its own code for strict preflight (4), a port
  in use (2) and Ctrl+C (0).

## 1.6.3 (2026-11-04)
- Coverage work (owner's target 98 % line / 95 % branch per file): child processes are measured
  (`[tool.coverage.run] patch = ["subprocess"]`, CI combines); property tests for `viwo slots
  --check`, `unpack --slot/--backend`, `patch`, `mod`, `trace`, `capture`, the indexes
  (validator faults, `indexes update`) and the third_party installer (every archive kind).
- Fixes they found: reinstalling a tool whose folder is locked (Windows: it is running) no
  longer half deletes it (the old folder moves aside and comes back); a build whose `find` file
  is missing leaves the installed tool in place; an unknown archive kind in tools.json is named;
  the RPA reader reads at most 80 bytes of a header (it read any non-RPA file up to its first
  newline) and quotes 16; `viwo trace` with an empty function list is refused (it traced
  nothing), `--functions ""` is no longer replaced by the default.
- `core/downloads.py`: the verified download, safe unzip/untar and folder swap the installer and
  the indexes share (the indexes' own swap removed).

## 1.6.2 (2026-11-04)
- Docs: current state only (CHANGELOG holds history; HANDOFF is the handover and the open work;
  CONFORMANCE regenerated: 165 implemented, 5 partial, 15 open).
- Fixes found by the docs pass: `POST /api/patch` and `POST /api/mod` are routed (the 14 view
  called them; a test now checks every route `api.js` calls); the `extraction`, `sorting` and
  `merger` switches gate what they name (`require`, `gated`); x64dbg and Cheat Engine handoffs
  are dynamic actions (the `capture` switch, one confirmation per game, the warnings; x64dbg
  runs a patched copy); 12.F VERSION DIFF in 12 ANALYSIS; 04 JOBS links patch and mod to 14;
  the game's Oodle DLL loads through `OS.load_native`; the never-written journal removed.

## 1.6.1 (2026-11-04)
- Rung D4, part: `viwo profile` (and `/api/runtime/profile`, PROFILE CPU in 13 RUNTIME): every
  thread of a running game sampled through the OS layer (Windows thread contexts without
  administrator rights, Linux perf); hot spots by module and nearest export, per thread.

## 1.6.0 (2026-11-04)
- Full audit (46 findings) fixed, each with a property test: the wheel ships `viwo/data/**` and
  the portable build adds every script module; a file an antivirus or a lock refuses, or a game
  file removed mid-run, is named and never fails an extraction; a reused agent copy never looks
  finished from the last run; patch offsets are bounded; duplicate mod names refused; a mod's AOB
  adaptation reads every patch back; a cancel anywhere in sanitize apply stays undoable;
  antivirus exclusions shared by concurrent jobs; new workspace folders get a cross-process lock;
  the probe cache keys on size and mtime; the API binds to this machine unless a LAN address is
  chosen; save-remaining needs an absolute destination; finished jobs bounded in memory; a failed
  dump leaves no file; backends no longer import core; the CLI prints every envelope warning.
- Typed decoders: `decode.slp` (Age of Empires SLP sprites to PNG with the game palette),
  Bannerlord TPAC textures to DDS (format and shape from the item metadata), Cyberpunk 2077
  archive members at their real paths from WolvenKit's path list (pin `cp77-hashes`).
- LoC reclaim: one patched-copy helper (repack, patch, mod, agent), one `RuntimeRequest` table
  for every runtime kind, the dead journal-overlay path and the `image.convert` slot removed,
  process listing through Toolhelp32. Budget `viwo = 13900`.
- Python pins hash-locked (`tools/pin_python.py`, `viwo/data/locks/`, `pip install
  --require-hashes`); a platform/version without wheels says why instead of installing unpinned.
- Rung D2 closed: the BepInEx IL2CPP agent verified on Among Us (120 interop assemblies).
- Developed as 1.5.2 (some test docstrings still say so).

## 1.5.1 (2026-11-04)
- Rung A4: `analysis.emulate` (`unicorn-emulate`) and `analysis.symbolic` (`angr-symbolic`) as
  worker tools (`tools.json` `workers`, `viwo/core/workers.py`): pip pins in `third_party/<id>/`,
  never imported, run as `python -I viwo/data/workers/<script>`; `viwo analyze --set KEY=VALUE`;
  routine options in 12 ANALYSIS. angr pinned at 9.2.223 (angr 10 crashes on Windows).
- A file an antivirus removes mid-copy is a named warning; preflight survives a dependency that
  cannot run alone.

## 1.5.0 (2026-11-04)
- Never silent: `Outcome.fallback` names the main backend's failure whenever the spare runs; an
  export that wrote nothing or left notes says so; progress stays on stderr with `--json`.
- Three arms in the UI and CLI: views declare an `arm` (static, dynamic, patching, global); arm
  homes with their end-to-end path; global strip (SYSTEM, JOBS, SETTINGS, game selector,
  workspace); new views 13 RUNTIME and 14 PATCHES + MODS; `viwo <arm>` lists one arm and `viwo
  <arm> <command>` runs a command (`viwo/cli_arms.py`).
- Games passes run against a committed version in a separate worktree.

## 1.4.7 (2026-11-04)
- Rung D3: `handoff.debug` (x64dbg, x32dbg for 32-bit PEs) and `handoff.memory` (Cheat Engine 7.6
  from Scoop's unpacked build, a ViWo table that attaches to the game); `viwo dump` (Windows
  `MiniDumpWriteDump`, Linux `/proc/<pid>/mem`) and `viwo trace` (frida-trace), job kinds `dump`
  and `trace`, routes `/api/runtime/*`.
- Rung D2: runtime agents (`viwo/contracts/runtime.py`): `runtime.unreal` = UE4SS 3.0.1 (writes
  `Mappings.usmap` and the object dump; verified on Void's Cave), `runtime.unity` = BepInEx 6
  be.785 for IL2CPP; `viwo agent`, job kind `agent`; `viwo record` (system loopback to WAV).
- First-run rule: every first-run dialog of a pinned tool is pre-answered off screen (x64dbg
  release notes, Cheat Engine CEShare and table-Lua prompt).
- Global `--features a,b`; plugin commands honour `--profile` and `--features`.
- Patched copies skip files the OS refuses to read and report them. Games pass fixes: VPK subsets
  with absent parts, PFH timestamp bit 0x40, UTF-8-safe integration report.

## 1.4.6 (2026-11-03)
- T1 complete: `rva` addresses (PE sections), `asm` edits assembled by Keystone's `kstool` (a
  pinned process, GPL-2), capstone disassembly in plans, whole-file verification, export of
  `<set>.diff.txt` and `<set>.aob.patch.json` into the copy's `.viwo-patched/`; core slot
  `patch.bytes` (`viwo-patcher`).
- T2 complete: mods carry their AOB patch sets, `requires` and `after`; `mod check` reports
  `adapts` for another game version; `mod apply` orders several mods and refuses conflicts.

## 1.4.5 (2026-11-03)
- Rung A3 version diff: the Ghidra export writes a mnemonic fingerprint per function; `viwo diff
  OLD NEW` and `POST /api/analysis/diff` pair functions by name, then by fingerprint.
- Rung T1 patch sets (`viwo/core/patchsets.py`, `viwo patch`, job kind `patch`): offset and AOB
  patches into a marked patched copy, read back, stackable.
- Rung T2 mod packages (`viwo/core/mods.py`, `viwo mod pack|check|apply`, job kind `mod`).
- Patching-arm CLI handlers in `viwo/cli_patch.py`; the CLI dispatcher is one table.

## 1.4.4 (2026-11-03)
- Temporary antivirus exclusions (`viwo/core/scan_exclusions.py`, `[startup] av_exclusions`):
  workspace, source and temp skip the real-time scan during a job (Defender, elevated only),
  journaled and undone at the next job after a crash.
- A2 complete: `analysis.python` (unrpyc, Ren'Py plugin) and `analysis.gdscript` (GDRE Tools,
  Godot plugin). Detect It Easy pinned for Linux.
- Review batch 5 (13 findings): analysis reruns start empty, `captureAfter` validated, OS-layer
  `config_home` / `data_home`, one `run_tool` for analyzers, `run()` pumps join after 1 s.

## 1.4.3 (2026-11-03)
- The game index holds 23 entries (one per verified title, the library games, Team Fortress 2,
  `unity-generic`, `rpgmaker-mv-generic`). TF2 joins the games pass with a VPK subset.

## 1.4.2 (2026-11-03)
- CTF flags for the library games (`sqc/ctf.json`): three shared baselines plus game-specific
  objectives; analysis flags run `viwo analyze` per target in the integration runner. The generic
  plugin proposes executables up to two folders down.

## 1.4.1 (2026-11-03)
- Rung A3 protector identification: `analysis.protector` = Detect It Easy 3.21 (`identify.json`,
  `identify.txt`). A second analyzer per target kind: `AnalysisRequest.slot`, `extras` in the
  listings, `viwo analyze --slot`.

## 1.4.0 (2026-11-03)
- Rung A2: `analysis.dotnet` (ilspycmd 11.2), `analysis.il2cpp` (Cpp2IL 2022.1 pre-release 21),
  `analysis.script` (unluac on the pinned JDK); `{java}` argv prefix. Verified on Baldi's
  Basics (646 C# files) and an IL2CPP title (80 stub assemblies).

## 1.3.7 (2026-11-03)
- Capture is unattended by default (30 s, `--auto 0` = attended with F12). A file the OS refuses
  to open is a run warning (`CollectReport.unreadable`), never a crash.

## 1.3.6 (2026-11-03)
- Rung D1: unattended RenderDoc capture (`--auto SECONDS`, API `captureAfter`): the game runs as a
  tracked child of `renderdoccmd capture -w`, `rd_trigger.py` takes one frame, the tree is
  stopped; the harvest also writes every shader's disassembly. Verified on ULTRAKILL.
- Minimal-prompt rule: qrenderdoc and Ghidra GUI first-run prompts pre-answered. OS `run()` reads
  through pump threads so a grandchild holding the pipes cannot hang it.

## 1.3.5 (2026-11-03)
- `tools/status_pdf.py` builds the status presentation (`tools/status_template.html`, Edge
  headless print) from the runs, the sqc suite, the CTF flags and the commit log.

## 1.3.4 (2026-11-03)
- Review batch 4: one media-type table (`viwo/core/media.py`), one progress `teller`, the
  sanitizer sink as a context field, one plugin-info loop, the pid check in the OS layer.

## 1.3.3 (2026-11-03)
- `taleworlds` plugin (Bannerlord TPAC, LZ4 blocks through the `lz4` pin). The Ghidra GUI
  handoff starts the JVM directly so the window is a tracked child. CTF flags sized five basic
  plus one per GB, with subsets for large games (`tools/games_pass.ps1`).

## 1.3.2 (2026-11-03)
- Container plugins from the owner's library: `genie` (Age of Empires DRS), `warscape` (Total
  War PFH4/PFH5 packs), `redengine` (Cyberpunk 2077 RDAR, Kraken inflated through the game's own
  Oodle DLL). Verified on real archives.

## 1.3.1 (2026-11-03)
- Review batch 2: one core context factory, `option_bool`, `count_files` in
  `contracts.workspace`, backends' `self_check_args` as the version table, the v1 payload parser
  in the API, plugins receive their `home` (no QuickBMS special case in boot).

## 1.3.0 (2026-11-03)
- Static analysis arm, rung A1: `viwo/contracts/analysis.py` (`AnalysisTarget`, `Analyzer`,
  `Handoff`, `LaunchSpec`), `EnginePlugin.analysis_targets(probe)`, `analysis.native` (Ghidra 12.2
  headless with `viwo/data/ghidra/ViwoExport.java`), `handoff.native` (Continue in Ghidra as a
  tracked child, `ProcessRunner.launch`), `viwo analyze`, `/api/analysis/*`, job kind `analyze`,
  12 ANALYSIS, the `analysis` feature. Ghidra and Temurin JDK 25 pinned; Ghidra on demand.
- `FolderProbe` returns case-preserved paths.

## 1.2.1 (2026-11-03)
- Conformance closure of all 592 clauses: inventory metrics from `verify_report`, the shared
  probe on plugin contexts, merger probe through `media.probe`, suffix-clash boot problem,
  derived capabilities, `--profile`, `GET /api/plugins` fields, `POST /api/jobs` wired, run-record
  context on extractions, process list through the OS layer, missing safety tests.

## 1.2.0 (2026-11-03)
- Contract 1.1 conformance batch: backend `network` and `parses_untrusted_in_process`,
  `self_check`, per-OS executables, manifest fields and option types, ini `contract` key with
  the major check, one `base =` level, value sources, `unarchive.upak` spare, `media.probe`,
  `export.godot`, conformance kit, L0 static tests, zstd/LZ4 stream rung, coverage floors, caps
  `[exceptions]` with expiry, run-record context (`viwo/core/records.py`), `viwo slots --check`,
  `unpack --slot/--backend`, `--quiet/--verbose`, `POST /api/jobs`.

## 1.1.1 (2026-11-03)
- Contract conformance audit (532 clauses, 23 defects, 34 gaps) recorded.

## 1.1.0 (2026-11-03)
- UI component library and functional/style boundary (`viwo/web/js/ui/`, `css/base.css`,
  themes `wormhole` and `plain`), lint and headless-browser smoke tests.
- Plugin add-ons: CLI commands (`cli_commands()`) and UI modules (`/plugins/<id>/ui.js`).
- Survey step events and numbered reports; cleanup as a visible job; `sqc/games.md` and
  `tools/integration_games.py`.

## 1.0.2 (2026-11-03)
- Handoff notes only.

## 1.0.1 (2026-11-03)
- Fixes from the first sqc run and the real-browser smoke: zip member names, stale sanitizer
  plans refused, unknown plugin ids refused (exit 2), `.nw` as zip, installer antivirus failure
  reported; Linux fake-tool shebang.

## 1.0.0 (2026-11-03): first product release
- Philosophy: no policy boundaries in code, a disclaimer instead; every refusal based on what a
  game is became a warning plus one confirmation.
- Startup installer: every tool pinned in `viwo/data/tools.json` (HTTPS, size, sha256) installs
  into `third_party/`; landing screen driven by the preflight job; 05 SYSTEM install and
  maintenance; 10 CAPTURE and 11 SETTINGS; per-game indexes (`indexes/`, `viwo install --game`,
  `viwo indexes update`); drop-in plugins; Ren'Py `.rpyc` decompile; Unity meshes to OBJ;
  `viwo diag`; the `sqc/` manual suite. Released as wheel, sdist and portable Windows zip.

## 0.3.0, 0.2.1, 0.2.0 (2026-11-02)
- 0.3.0: the 1.0 feature batch above. 0.2.1: `tools/version.py` and the pre-commit guard; LF
  line endings. 0.2.0: plan to automate unrar, QuickBMS, DataTool and RenderDoc.

## Before 0.2.0
- The v1 application (RPy Extractor) was hotfixed (game files copied, never moved; workspace
  marker; API token, JSON-only, Host check; safe archive extraction), then replaced. Prototype A
  built the core (contracts, OS layers, ini wiring, slots with failover, stage runner, workspace,
  jobs, CLI, web UI; Ren'Py, Unity, Godot). Prototype B added Unreal, Doom, RPG Maker, KiriKiri,
  Electron, Source, Bethesda, Overwatch and QuickBMS, round trip into a patched copy, mixed mode,
  the sanitizer, the RenderDoc capture pilot and the coverage ladder (carver, streams, decoders,
  survey).
