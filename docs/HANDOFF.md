# Handoff

State at **v1.20.27** (branch `makeover`; local `main` fast-forwarded to it). History is in [CHANGELOG.md](../CHANGELOG.md); the
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
python tools/run_tests.py                      # the whole suite in parallel (a commit runs the affected tests)
python tools/version.py commit -m "..." [--feature|--major] [--push]
```

- **Commits** only through `tools/version.py commit`: it runs format, lint, caps and the tests
  the change is close to (`tools/affected.py`, doc 17; `--full` before a merge or a tag),
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
  git worktree add ..\viwo-pass v1.20.27
  cd ..\viwo-pass; py -3.13 -m venv .venv; .venv\Scripts\pip install -e ".[unity,sevenzip,renpy,lz4]"
  powershell -File tools\games_pass.ps1 -Source C:\Users\<you>\Games [-Only <folder>,...]
  ```
  `games_pass.ps1` copies each game (or its `sqc/ctf.json` subset) into `Test-games/<slug>`, runs
  `tools/integration_games.py` on the copy (detect, survey, extract, repack and sanitize plans,
  analysis flags, game-folder hash check), keeps `viwo-data/games-pass/<slug>/report.*` and
  deletes the copy. Free titles: `python tools/integration_games.py` over `Test-games/`
  (`sqc/games.md`).
