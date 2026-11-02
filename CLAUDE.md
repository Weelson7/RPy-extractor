# ViWo (Vidya Wormhole): instructions for coding agents

Local-first game reverse-engineering platform, asset-extraction oriented. Python 3.11+, stdlib
first, plain-ES-module web UI (no build step). Start with `ARCHITECTURE.md`, then
`docs/HANDOFF.md` (current state and open work), then `docs/contract/` when you need intent.

## Rules that never bend
- The game folder is read-only. Extraction copies; repack writes a separate, marked patched copy;
  only runtime-capture agents may touch a game folder, and only through `core/capture/journal.py`.
- No DRM or anti-cheat circumvention. No password/key guessing: keys come from the user or from the
  game's own local files and are verified before use (D18). Capture is refused when anti-cheat or an
  online title is detected (`viwo/data/capture_policy.json`).
- Secrets and found keys are never logged or written to disk (run records store `<secret>`).
- GPL/AGPL tools run only as separate processes, never imported.
- `tos_sensitive` plugins (Overwatch) are never auto-selected; real-game tests are the independent
  operator's job, not yours.
- Every write into a folder built from untrusted names goes through `contracts.workspace.safe_member`
  and `contracts.workspace.inside` (traversal, drive letters, links).

## Commands (Windows, PowerShell)
```powershell
py -3.13 -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[unity,sevenzip,renpy,dev]"
ruff format viwo tests tools packaging; ruff check viwo tests tools packaging
python tools/loc_count.py --report          # caps: run AFTER ruff format
python -m unittest discover -s tests -t .    # ~110 tests, ~30 s; real-tool tests need VIWO_L5=1
viwo serve                                   # web UI, opens the browser
viwo config check startup.ini distros/*.ini  # strict config validation
```
Always run format, lint, caps and the full test suite before committing.

## Code size caps (enforced by tools/loc_count.py and a test)
Non-blank, non-comment lines: function 40, class 200, file 250 (contracts 150, tests 400),
params 6, line length 100, JS file 300. Package budgets are in `loc_caps.ini`; raise one only with
a reason in the comment next to it. Split functions rather than bending the caps.

## CI policy (owner's rule: GitHub Actions minutes cost money)
- CI runs only for major release tags (`vN.0.0`) or when the owner starts it by hand.
- Never dispatch workflows yourself unless the owner asks for that specific run. Test locally.
- `release.yml` (manual, one Windows job) builds wheel + sdist + the portable `viwo.exe` bundle
  and publishes the GitHub release. Run it only when the owner asks to ship.

## Windows gotchas
- Store relative paths in JSON/provenance with `.as_posix()`; compare paths with `Path`, not strings.
- Close every file and mmap (use `with`); UnityPy holds handles until `gc.collect()`. Open handles
  lock files on Windows and break later moves/deletes.
- Tests that fake external tools write a `.py` script plus a `.cmd` wrapper on Windows; follow the
  pattern in `tests/test_godot.py` (`fake_tools`). Use `\r\n` (not `\\r\\n`) in those wrappers.
- `bash` steps in workflows on Windows run in Git Bash: convert paths with `cygpath -w` before
  handing them to Python.

## Layout cheat sheet
- `viwo/contracts/` interfaces only · `viwo/os/` OS layer · `viwo/core/` pipeline, wiring
  (ini + distros), carve, decode, roundtrip, sanitizer, survey, capture, curation, merger
- `viwo/plugins/<engine>/` one folder per engine · `viwo/api/` server · `viwo/web/` UI
- `distros/` generated configs (`viwo config generate`; a test guards against drift)
- `packaging/` frozen build (`build_portable.py`, `viwo_entry.py`)
