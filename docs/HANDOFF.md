# Handoff

State at **v1.6.0** (branch `makeover`). History is in [CHANGELOG.md](../CHANGELOG.md); the
design in [docs/contract/](contract/README.md); what is open in
[CONFORMANCE.md](contract/CONFORMANCE.md) and below.

## Where things are

| What | Where |
|------|-------|
| rules for agents and contributors | `CLAUDE.md`, `CONTRIBUTING.md` |
| module map | `ARCHITECTURE.md` |
| normative design, conformance | `docs/contract/` |
| web UI layers, plugin add-ons, per-game indexes | `docs/ui.md`, `docs/plugins.md`, `docs/indexes.md` |
| manual check suite, real-game list, CTF flags | `sqc/` (`00-README.md`, `games.md`, `ctf.json`) |
| pins | `viwo/data/tools.json`, `viwo/data/locks/` |
| release notes body used by the release workflow | `docs/release-notes.md` |

## How to work

```powershell
py -3.13 -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[unity,sevenzip,renpy,lz4,dev]"
ruff format viwo tests tools packaging; ruff check viwo tests tools packaging
python tools/loc_count.py --report
python -m unittest discover -s tests -t .      # 566 tests, ~19 min on Windows
python tools/version.py commit -m "..." [--feature|--major] [--push]
```

- **Commits** only through `tools/version.py commit`: it runs format, lint, caps and the suite,
  bumps `va.b.c`, commits and tags; the pre-commit hook refuses a version not past the latest
  tag. No model names in messages. CI and the release workflow run only on `vN.0.0` tags or by
  hand; never dispatch them without the owner.
- **Real tools:** `VIWO_L5=1 python -m unittest tests.test_l5_tools tests.test_l5_data
  tests.test_thirdparty` after `viwo install --all`.
- **After changing plugins or slots:** `viwo config generate` (the drift test fails otherwise).
  After changing a pin: `python tools/notices.py`; after changing a Python pin:
  `python tools/pin_python.py`.
- **Games pass** (real games, L7): never from a tree being edited (a pass once imported a
  half-edited module). Make a worktree at a committed version with its own venv, then run the
  pass there:
  ```powershell
  git worktree add ..\viwo-pass v1.6.0
  cd ..\viwo-pass; py -3.13 -m venv .venv; .venv\Scripts\pip install -e ".[unity,sevenzip,renpy,lz4]"
  powershell -File tools\games_pass.ps1 -Source C:\Users\<you>\Games [-Only <folder>,...]
  ```
  `games_pass.ps1` copies each game (or its `sqc/ctf.json` subset) into `Test-games/<slug>`, runs
  `tools/integration_games.py` on the copy (detect, survey, extract, repack and sanitize plans,
  analysis flags, game-folder hash check), keeps `viwo-data/games-pass/<slug>/report.*` and
  deletes the copy. Free titles: `python tools/integration_games.py` over `Test-games/`
  (`sqc/games.md`).
- **Status PDF:** `python tools/status_pdf.py [--out PATH] [--tests LOG]` fills
  `tools/status_template.html` from the reports, the sqc suite, the CTF flags and the commit log
  and prints it with headless Edge.

## Gotchas that still apply

- Bash heredocs on the owner's machine halve backslashes: write files with the file tools.
- Windows Defender: quarantines GodotPckTool 2.3 (allow `third_party/godotpcktool` for
  `pack.pck`); holds loader DLLs of online-fix builds (`Custom.dll`, `winmm.dll`,
  `OnlineFix64.dll`), which ViWo names as unreadable or not copied; Defender exclusions need an
  elevated ViWo.
- Ghidra 12.2 needs JDK 25 and refuses project paths with a dot folder (projects live in
  `<workspace>.ghidra/`); `cmd /c` drops the quotes of a batch path with spaces (`call` fixes it).
