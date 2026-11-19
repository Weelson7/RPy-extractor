# Handoff

State at **v1.23** (2026-11-19), branch `makeover` (`main` is at v1.20.27 and takes `makeover` after a
`--full` commit). What changed is in [CHANGELOG.md](../CHANGELOG.md), the design in
[docs/contract/](contract/README.md), what is implemented in
[CONFORMANCE.md](contract/CONFORMANCE.md). This page says how to work and what is open.

## Where things are

| What | Where |
|------|-------|
| rules for agents and contributors | `CLAUDE.md`, `CONTRIBUTING.md` |
| module map | `ARCHITECTURE.md` |
| design and conformance | `docs/contract/` |
| web UI, plugin add-ons, per-game indexes | `docs/ui.md`, `docs/plugins.md`, `docs/indexes.md` |
| manual checks, real-game list, CTF flags | `sqc/` (`00-README.md`, `games.md`, `ctf.json`) |
| pins | `viwo/data/tools.json`, `viwo/data/locks/` |

## How to work

```powershell
py -3.13 -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[unity,sevenzip,renpy,lz4,dev]"
python tools/version.py commit -m "..." [--feature|--major] [--full] [--push]
```

- **Commit** only through `tools/version.py commit`: format, lint, caps, the tests the change
  reaches (`tools/affected.py`), version bump, commit, tag. `--full` runs the whole suite:
  use it before a merge to `main` or a tag. One change per commit, subject under 72
  characters, no model names.
- **After changing** plugins or slots: `viwo config generate`. A tool pin: `python
  tools/notices.py`. A Python pin: `python tools/pin_python.py`.
- **Real tools:** `VIWO_L5=1 python -m unittest tests.test_l5_tools tests.test_l5_data
  tests.test_thirdparty` after `viwo install --all`.
- **CI** runs only on `vN.0.0` tags or by the owner's hand. Never dispatch it.

### Real games

Never from a tree being edited. Use a worktree at a committed version with its own venv
(`git worktree add ..\viwo-pass <tag>`), and keep a memory watchdog on the run.

| Run | Command (from the worktree) | Output |
|-----|-----------------------------|--------|
| free test games | `python tools/integration_games.py` | `viwo-data/integration/` |
| installed games, flags of `sqc/ctf.json` | `tools\games_pass.ps1 -Source <games folder> [-Only <folder>]` | `viwo-data/games-pass/<slug>/` |
| every capability on one game | `python tools/deep_pass.py <game> [--arms static,patching] [--workspace WS] [--dynamic]` | `viwo-data/deep-pass/<slug>/` |
| the same on an installed game's copy | `tools\games_pass.ps1 -Deep static,patching -Only <folder>` | `viwo-data/deep-pass/<slug>/` |

The presentation tools (`tools/presentation/`: `frames.py`, `deck.py`, `tech_pdf.py`,
`video.py`) are run only when the owner asks for a new deck, PDF or video.

## How a run behaves

- **Parallel:** the stages share one worker count, 80 % of the processors (`VIWO_WORKERS`);
  results keep the items' order (doc 3.1).
- **Memory:** ViWo's process runs under `[startup] memory_limit` (default 50 % of the machine).
  Child tools that keep what they convert run under a cap held out of a budget of the same
  size (`ctx.memory`). WolvenKit's runs are sized from the files' sizes (doc 8). On the
  Cyberpunk demo subset (183,515 files) the extraction takes 1 h 14 min; the budget is the
  limit there (about five WolvenKit at once).
- **Console:** every stage says what it does, counts, and how long it took; a child tool's
  lines are relayed live; `--json` keeps stdout clean.

## Gotchas

- Bash heredocs on the owner's machine halve backslashes: write files with the file tools.
- Windows Defender quarantines GodotPckTool 2.3 (allow `third_party/godotpcktool`) and holds
  loader DLLs of online-fix builds, which ViWo names as unreadable. Its exclusions need an
  elevated ViWo.
- Ghidra 12.2 needs JDK 25 and refuses project paths with a dot folder (projects live in
  `<workspace>.ghidra/`).
