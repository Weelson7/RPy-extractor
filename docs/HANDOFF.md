# Handoff

State at **v1.20.65**, branch `makeover` (`main` is at v1.20.27 and takes `makeover` after a
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
- The game loading a change is proven on Ren'Py, Unity and RPG Maker MV (SQC-RT-LOAD,
  `tools\game_shot.ps1`, `sqc/proof/`); the other engines are open.
- `viwo attach` (x64dbg live patch, Cheat Engine) and `viwo hook` on a running game
  (SQC-DYN-01, -02, -07).
- The SQC checks that need eyes and a browser (`sqc/`, results marked NOT RUN).

**Needs an environment or a game that is not here**
- Linux: the suite passed at 1.20.13; the memory ceiling, the child cap and `memory_room`
  have a Linux side that never ran. No Linux environment is at hand.
- Godot (the test games carry no PCK data), Bethesda, RPG Maker with a packed archive,
  QuickBMS on a real archive, Overwatch (the independent operator's).

**Open in the code**
- The game-folder guard without a game path (doc 3.1): `dump`, `trace`, `hook`, `profile`,
  `record` and `sanitize` cannot tell a new folder inside a game, a folder above one, or a game
  carrying a workspace marker. `viwo unpack --out` and `viwo diff --out` take no game either:
  unpack needs an empty or new folder (it never overwrites), diff writes its two files.
- CONFORMANCE rows: sanitizer phases 2-3, the `supplement` slot policy, `[hooks]`,
  `memory_image` targets, asset converters, Kaitai formats, the engines of doc 13.7, a
  structured runbook editor, more workbooks.
- `hook.overlay`: neither candidate fits the rules (doc 11.7).
- Coverage: 98.2 % line / 95.0 % branch overall at 1.20.58; 84 of 200 files are under the
  per-file target of 98 / 95 (`coverage run -m unittest discover -s tests -t .`, then
  `combine` and `json`). The furthest are `os/linux.py`, `contracts/paths.py` (links need
  rights Windows does not give) and the packers' error paths.
- UI review findings left: the ANALYSIS action bar over VERSION DIFF, button spacing in
  RUNTIME, PATCHES and RUNBOOKS, single-file groups in MERGER, repeated codes on the arm
  homes, raw JSON in RUNBOOKS steps.
- Completeness (doc 16.0c): everything out of every game, decoded, on all three arms. Notes
  kept for it: Unity IL2CPP MonoBehaviour fields come out for the scripts whose rebuilt
  layout fits (the rest are listed without fields); Unreal models are UEFormat (glTF needs
  another exporter); a REDengine TweakDB reader was prototyped and not shipped (one game);
  Total War schemas install with `viwo install rpfm-schema-<game>`.
