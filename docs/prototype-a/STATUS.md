# Prototype A: implementation status

Unattended run started 2026-11-02 on branch `makeover`. Contract: `docs/contract/`.
This file is the running log: plan, progress, and every deviation from the
contract with its reason.

## Plan (roadmap M0–M6)

| M | Scope in this run | Status |
|---|-------------------|--------|
| M0 | decisions closed, docs renamed (OS layer, ViWo) | done |
| M1 | hotfix (merged); LoC counter + caps file; CI workflow (Linux + Windows); v1 result-shape checks | done |
| M2 | `viwo/contracts`, `viwo/os` (process with tree-kill, tool locator, fs rules) for Linux + Windows; conformance tests | done |
| M3 | flat startup ini; slot binder (failover); stage runner (probe, detect, select, identify/carve, unpack, collect copy/move, provenance, verify, report); workspace ownership + lock; jobs + run records + envelope; CLI `info/detect/extract/slots/serve`; v1 server delegates extraction to the core; `generic` plugin; zip/tar/7z/rar/py7zr backends | done (see notes) |
| M4 | `renpy` plugin: safe RPA reader (main) + unrpa subprocess (spare) | done |
| M5 | `unity` plugin: UnityPy (main) / AssetStudioModCLI (spare) | done |
| M6 | `godot` plugin: PCK identify + carving of embedded PCKs, GDRE (main) / GodotPckTool (spare) | done |

## Layout

```
pyproject.toml            package "viwo", Python >= 3.11, console script `viwo`
startup.ini               default startup wiring (doc 9, flat form)
loc_caps.ini              LoC caps (doc 15); tools/loc_count.py enforces them
viwo/contracts/           interfaces + value types (stdlib only)
viwo/os/                  LinuxOS, WindowsOS
viwo/core/                wiring (ini, registry, binder), pipeline, workspace, jobs
viwo/backends/            core-owned backends (zip, tar, 7z, rar, py7zr)
viwo/plugins/             generic, renpy, unity, godot
viwo/cli.py               CLI
tests/                    unittest suites (no extra test dependency)
RPy-extractor/            the v1 app ("legacy"), still serving the web UI
```

## Deviations from the contract (with reasons)

| # | Deviation | Reason | Planned resolution |
|---|-----------|--------|--------------------|
| X1 | The v1 web server (`RPy-extractor/extract.py`) stays the HTTP front end. Only extraction (and dependency status) is delegated to the ViWo core; sorting, trash and the merger stay legacy code | Porting curation and merger (~1,400 legacy LoC) is not needed to prove the contract, and keeping them keeps the UI working | port to `viwo/core/workspace` + `viwo/core/merger` after Prototype A |
| X2 | LoC caps apply to `viwo/` (product) and `tests/`; `RPy-extractor/` is legacy under a **ratchet** (may only shrink) | the legacy code predates the caps | shrinks as code is ported |
| X3 | Three trash layouts (doc 4.3) not yet applied | curation is still legacy (X1) | with the curation port |
| X4 | No separate `unpack` CLI command yet | `extract` covers it; the unpack loop takes explicit files so the command is a thin addition | next CLI pass |
| X5 | `[tools]` in the ini is keyed by **dependency id** (e.g. `sevenzip`), not backend id as doc 9 said | one tool can serve several backends (7-Zip serves zip/tar/7z/rar spares) | done: doc 9 updated |
| X6 | Legacy extraction code (`extraction_types/`, `extraction_core/archive.py`, `pipeline.py`) deleted; Unity games use the `generic` plugin until M5 lands | the v1 route now runs the ViWo core; keeping two pipelines would double the surface | M5 |

## Notes per milestone

**M3 (lean core).** v1 `/api/extract` and `/api/dependencies` now run through `viwo.api.legacy`.
Verified: 21 core tests + 10 legacy tests green; real-server UI check in Chromium: extract,
re-extract shows the decision dialog, "replace" succeeds. Legacy Python shrank 4,246 -> 2,430 LoC.