- qrenderdoc's first-run analytics modal blocks `--py`; ViWo pre-answers it. A grandchild holding
  pipes (qrenderdoc's adb server) is why `run()` reads through pump threads.
- angr is pinned at 9.2.223 (angr 10's solver crashes on Windows); some Python pins have no
  wheels for every CPython (py7zr on 3.14, soundcard/numpy on 3.11, angr outside 3.12-3.13).
- UnityPy holds file handles until `gc.collect()`; close every handle before moving files.
- Owner's machine: the rejected Cheat Engine 7.7 installer left an uninstall entry, the `.CT`
  association and `third_party/.cheatengine-7.7-installer-leftover`; removing them needs one
  elevated command.

## Open work

1. **Rung D4** (partly shipped: CPU profiling, `viwo profile`, 1.6.1): open are the hook loader
   with hot reload (`hook.inject`), the overlay (`hook.overlay`) and own-traffic network tooling
   (`net.*`). The network plaintext capture and the DLL injection loader are the owner's call and
   are not authored by the assistant.
2. **Coverage** (in progress): owner's target 98 % line / 95 % branch per file; measured 98.6 %
   line / 95.3 % branch overall at 1.6.23 (child processes counted); 72 files are still under
   the per-file target, most by one or two branches. Tests are property checks over random
   inputs, never assertions for their own sake. The CI floors (`tools/coverage_check.py`) only
   move up.
3. **CONFORMANCE partials:** built-in plugins keep no inventory and ship no sanitizer rules
   (the hooks work; nothing needs them yet); `core/thirdparty.py` runs `msiexec` (recorded).
4. **CONFORMANCE opens:** sanitizer phases 2-3, `[slot_policy]`, `[hooks]`, `--plugin`/`--slot`
   overrides, `memory_image` targets, round-trip converters, the engines of doc 13.7, Kaitai
   plugins.
5. **Indexes:** create the `vidya_wormhole_indexes` repository, split `indexes/` out
   (`docs/indexes.md`), publish its first release; add QuickBMS scripts pinned by checksum.
6. **Not verified on real data:** DataTool on a real Overwatch install (independent operator);
   QuickBMS on a real game archive; the Godot PCK path on a title that ships its data; the game loading a
   `pack.archive` override (`archive/pc/mod/!viwo_*.archive`, ahead of other mods by name).
7. **Completeness contract (doc 16.0c, owner):** everything out of every game, decoded, all
   three arms per engine; every capability valid for all games of its engine (owner: no
   overfitting to one game). Work the open column of the 16.0c table by reach; a row closes only
   when verified on a real install. Verifiable here: Cyberpunk 2077, two Unity IL2CPP games,
   two Unity Mono test games, a UE5.1 test game, Rome II, Bannerlord, AoE II HD, Ren'Py, RPG
   Maker MV; no Godot game with data, no Source, Bethesda, KiriKiri-with-TLG or RPG Maker XP/VX.
   Findings kept for the open rows:
   - Unity IL2CPP MonoBehaviour fields: UnityPy's TypeTreeGenerator recovers almost nothing on
     Unity 2022.3/6 IL2CPP (12/64,657 on Schedule I; "failed to load il2cpp" on Unity 6); the
     Cpp2IL stand-in route (`load_local_dll_folder` on Cpp2IL's dummy assemblies) is untested.
   - Unreal models are UEFormat (`.uemodel`, Blender importer); glTF needs another exporter.
   - REDengine TweakDB: a reader prototype works (flats: per type `<QIII>` header (hash
     FNV-1a64 of the type name, values, keys, offset); values then keys `<QI>`; arrays and string
     lengths are the engine's packed int; records `<QI>` id and Murmur3 seed 0x5EEDBA5E of the
     class name, whose names are in the game's exe as `gamedata<Name>_Record`); names from
     WolvenKit's `tweakdbstr.kark` (Kraken); 164 MB JSON in 11 s on 2.x. Not shipped (one game).
   - Total War schema install on first use (today: `viwo install rpfm-schema-<game>`).
8. **End of the open work, in this order:** a full audit (and its fixes); then the
   presentation, in two parts that replace the status PDF. (The UX/UI review from frames of the
   running UI at the owner's window and zoom, and on a real extraction, was done at 1.12.0; it
   is repeated for the demo.)
   - a product demo video (MP4, on-screen captions, no voice) on Cyberpunk 2077, the most
     technically advanced covered game: boot, setup from blank, survey, select, extract, browse
     the assets, the analysis, runtime and patching arms where they apply;
   - a technical PDF (built by a `tools/` script from HTML): architecture and the three arms in
     mermaid diagrams, every view with its screenshot, the specs (contract, conformance, CLI,
     API, plugins); clear, structured, in depth, the whole UI and every feature.
9. **v2.0.0:** the tag needs the owner's approval: it starts the paid CI and the release workflow.
