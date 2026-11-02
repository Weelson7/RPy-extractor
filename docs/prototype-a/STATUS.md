# Prototype A: status (closed)

Branch `makeover`. Contract: `docs/contract/`. This file records what Prototype A delivered,
where it deviates from the contract and why, and the evidence for the exit check.

## Roadmap M0–M6

| M | Scope | Status |
|---|-------|--------|
| M0 | decisions closed (D0–D20), docs renamed (OS layer, ViWo) | done |
| M1 | v1 hotfix (merged); LoC counter + caps; CI on Linux and Windows | done |
| M2 | `viwo/contracts`, `viwo/os` (process tree-kill, tool locator, filename rules, pickers) | done |
| M3 | ini wiring, slot binder with failover, stage runner, workspace ownership + lock, jobs, run records, envelope, CLI, `generic` plugin, zip/tar/7z/rar/py7zr backends | done |
| M4 | `renpy`: safe RPA reader (main), unrpa subprocess (spare) | done |
| M5 | `unity`: UnityPy (main), AssetStudioModCLI (spare), cache roots opt-in | done |
| M6 | `godot`: PCK identify, embedded-PCK carving, GDRE Tools (main), GodotPckTool (spare) | done |
| A+ | v1 removed: web server, curation, merger and UI rebuilt inside `viwo/` | done |

## Layout

```
pyproject.toml     package "viwo", Python >= 3.11, console script `viwo`
startup.ini        startup wiring: plugins, slots, tools, [server]
loc_caps.ini       code size caps; tools/loc_count.py enforces them (CI L0)
viwo/contracts/    interfaces + value types (stdlib only)
viwo/os/           LinuxOS, WindowsOS
viwo/core/         wiring, pipeline (+ game-folder guard), workspace, jobs, curation, merger
viwo/backends/     core unpackers (zip, tar, 7z, rar, py7zr)
viwo/plugins/      generic, renpy, unity, godot
viwo/api/          local HTTP server (token, JSON-only, Host check), handlers, job routes
viwo/web/          web UI (plain ES modules, no build step)
viwo/cli.py        info | slots | detect | extract | replay | unpack | serve
tests/             unittest suites L1–L6 (no extra test dependency)
```

The v1 application (`RPy-extractor/`) and its bridge are deleted; every feature runs on ViWo.

## Deviations from the contract

| # | Deviation | Reason | State |
|---|-----------|--------|-------|
| X1 | v1 server kept as front end during M3–M6 | keep the UI working while the core landed | **resolved**: server, curation and merger ported, v1 deleted |
| X2 | legacy code under a shrink-only ratchet | it predated the caps | **resolved**: legacy deleted, ratchet removed |
| X3 | three trash layouts pending | curation was legacy | **resolved**: `.trash/groups`, `.trash/items`, `.trash/merger`, with migration from the v1 layout |
| X4 | no `unpack` CLI command | — | **resolved**: `viwo unpack`, plus `viwo replay` |
| X5 | `[tools]` keyed by dependency id, not backend id | one tool serves several backends | kept; doc 9 updated |
| X6 | Unity games used `generic` until M5 | — | **resolved** by M5 |

## Notes

**Game integrity.** Files are copied from the game folder, never moved. A workspace or temp folder
inside the game folder is refused before anything is written. Every run snapshots the game folder
(path, size, mtime) before and after, and a difference becomes a `GAME FOLDER CHANGED` warning.
Unity file handles are released after each container group (Windows locks were found on CI).

**Archives are never forced open.** Recognized containers (by Godot trailer, suffix, or magic bytes
for extension-less files) are unpacked recursively up to depth 10. There is no password or key
guessing and no "try another format": an encrypted archive ends as `needs_key`, which never falls
through to the spare. 7-Zip is called with `-p` and unrar with `-p-`, so neither can prompt.

**Ren'Py.** RPA-2.0/3.0 with XOR key and prefixes. The pickled index may only reference
`_codecs.encode` and `bytes`; a malicious `__reduce__` payload is refused without running.
Other variants go to unrpa (GPL-3.0, subprocess).

**Unity.** Containers in one folder load together (cross-file references), falling back to
one-by-one. Signatures are searched in the first 4 KB. Cache / persistent-data roots are read only
with the `include_cache` option.

**Godot.** GDRE and GodotPckTool flags are verified against their sources and on CI with the real
binaries (standalone and embedded PCK). The key is a `secret` option and is masked in run records.

**Web UI.** Rebuilt from scratch in an original red terminal style: 01 EXTRACT, 02 WORKSPACE,
03 SORT, 04 JOBS, 05 SYSTEM, 06 MERGER. It went through three review rounds with screenshots
at 1440 and 1280 px. Small text meets WCAG AA contrast. Media previews stream with byte ranges.

**Security.** Per-start API token injected into the page, JSON-only POST, Host allow-list,
contained static and preview paths, curation group names restricted to one plain folder name.

## Exit check (doc 14.4)

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Ren'Py, Unity, Godot fixtures extract via CLI and HTTP on Linux and Windows CI; game folder unchanged | yes; Godot tests use cross-platform fake tools, so they run on Windows too |
| 2 | Failover with fakes; L5 with real tools | fakes: all availability cases and outcome kinds. Real tools green on CI (run 41419317713): 7-Zip, unrar, py7zr, unrpa, UnityPy, AssetStudioModCLI, GDRE Tools, GodotPckTool, ffmpeg |
| 3 | Web UI covers the v1 workflows; differences listed | yes: extract, workspace groups and trash, sort with undo, merger, jobs, system; differences below |
| 4 | Re-run gives an identical workspace | yes (names + hashes); `viwo replay <run record>` reproduces a run |
| 5 | Product LoC within budget; boots on native runners | ~4,000 / 5,500 Python LoC, web 2,2xx / 2,400; Linux and Windows |

**Open, by decision:** a check on a real commercial game (D20) happens after Prototype B. There is
no redistributable real Unity asset fixture yet.

**Intended differences from v1:**
1. Game files are copied, never moved.
2. A non-empty folder ViWo did not create is never cleared.
3. Re-extracting into an existing workspace asks: replace / new / cancel.
4. Unity exports use the per-extension layout; v1's meaningless Unity-only keys are gone.
5. Duplicates are recognized by content hash, not by modification time.
6. Workspaces carry `.viwo-workspace` and `.extraction_metadata/` (provenance, run records).
7. Dependencies are reported per slot; nothing is installed at startup.
8. The API needs the per-start token; the UI sends it automatically.

## Next: Prototype B (doc 16)

M7 Unreal (repak/retoc; user AES key first, otherwise key finder with candidates verified against
the pak index), M8 custom plugins (Doom WAD with Freedoom on CI; Overwatch, operator-tested),
M9 round trip into a patched game copy for all four engines, M10 mixed mode + sanitizer phase 1,
M11 runtime capture pilot.