- qrenderdoc's first-run modal blocks `--py`; ViWo pre-answers it.
- angr is pinned at 9.2.223 (angr 10's solver crashes on Windows). Some Python pins have no
  wheel for every CPython (py7zr on 3.14, soundcard/numpy on 3.11, angr outside 3.12-3.13).
- UnityPy holds file handles until `gc.collect()`; close every handle before moving files.
- A reader given a layout that does not fit can ask for all the memory in seconds (it took
  the owner's PC down twice): keep the memory ceiling on when reproducing such a run.
- A WolvenKit run cannot start under about 1.5 GB, and drops bytes appended past a
  resource's own size when it packs.
- Owner's machine: the rejected Cheat Engine 7.7 installer left an uninstall entry and the
  `.CT` association; removing them needs one elevated command.

## Open work

**Waiting on the owner**
- Rename the repository to `ViWo` in GitHub's settings; then update `origin`,
  `viwo/core/diag.py` `REPO`, `tests/test_diag.py`, `indexes/README.md` and the URLs in
  `pyproject.toml` and the README.
- Create the `vidya_wormhole_indexes` repository; the history of `indexes/` is ready on the
  local branch `indexes-main`. Then its first release, and QuickBMS scripts pinned by checksum.
- The `v2.0.0` tag: it starts the paid CI and the release.

**Needs a person at the machine**
- The game loading a change is proven on Ren'Py, Unity, RPG Maker MV, KiriKiri, Unreal, Age of Empires and Doom (SQC-RT-LOAD,
  `tools\game_shot.ps1`, `sqc/proof/`); the other engines are open.
- `viwo attach` (x64dbg live patch, Cheat Engine) and `viwo hook` on a running game
  (SQC-DYN-01, -02, -07).
- The SQC checks that need eyes and a browser (`sqc/`, results marked NOT RUN).

- Godot (the test games carry no PCK data), Bethesda, RPG Maker with a packed archive,
  QuickBMS on a real archive, Overwatch (the independent operator's).

**Linux (WSL Ubuntu-22.04, Python 3.10.12, ran at 1.30.x)**
The suite runs: `Ran 826 tests in 148 modules; FAILED: test_hook, test_owmdl, test_thirdparty`,
with Pillow + UnityPy installed (without them ~26 modules fail for want of those deps). What is
left, by cause:
- `test_owmdl`: a cross-platform bug in `plugins/overwatch/owmdl.py`. DataTool writes Windows
  paths; the material name is read with `Path(src.text()).name`, which does not split on `\` off
  Windows, so the material never resolves. Splitting it (`.replace("\\", "/")`) gets further but
  then hits a second parse mismatch not yet pinned down — left whole, not half-fixed.
- `test_hook`, `test_thirdparty` (`test_python_pins...`): no Linux-3.10 package locks. 3.10 was
  added to `tools/pin_python.py` at 1.27.5 but the locks were never generated; run
  `python tools/pin_python.py` to write them (a long download job).
- `test_thirdparty` (`...ships_in_the_wheel`): the dev venv needs the `wheel` package
  (`bdist_wheel`); not a ViWo bug. Also: `Pillow` is a real runtime dependency reached only
  transitively through UnityPy (`.[unity]`) — it should be declared, or image decoding fails on a
  minimal install.
- The memory ceiling, the child cap and `memory_room` have a Linux side still only unit-tested.

**Open in the code**
- Patcher / isolation (doc 11.8, rung T4) is **built across all three tiers**: the contract
  (`viwo/contracts/patcher.py`), VirtualBox T1 (`vbox.py`, `VBoxManage`), QEMU T2 out of the guest
  over its gdbstub + QMP (`qemu.py` with the first-party GDB-remote-serial client `gdb.py` and
  `qmp.py`), DRAKVUF/LibVMI T3 (`vmi.py`: `vmi-dump-memory`, `virsh`/`xl`, not-ready off a Linux
  VMI host), Scylla dump-to-patch (`attach.dump`), the cold+live bridge (`live.py`: one located
  patch written cold or live) and the session surface (`viwo isolate`, `/api/runtime/isolation`,
  RUNTIME). Tested on fakes and in-process loopback gdbstub/QMP stubs (`tests/test_isolation.py`,
  `test_isolation_tiers.py`, `test_isolation_bridge.py`). **Still open, and the only open piece:
  real in-VM proof** — no VM, QEMU or VMI host has run here; VirtualBox and QEMU are located-only
  (a person installs them and runs `viwo isolate` against a real guest; needs a machine). T3 also
  needs a bare-metal Linux KVM/Xen host, and a LibVMI/DRAKVUF write helper for a live `write_mem`.
- Desktop-app frameworks (doc 13.8): the Qt embedded-resource carve recovers textual resources
  by content, not the resource tree's names (a stripped binary keeps none) — reconstructing the
  `qt_resource_struct`/`qt_resource_name` tables from a binary would give real paths. A .NET
  managed resource whose edited size changed is refused; rewriting the ManifestResource offsets,
  the CLI header size and the section table would lift that. PyInstaller PYZ-interior modules are
  read but not repacked. No Python or Java class decompiler is pinned (bytecode only). Free
  Download Manager's connection cap is native (the `MaxConnectionsPerServerLimit` setting), so
  the full proof is a `patch.bytes` binary patch located with the disassembler (not run here).
- The game-folder guard without a game path (doc 3.1) knows the games ViWo was given, Steam
  libraries, Epic and GOG installs and patched copies; a game ViWo was never given, from no
  store with marks, is still out of its reach.
- `memory_image` targets (doc 6.5): a full-memory minidump takes Ghidra long (a 14.6 MB dump
  of `ping.exe`: 47 min, 21,859 functions decompiled); a game's dump is far larger. Not yet
  run on a game's dump; the Linux `.mem` layout has no reader.
- Sanitizer phases 2-3 (doc 5.1) are tests only, on a stand-in ffmpeg: the transcode presets
  (libopus, libx264 of the pinned ffmpeg 6.1.1) and a real decoder through `core.convert` on a
  real workspace are to be run once; `[hooks]` (doc 9.5) ran on Windows only (`cmd /d /s /c`).
- CONFORMANCE rows: the way back of typeless BC6H DDS (no decoder) and of ETC, ASTC, PVRTC or
  Basis Godot textures (no decoder for those either) (doc 18.3; premultiplied DXT2/DXT4 and
  signed BC4/BC5 now encode, at 1.32; the BC1-BC7, `.ctex` and redscripts ways back are tests
  only: a real game pass for each is open, redscripts with the compiler installed in the copy;
  `pack.tpac` rewrote one real Bannerlord package by hand, unchanged and with a BC7 texture
  edited, but no repack run has put one in a patched copy the game then started: it may check
  the item checksum ViWo keeps but cannot compute), the one engine doc 13.7 still lists (Unreal
  asset export, a CUE4Parse wrapper), a structured runbook editor, more workbooks.
- LÖVE, XNA/FNA, AGS, Defold, Unreal `.locres`, Wolf RPG, GameMaker and TyranoScript (first-party
  readers and their ways back): checked on real data from the engines' own releases (CLIB 30
  templates, a Defold index-6 example bundle, the official `love.exe` fused with a test zip,
  MonoGame's test XNB files), never on a game install, and no game has run with a change. Wolf RPG
  (DXArchive v6), XNB LZX, GameMaker (the `FORM` container, at 1.33) and TyranoScript (loose
  HTML5/JS, at 1.33) are proven only on fixtures the tests write byte by byte, never on a real
  file. Defold's XTEA-CTR resource decryption (at 1.33) matches the engine's own test vector but
  has not been re-run against the real example's two encrypted resources (operator's job).
  Unverified on real data: LZ4 XNB, CLIB 6 to 21, Defold index 4 and 5 and its encrypted
  resources, any `.locres`, any Wolf RPG archive, any LZX XNB, any GameMaker or TyranoScript game.
  Open in them: XNB content other than Texture2D/SoundEffect, Wolf RPG's DXA-compressed members
  (ViWo's DXA decoder is unverified) and versions other than 6, a Defold bundle whose only
  encrypted resources are uncompressed (the key cannot be self-verified), GameMaker's full
  re-chunk (only same-size edits go back), new keys in version 3 `.locres`.
- `hook.overlay`: neither candidate fits the rules (doc 11.7).
- Coverage: 98.2 % line / 95.0 % branch overall at 1.20.58 (`coverage run -m unittest discover
  -s tests -t .`, then `combine` and `json`). Many files are still under the per-file target of
  98 / 95. The furthest are `os/linux.py`, `contracts/paths.py` (links need rights Windows does
  not give), the isolation arm (`core/isolation/*`: QEMU/VBox/gdb need the VMs) and the packers'
  error paths. Raised to 100 % line / 100 % branch (a single Windows L0-L4 run): `core/hooks.py`,
  `plugins/dotnet/pe.py`, `plugins/qt/{qm,binres,pack,rcc}.py`, `plugins/chromium/pack.py` (their
  bad-magic, overrun, unknown-member and verify-mismatch paths; `tests/test_job_hooks.py`,
  `test_dotnet.py`, `test_qt.py`, `test_chromium.py`). Still open and high-value next:
  `plugins/dotnet/{meta,resources}.py` (need no-tables / linked-resource metadata fixtures),
  `plugins/qt/__init__.py`, `plugins/dotnet/pack.py`.
- Completeness (doc 16.0c): everything out of every game, decoded, on all three arms. Notes
  kept for it: Unity IL2CPP MonoBehaviour fields come out for the scripts whose rebuilt
  layout fits (the rest are listed without fields); Unreal models are UEFormat (glTF needs
  another exporter); a REDengine TweakDB reader was prototyped and not shipped (one game);
  Total War schemas install with `viwo install rpfm-schema-<game>`. Models as `.glb`: Total
  War rigid models versions 1, 3 (Rome II's few oldest files) and 8 (Warhammer III) are
  refused, as are flag placements and lights (no vertex data) and Rome II's one debug capsule
  (material type 46, layout not verified); version 5 names its colour maps `.tga` (71 of 157 are
  in the packs as `.dds` under the same path, not substituted); version 7 is tests only, as is all of NIF (no
  Bethesda game at hand, the skin partition included); NiTriStrips and Fallout 4's `.bgsm`
  materials are not read yet.
