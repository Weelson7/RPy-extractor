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

## Open work, in priority order (do all of it; afterwards only manual testing remains)

Owner's rules for this work: fully automated (no manual commands, no "go download this"),
every third-party tool lives under `third_party/`, CI only on major releases, commit in batches.

1. **Startup installer: verify for real on Windows** (built, unit-tested with a local file URL,
   never run against the real downloads; the cloud session was not allowed to execute them).
   - `viwo/data/tools.json` pins 9 tools (repak, retoc, vgmstream, GDRE, GodotPckTool,
     AssetStudioModCLI, 7-Zip, ffmpeg, ffprobe) per OS with URL, size and sha256, plus 3 Python
     pins. `core/thirdparty.py` downloads, verifies, unpacks into `third_party/<id>/`; boot finds
     them (`found_tools`) and appends `third_party/python` to `sys.path`.
   - `core/preflight.py` + `POST /api/preflight` (job "preflight": check events per dependency,
     then installs everything missing when `auto_install = on`, the default) and
     `POST /api/preflight/install {id}`; the app reloads its bindings afterwards.
   - To do: run `viwo serve`, call the preflight, confirm each tool installs and binds
     (`viwo slots`). Watch: the 7-Zip MSI unpack (`msiexec /a`), the AssetStudioModCLI net10 build
     (may need the .NET 10 runtime: if so, fall back to the `net472_win32_64` asset on Windows and
     pin its checksum), ffmpeg `.gz` binaries, GDRE needing its `.pck` next to the exe.
   - Add a CLI `viwo install [--all|<id>]` (same code) and an `L5` test that installs into a temp
     home; add `lz4` (Skyrim SE BSA) to the Python pins.
   - **Required (owner): automate the four tools still missing** the same way (pinned version,
     size and sha256 in `viwo/data/tools.json`, installed into `third_party/<id>/`, no manual step):
     - `unrar`: RARLAB's official builds (rarlab.com; Windows `unrarw64.exe` is a self-extractor:
       unpack it with the bundled 7-Zip, `7z x`; Linux `rarlinux-x64-<ver>.tar.gz` contains `unrar`).
     - `quickbms`: the official QuickBMS zip (aluigi.altervista.org; the cloud session could not
       reach that host, so pin it from Windows), plus a pinned scripts pack into
       `third_party/quickbms/scripts`, set as the default `[options.quickbms] scripts`.
     - `datatool`: overtools/OWLib release or CI artifact (pin the newest tagged build; it is a
       .NET app, so include its runtime need in the check). The Overwatch plugin stays explicit-only.
     - `renderdoccmd` + `rdpython`: RenderDoc's official portable zip (renderdoc.org/builds,
       `RenderDoc_<ver>_64.zip` on Windows, `renderdoc_<ver>.tar.gz` on Linux); `rdpython` is the
       Python that can import its `renderdoc` module: install the matching embeddable Python into
       `third_party/rdpython/` and point the tool there.
     A new installer kind may be needed (`sfx`: run 7-Zip on a self-extracting exe). Compute every
     checksum from the real asset; never install without one. Hosts outside GitHub must be HTTPS.
   - `strict_preflight = on` is still reserved: implement it in `api/server.py serve()` as exit 4
     (doc 9) when an enabled plugin has no bound main backend after preflight.
2. **Landing animation (owner's request).** On page load, before the app, a full-screen landing
   driven by the real preflight job: logo, one line per check/install event as it arrives
   ("Checking repak... found v0.2.3", "Downloading repak.zip 1,200 / 1,975 KB"), a determinate bar
   from the "(i/N)" and "X / Y" counts (the progress component in `web/js/progress.js` already
   parses both), a summary ("12/17 tools ready, 5 installed"), then a smooth hand-off into
   01 EXTRACT. Hold it at least ~1.2 s so it never flashes; skip it on later navigations; respect
   reduced motion. 05 SYSTEM: an INSTALL button per missing installable tool and "INSTALL ALL"
   (POST /api/preflight/install, progress via the job events), and a re-check button.
   Keep `viwo/web` within its budget (raise in `loc_caps.ini` with a reason if needed).
3. **Manual check suite `sqc/`** (owner's request; only `sqc/fixtures/build_fixtures.py` exists).
   Write one file per area with very precise checks (ID `SQC-<AREA>-<NN>`, priority P0/P1/P2,
   preconditions, fixture recipe, numbered steps with exact commands or UI paths and labels,
   exact expected results, cleanup, result table): 00-README (setup, P0 smoke subset),
   01 install + first run (+ startup installer and landing), 02 dependencies, 03 detection +
   survey, 04 extraction per engine (every plugin, encrypted/needs-key cases, nested archives),
   05 modes and options, 06 game integrity and safety, 07 workspace/sort/trash, 08 cleanup,
   09 round trip, 10 merger, 11 capture, 12 UI/UX (all views at 1920/1440/1280/1024, every error
   code, keyboard, reduced motion, progress honesty), 13 CLI, 14 security, 15 release package.
   Mark operator-only checks (Overwatch) as OPERATOR.
4. **Remaining code-review items:** capture journal atomic write + corrupt-journal handling +
   created-dir cleanup (`core/capture/journal.py`); cancel token through `survey()` and
   `count_embedded`; lock the repack target folder; read `app.workspace` once per handler; a
   cross-process workspace lock file; provenance rewrite when the sanitizer or SORT renames or
   moves files; validate DataTool `modes`; avoid the AES key on tool command lines if possible.
5. **Progress honesty gaps left:** collect has no total (send "Collecting N files" first so the
   bar is determinate); single long external-tool runs report nothing until done (stream their
   stdout lines as events where the tool prints progress, e.g. repak/retoc verbose output).
6. **Release (on Windows, locally):**
   ```powershell
   pip install pyinstaller==6.22.3 build==1.3.0
   python packaging/build_portable.py --out dist     # builds dist\viwo\ and smoke-tests viwo.exe
   python -m build --outdir release                  # wheel + sdist
   Compress-Archive dist\viwo release\ViWo-0.2.0-windows-x64.zip
   gh release create v0.2.0 release\* --target makeover --title "ViWo 0.2.0" --notes-file docs/release-notes.md
   ```
   The portable bundle must include `viwo/data/tools.json`; `third_party/` is created next to
   `viwo.exe` on first start. Watch PyInstaller collecting UnityPy's native libs and tkinter.
7. **Production-grade checklist** before calling it done: everything above, `docs/prototype-b/
   STATUS.md` updated with evidence, README updated (installer replaces the manual tool table),
   all tests + caps green locally on Windows, one manual CI run (owner starts it) green, then the
   `sqc/` P0 subset passed by hand. After that, only the full manual `sqc/` pass remains.

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