**M4 (Ren'Py).** Safe RPA reader for RPA-2.0/3.0 (XOR key, prefixes); the pickled index
may only reference `_codecs.encode` and `bytes`. A malicious `__reduce__` payload is refused
without running (test). unrpa (GPL-3.0) runs as a subprocess spare; L5 confirmed real unrpa
reads our RPA fixtures. Source root is `game/` only (v1 rule). RPA-1.0/3.2/ALT variants fall
through to the spare.

**M5 (Unity).** UnityPy export ported from v1 into small functions; outputs go to staging and are
collected into the per-extension layout (D3), so the v1 F1 wipe cannot happen. AssetStudioModCLI
is the spare (its exact CLI flags are from research, **not verified against the binary**: it is
not installable here). Detection fixes v1 F2 (case-insensitive markers; `*_Data` alone = 0.5).
Removed v1 placeholder "slices" and the always-passing completeness gate (F11). Tests use a fake
`UnityPy` module; L5 checks real UnityPy on a corrupt container. **Gap:** no real Unity asset
fixture yet (needs a redistributable sample; L7 manual check on a real game is pending).

**M6 (Godot).** PCKs are identified by the `GDPC` magic, and PCKs embedded in executables by the
`GDPC` trailer (size + magic), then carved out before unpacking. GDRE Tools is main
(`--headless --extract= --output= [--key=]`), GodotPckTool spare. The encryption key is a
`secret` plugin option: "needs key" outcomes do not fall through to the spare (it cannot
decrypt). **Not verified against the real binaries:** the exact GDRE/GodotPckTool flags
(tools not installable here), and whether carved PCKs from Godot 3 executables keep valid
offsets. Tests use fake CLI tools (POSIX only; skipped on Windows CI).

**Mixed mode (pulled forward from M10, small).** Pairwise runs over generic/renpy/unity/godot
on one mixed fixture: every run selects exactly the requested set, the game folder is
unchanged, results are deterministic.

## Prototype A exit check (doc 14.4)

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Ren'Py, Unity, Godot fixtures extract via CLI and HTTP on Linux and Windows CI; game folder unchanged | **Linux: yes. Windows: yes for generic/Ren'Py/Unity**; the Godot and mixed pipeline tests use POSIX fake tools and are skipped on Windows (identification/carving tests do run there) |
| 2 | Failover cases with fakes; L5 with real tools | fakes: all four availability cases + outcome kinds; real tools verified locally: **unrpa, py7zr, UnityPy**. Not verified (not installable here): 7-Zip CLI, unrar, AssetStudioModCLI, GDRE Tools, GodotPckTool; the nightly CI job installs 7-Zip on Linux |
| 3 | v1 web UI works; intended differences listed | real-server Chromium check: extract, re-extract dialog, replace. Differences listed below |
| 4 | Re-run gives an identical workspace | yes (names + hashes) for a re-run of the same request. A `viwo replay <run record>` command does not exist yet |
| 5 | Product LoC <= 5,500; ini boots on the native runner | **2,339 LoC**; boots on Linux and Windows runners |

**Intended differences from v1** (golden behavior changes, all deliberate):
1. Files are **copied** from the game folder, never moved (v1 moved them: H1).
2. A non-empty folder that ViWo did not create is never cleared; extraction into it is refused (H2).
3. Re-extracting into an existing workspace asks: replace / new / cancel (v1 silently wiped it).
4. Unity exports land in the per-extension layout (`png/`, `wav/`, `txt/`, `obj/`) instead of `images/`, `audio/`...; v1's Unity-only result keys (`discoveredCount`, `qualityGatePass`...) are gone (they were meaningless: F11).
5. Duplicate files are recognized by content hash, not by modification time (F6).
6. Workspaces contain `.viwo-workspace` and `.extraction_metadata/` (provenance + run records); dot-folders are hidden from step 3, sorting and the merger.
7. `/api/dependencies` lists backend dependencies per owner plugin; unrpa is no longer required at startup, and no packages are installed at boot.
8. The API needs the per-start token (hotfix H3); the UI sends it automatically.

## Next (after Prototype A)

- Port curation (sorting, trash with the three layouts) and the media merger into `viwo/core` (X1, X3).
- `viwo replay`, `viwo unpack`, HTTP job routes (`/api/jobs/...`), `/api/plugins`, `/api/detect`.
- Real-binary L5 checks for GDRE Tools, GodotPckTool, AssetStudioModCLI, 7-Zip, unrar (tool lock file).
- Prototype B (doc 16): Unreal unpack, custom plugins, round trip, sanitizer phase 1, capture pilot.