- **Presentation** (`tools/presentation/`, owner's two parts): `frames.py <game> [--features
  extraction,sorting,merger,analysis,capture] [--keep]` serves ViWo with the repository's
  startup.ini (the switches overridden for the run only; the run's workspace is deleted after
  unless `--keep`) on a fresh workspace and drives headless Edge or Chrome
  through every view (`shots.mjs`: one PNG per step, a burst while an extraction runs, with a
  caption and a longer description each, in `steps.json`); `tech_pdf.py` builds the technical
  PDF from `tech_template.html` (mermaid charts, pinned and installed by itself), the frames and
  reference tables generated from the code (`reference.py`); `video.py` turns the frames into
  the demo MP4 with burned-in captions through the pinned ffmpeg; `deck.py` builds the
  technical deck (PowerPoint, the presentation the owner shows: the PDF stays as the long
  reference) from `deck.js` (layout and prose), the frames, the counts of the code and the
  CTF results, through the pinned pptxgenjs (one file, run by Node, nothing to install); check
  a new deck by eye before it leaves (PowerPoint or LibreOffice renders it). Output in
  `viwo-data/presentation/`. Capture the frames on the demo game (Cyberpunk 2077) after the
  last change to the UI.
- **Deep pass** (real games, every capability, judged on its output): from the same worktree,
  `python tools/deep_pass.py <game folder> [--dynamic] [--exe EXE]` runs detect, a deep survey,
  a full extraction, the accounting of every game byte and workspace file (open, raw, unknown;
  the raw types ranked), every decoded file opened by a real reader (Pillow, WAV, JSON, glTF,
  ffprobe), a contact sheet of sampled images, cleanup plan/apply/undo, every analysis target,
  a real edit per container type repacked and read back, an AOB patch set, a mod packed,
  checked and applied, and with `--dynamic` capture, the engine agent, a dump, a trace and the
  game's sound. Reports in `viwo-data/deep-pass/<slug>/` (`report.md`, `report.json`,
  `contact.png`); the game folder is only read (checked). A patched copy is skipped, and said,
  when the disk cannot hold one.

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
- A reader given a layout that does not fit (UnityPy with Cpp2IL's stand-ins on Schedule I) can
  ask for all the machine's memory in seconds: it took the owner's PC down twice (2026-11-10).
  `[startup] memory_limit` (default 50 %) now stops it inside ViWo; when reproducing such a run,
  keep the ceiling on. The Linux side (soft data limit) is written but not run on Linux yet.
- Owner's machine: the rejected Cheat Engine 7.7 installer left an uninstall entry, the `.CT`
  association and `third_party/.cheatengine-7.7-installer-leftover`; removing them needs one
  elevated command.

## Open work

- **Waiting on GitHub** (unreachable since 2026-11-05; the owner says when it is back): push
  `makeover` and `main` with every tag from v1.20.10 on (`git push origin makeover main --tags`),
  then rename the repository from `RPy-extractor` to `ViWo` (GitHub redirects the old URL) and
  point `origin` and the URLs in `pyproject.toml` and the README at the new name.
0. **UI capabilities (doc 16.4, spec in doc 19; owner flagged, in this order):** workbooks
   shipped (1.18.0: four, for x64dbg, Ghidra and Cheat Engine; 1.20.8: RenderDoc, on the frames
   a capture now keeps; more tools and topics by reach, e.g. WolvenKit, whose GUI ViWo does not
   pin); runbooks shipped (1.19.0: three defaults, run one step per
   request through the job handlers, edited as JSON; a structured step editor is open);
   workflows shipped (1.20.0: the server records every action route, saved as a runbook with
   expected answers; replay stops where one differs; what is done inside a child tool is a
   note the user writes). Embedded child GUIs are dropped (owner, 2026-11-05): native tools stay
   native, in their own windows (doc 19.4). Open here: more workbooks by reach, a structured
   runbook step editor.
1. **Rung D4** (shipped: CPU profiling `viwo profile`; own traffic `attach.net`, mitmproxy;
   the user's hook script `viwo hook`, the pinned Frida, verified on a process that is not a
   game): open is the overlay (`hook.overlay`). Special K is not pinned because it works around
   CAPCOM's copy protection by default (the owner's call) and MangoHud's release installs into
   `/usr` with `sudo` (doc 11.7). D4 is served by third-party tools only.
2. **Coverage** (in progress): owner's target 98 % line / 95 % branch per file; measured 98.6 %
   line / 95.3 % branch overall at 1.6.23 (child processes counted); 72 files are still under
   the per-file target, most by one or two branches. Tests are property checks over random
   inputs, never assertions for their own sake. The CI floors (`tools/coverage_check.py`) only
   move up.
3. **CONFORMANCE partials:** built-in plugins keep no inventory and ship no sanitizer rules
   (the hooks work; nothing needs them yet); `core/thirdparty.py` runs `msiexec` (recorded).
4. **CONFORMANCE opens:** sanitizer phases 2-3, `[slot_policy]`, `[hooks]`,
   `memory_image` targets, round-trip converters, the engines of doc 13.7, Kaitai
   plugins.
5. **Indexes:** create the `vidya_wormhole_indexes` repository, split `indexes/` out
   (`docs/indexes.md`), publish its first release; add QuickBMS scripts pinned by checksum.
6. **Not verified on real data:** `viwo attach` since 1.17.0 (SQC-DYN-01/02: x64dbg attached to a
   running game and a live byte patch, Cheat Engine's table under `.runtime/`);
   DataTool on a real Overwatch install (independent operator);
   QuickBMS on a real game archive; the Godot PCK path on a title that ships its data; the game loading a
   `pack.archive` override (`archive/pc/mod/!viwo_*.archive`, ahead of other mods by name).
7. **Completeness contract (doc 16.0c, owner; per engine in CONFORMANCE "Done, per engine and
   arm"):** everything out of every game, decoded, all
   three arms per engine; every capability valid for all games of its engine (owner: no
   overfitting to one game). Work the open column of the 16.0c table by reach; a row closes only
   when verified on a real install. Verifiable here: Cyberpunk 2077, two Unity IL2CPP games,
   two Unity Mono test games, a UE5.1 test game, Rome II, Bannerlord, AoE II HD, Ren'Py, RPG
   Maker MV; no Godot game with data, no Source, Bethesda, KiriKiri-with-TLG or RPG Maker XP/VX.
   Findings kept for the open rows:
   - Unity IL2CPP MonoBehaviour fields: the export feeds Cpp2IL's stand-in assemblies to
     UnityPy's TypeTreeGenerator (1.16.5): 270 of 745 MonoBehaviours of Schedule I's
     resources.assets come out with their fields (6 without); the rest fail inside the native
     generator ("Object reference not set", generic and nested types).
   - Unreal models are UEFormat (`.uemodel`, Blender importer); glTF needs another exporter.
   - REDengine TweakDB: a reader prototype works (flats: per type `<QIII>` header (hash
     FNV-1a64 of the type name, values, keys, offset); values then keys `<QI>`; arrays and string
     lengths are the engine's packed int; records `<QI>` id and Murmur3 seed 0x5EEDBA5E of the
     class name, whose names are in the game's exe as `gamedata<Name>_Record`); names from
     WolvenKit's `tweakdbstr.kark` (Kraken); 164 MB JSON in 11 s on 2.x. Not shipped (one game).
   - Total War schema install on first use (today: `viwo install rpfm-schema-<game>`).
8. **End of the open work, in this order:** the full audit is done (fourth audit, 1.20.2, and
   its last open point at 1.20.6: Genie and Warscape detect by their archive signatures); the
   LoC-reclaim pass is done (1.20.3 and 1.20.7: web back to its own budget, `viwo` 17,187 ->
   16,701, the tools' descriptions in `viwo/data/dependencies.json`, unused contract members
   dropped; API handlers keep answering failure dicts, see CHANGELOG 1.20.7). Next the presentation, in two parts that replace the status PDF. The
   whole of Cyberpunk 2077 (86 GB) cannot be extracted inside the walk (hours, and its
   uncompressed archives come close to the free disk), so the demo runs on the subset the
   games pass already defines (`sqc/ctf.json` `pass-cyberpunk-2077`: seven archives, 6.7 GB)
   plus the executable and `final.redscripts`, copied to `Test-games/cyberpunk-2077-demo`
   (owner's approval, 2026-11-05); its extraction takes about 2 h 20 min (87,000 files, of
   which 62,653 CR2W through WolvenKit for about 100 minutes), the walk waits up to four hours
   for it and for every view to finish loading, and `frames.py` cancels and waits for any job
   still running, so no staging is left behind. The first capture (at 1.20.6) ran out of its
   two hours in the WolvenKit decode, whose counter did not move (fixed at 1.20.9); the capture
   at 1.20.9 came out whole (183,621 files, every view loaded) but for the debugger frame
   (fixed at 1.20.10); recapture at 1.20.10 or later.
   (The UX/UI review from frames of the running UI at the owner's window and zoom, and on a
   real extraction, was done at 1.12.0; it is repeated for the demo.)
   - a product demo video (MP4, on-screen captions, no voice) on Cyberpunk 2077, the most
     technically advanced covered game: boot, setup from blank, survey, select, extract, browse
     the assets, the analysis, runtime and patching arms where they apply;
   - a technical PDF (built by a `tools/` script from HTML): architecture and the three arms in
     mermaid diagrams, every view with its screenshot, the specs (contract, conformance, CLI,
     API, plugins); clear, structured, in depth, the whole UI and every feature.
9. **v2.0.0:** the tag needs the owner's approval: it starts the paid CI and the release workflow.
