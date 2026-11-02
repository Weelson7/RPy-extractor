# Handoff (cloud session -> VS Code on Windows)

Branch `makeover`, version 0.2.0. Prototype A and Prototype B are delivered; see
`docs/prototype-a/STATUS.md` and `docs/prototype-b/STATUS.md` (evidence and not-yet-verified list).
Read `CLAUDE.md` first: rules, commands, caps, CI policy.

## State at handoff
- Local suite: about 112 tests, all passing except the size-cap test while the last UI polish
  round was in flight (see "Open work 1"). Last full CI run (Linux + Windows, real tools): green on
  8114af1. CI now runs only on `vN.0.0` tags or by hand.
- Coverage ladder done: engine plugins (Ren'Py, Unity, Godot, Unreal, Doom, RPG Maker, KiriKiri,
  Electron, Source, Bethesda, Overwatch, QuickBMS bridge) -> unpackers -> carver -> zlib/gzip
  streams -> decoders (vgmstream/ffmpeg) -> runtime capture pilot (RenderDoc).
- Tools: `survey`, `sanitize` (+undo), `repack` (verified patched copy), `capture`, `config`.
- Web UI: 9 views (extract, workspace, sort, jobs, system, merger, survey, cleanup, patched copy).
- Release packaging ready but never run on Windows: `.github/workflows/release.yml`,
  `packaging/build_portable.py` (verified building and smoke-testing on Linux only).

## Open work, in priority order
1. **UI polish round.** An agent was polishing all views (consistency, wording, error states,
   1024 px layout, a11y) and recording/reviewing animations. If its changes are not committed,
   check `git status`: run caps + tests; the web budget in `loc_caps.ini` may need raising to
   at most 3600 with a reason. If the tree is clean, it landed.
2. **Ship the release packages, built on Windows (locally, not on CI).**
   ```powershell
   pip install pyinstaller==6.22.3 build==1.3.0
   python packaging/build_portable.py --out dist     # builds dist\viwo\ and smoke-tests viwo.exe
   python -m build --outdir release                  # wheel + sdist
   Compress-Archive dist\viwo release\ViWo-0.2.0-windows-x64.zip
   ```
   Then publish with `gh release create v0.2.0 release\* --target makeover --title "ViWo 0.2.0"
   --notes-file docs/release-notes.md` (needs `gh auth login`). The same steps exist as the
   manual `release.yml` workflow; use it only if the owner asks. Watch for: PyInstaller
   collecting UnityPy's native libs (fmod, texture decoders), tkinter in the bundle (folder
   pickers), and the smoke test's `viwo.exe -m unrpa`. The bundle was verified on Linux only.
3. **Remaining code-review findings** (the rest are fixed in 38b4a14):
   - `core/capture/journal.py`: write `journal.json` atomically (temp + `os.replace`); tolerate a
     corrupt journal with a clear error instead of blocking every capture; remove directories
     that `write` created on restore; build restore paths with `joinpath(*PurePosixPath(rel).parts)`.
   - Cancellation and locking: pass the job's cancel token into `survey()` and `count_embedded`
     (`api/handlers_tools.py`, `core/survey.py`); lock the repack target folder too
     (`core/roundtrip.py` `_prepare`); read `app.workspace` once per handler; consider a
     cross-process lock file so the CLI and the server cannot write one workspace together.
   - Provenance after renames: the sanitizer and SORT rename/move files without updating
     `.extraction_metadata/provenance.jsonl`; the round trip now reports those files as
     "moved, renamed or trashed" instead of writing them back. Add a provenance rewrite helper
     and call it from `core/sanitizer.py` and `core/curation/sorting.py`.
   - Small: validate DataTool `modes` (`^[a-z-]+$`, `plugins/overwatch`); the AES key passed to
     repak/retoc is visible in the process list (prefer a temp key file if the tools allow it).
4. **Not verified on real data** (needs the owner or the operator): Unity repack on a real
   bundle, RenderDoc capture/harvest, QuickBMS flags, DataTool on a real install, retoc on real
   UE5 IoStore, real commercial games end to end (D20).

## Local test checklist (Windows)
1. `pip install -e ".[unity,sevenzip,renpy,dev]"`, then `viwo` (prints the guide) and `viwo slots`.
2. Install the optional tools you need (README table) or set `[tools]` in `startup.ini`;
   `viwo config check startup.ini` must say OK.
3. `viwo serve` -> 07 SURVEY on your games folder -> 01 EXTRACT a few games of different engines.
4. 02 WORKSPACE / 03 SORT / 08 CLEANUP (apply, then UNDO) on one workspace.
5. Edit a file in a workspace with any editor -> 09 PATCHED COPY -> PLAN -> BUILD; run the game from
   the copy; the original folder must be unchanged (the result card says UNTOUCHED).
6. Report anything odd with the run record from `<workspace>/.extraction_metadata/runs/`.

## Conventions
- Commit in batches; run format, lint, caps and tests first. Never put model names in commits.
- Keep `docs/prototype-b/STATUS.md` honest: move items out of "not verified" only with evidence.
- `viwo config generate` after changing plugins or slots, or the drift test fails.
