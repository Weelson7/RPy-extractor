# ViWo (Vidya Wormhole): instructions for coding agents

Local-first game reverse-engineering orchestrator over three arms (static, dynamic, patching).
Python 3.11+, stdlib first, plain-ES-module web UI (no build step). Start with `ARCHITECTURE.md`,
then `docs/HANDOFF.md` (current state, how to work, open work), then `docs/contract/` (the
normative design; `CONFORMANCE.md` says what is implemented, partial or open).

## Docs (owner's rule)
Docs are the source of truth and describe the current state only. Update them in the commit that
changes the behaviour (contract doc, `CONFORMANCE.md` row, HANDOFF open work); history goes into
`CHANGELOG.md` only. Keep contract section numbers stable: code cites them as "doc N.M".

## Philosophy (owner's decision, confirmed; README "Philosophy" is the reference)
Community tool, MIT, forkable. It is for everyone who wants to look inside a game and judges
neither the user nor the purpose. **No boundaries and no safeguards in the code**: ViWo refuses
nothing because of what a game is, which plugin runs, or what the user intends; anti-cheat and
online detection are warnings plus one opt-in, never a gate. A disclaimer replaces safeguards.
Borderline code (DRM defeat, key brute force, anti-cheat evasion) is never first-party: ViWo does
not author it; if it exists it is a pinned third-party tool or community script under the
disclaimer. Engineering properties are not boundaries; any that blocks a wanted capability
becomes an option.

## Engineering rules
- The game folder is read-only. Extraction copies; repack, patch sets, mods and runtime agents
  write a separate, marked patched copy (`.viwo-patched/`). Nothing writes into a game folder.
- Never silent (owner's rule): a fallback to the spare, an empty export, a skipped or unreadable
  file is said in the CLI and the GUI (`Outcome.fallback`, warn events).
- Minimal prompts (owner's rule, critical): whatever a tool needs on first run or after a config
  change happens by itself, off screen: no dialogs, no wizards, no installers, no UAC.
- Keys come from the user or from the game's own local files and are verified before use (D18).
- Secrets and found keys are never logged or written to disk (run records store `<secret>`).
- GPL/AGPL tools run only as separate processes, never imported.
- `tos_sensitive` plugins (Overwatch) carry a reminder on every run; real-game tests are the
  independent operator's job, not yours.
- Every write into a folder built from untrusted names goes through `contracts.workspace.safe_member`
  and `contracts.workspace.inside` (traversal, drive letters, links).
- Third-party tools are pinned (version, size, sha256) in `viwo/data/tools.json`, HTTPS only,
  installed into `third_party/` and nowhere else.
- Python packages are pinned in `tools.json` (`python`, `workers`) and installed only from their
  hash locks (`viwo/data/locks/`, written by `python tools/pin_python.py`; rerun it when a pin
  changes). Worker packages (GPL: Unicorn, angr) are never imported, only run as processes.

## Commands (Windows, PowerShell)
```powershell
py -3.13 -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[unity,sevenzip,renpy,dev]"
ruff format viwo tests tools packaging; ruff check viwo tests tools packaging
python tools/loc_count.py --report          # caps: run AFTER ruff format
python -m unittest discover -s tests -t .    # 541 tests, ~18 min; real-tool tests need VIWO_L5=1
viwo serve                                   # web UI, opens the browser
viwo config check startup.ini distros/*.ini  # strict config validation
```
Always run format, lint, caps and the full test suite before committing. After changing plugins
or slots run `viwo config generate`; after changing a tool pin run `python tools/notices.py`.
Real-game passes run from a worktree at a committed version (`tools/games_pass.ps1`,
`docs/HANDOFF.md`), never from a tree being edited.

## Versioning and commits (owner's rule, enforced by a pre-commit hook)
Version `va.b.c`: `a` product release (roadmap finished; CI runs on its tag), `b` feature
(new feature or overhaul), `c` tweak (every commit). Never run `git commit` yourself:
```powershell
python tools/version.py commit -m "message" [--feature|--major] [--push]   # checks, bump, commit, tag
```
The hook refuses a commit whose version is not past the latest `v*` tag. Push the branch with
all tags (`--push`). Do not put model names in commit messages.

## Code size caps (enforced by tools/loc_count.py and a test)
Non-blank, non-comment lines: function 40, class 200, file 250 (contracts 150, tests 400),
params 6, line length 100, JS file 300. Package budgets are in `loc_caps.ini`; raise one only with
a reason in the comment next to it. Split functions rather than bending the caps.

## CI policy (owner's rule: GitHub Actions minutes cost money)
- CI runs only for major release tags (`vN.0.0`) or when the owner starts it by hand.
- Never dispatch workflows yourself unless the owner asks for that specific run. Test locally.
- `release.yml` (one Windows job, on a `vN.0.0` tag push or by hand) builds wheel + sdist + the
  portable `viwo.exe` bundle and publishes the GitHub release with `docs/release-notes.md` as
  its body. Run it only when the owner asks to ship; a `vN.0.0` tag needs the owner's approval.

## Windows gotchas
- Store relative paths in JSON/provenance with `.as_posix()`; compare paths with `Path`, not strings.
- Close every file and mmap (use `with`); UnityPy holds handles until `gc.collect()`. Open handles
  lock files on Windows and break later moves/deletes.
- Tests that fake external tools write a `.py` script plus a `.cmd` wrapper on Windows; follow the
  pattern in `tests/test_godot.py` (`fake_tools`). Use `\r\n` (not `\\r\\n`) in those wrappers.
- `bash` steps in workflows on Windows run in Git Bash: convert paths with `cygpath -w` before
  handing them to Python.

## Layout cheat sheet
- `viwo/contracts/` interfaces only · `viwo/os/` OS layer · `viwo/backends/` core unarchivers
- `viwo/core/` wiring (ini, registry, binder, distros), pipeline, carve, decode, curation, merger,
  sanitizer, survey, analysis (static arm), capture (dynamic arm), roundtrip, patchsets, mods,
  thirdparty, downloads, workers, preflight, indexes
- `viwo/plugins/<engine>/` one folder per engine · `viwo/api/` server · `viwo/web/` UI ·
  `viwo/cli*.py` CLI (commands grouped by arm in `cli_arms.py`)
- `distros/` generated configs (`viwo config generate`; a test guards against drift)
- `packaging/` frozen build (`build_portable.py`, `viwo_entry.py`)
