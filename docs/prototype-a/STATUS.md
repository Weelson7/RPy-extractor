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
| M4 | `renpy` plugin: safe RPA reader (main) + unrpa subprocess (spare) | todo |
| M5 | `unity` plugin: UnityPy (main) / AssetStudioModCLI (spare) | todo |
| M6 | `godot` plugin: PCK identify + carving of embedded PCKs, GDRE (main) / GodotPckTool (spare) | todo |

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
| X5 | `[tools]` in the ini is keyed by **dependency id** (e.g. `sevenzip`), not backend id as doc 9 said | one tool can serve several backends (7-Zip serves zip/tar/7z/rar spares) | doc 9 updated at the end of the run |
| X6 | Legacy extraction code (`extraction_types/`, `extraction_core/archive.py`, `pipeline.py`) deleted; Unity games use the `generic` plugin until M5 lands | the v1 route now runs the ViWo core; keeping two pipelines would double the surface | M5 |

## Notes per milestone

**M3 (lean core).** v1 `/api/extract` and `/api/dependencies` now run through `viwo.api.legacy`.
Verified: 21 core tests + 10 legacy tests green; real-server UI check in Chromium: extract,
re-extract shows the decision dialog, "replace" succeeds. Legacy Python shrank 4,246 -> 2,430 LoC.
