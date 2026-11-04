# Contributing to ViWo

ViWo is a community tool under the MIT license. Read the **Philosophy** section of the README
first: it is the reference for what the tool is, who it is for, and why it has no policy
boundaries in its code. Contributions that add boundaries, judge users or purposes, or author
borderline code (DRM defeat, key brute force, anti-cheat evasion) do not fit; those things stay
third-party, pinned like everything else, under the disclaimer.

Four kinds of contribution, from the most valuable to the most involved:

## 1. An index entry (knowledge about one game)

Indexes live in `indexes/games/<slug>/<game-version>/index.json`, laid out as the future
`vidya_wormhole_indexes` repository (`docs/indexes.md`). One entry says how to recognize a game,
which engine plugin and options it needs, which pinned tools, and which QuickBMS scripts.

1. Read `indexes/SCHEMA.md`. Copy a neighbouring entry (`freedoom`, `skyrim-se`).
2. `slug`: lowercase, digits and dashes. `game_version`: `any` or a real version string.
3. `detect`: relative paths or globs that exist in every install of that game version.
4. `options`: never secrets (keys named `*key*`, `*secret*`, `*password*` are rejected).
5. `tools`: dependency ids from `viwo/data/tools.json`; `scripts`: see 2 below.
6. Validate: `python indexes/tools/validate.py`. Try it: `viwo install --game <slug>`.
7. `source`: where the knowledge comes from (a wiki page, a forum thread, your own analysis).

## 2. A QuickBMS script

Scripts are community data, pinned by checksum, never copied into this repository unless their
license allows it. In an index entry:

```json
{"name": "dat.bms", "url": "https://.../dat.bms", "sha256": "<64 hex>", "size": 1234}
```

- HTTPS only. `name` is `<ext>.bms` (or `<ext>.<anything>.bms`): the extension it opens.
- Compute `sha256` and `size` from the exact file you tested. A changed file is refused.
- Say in `license` which license the script carries, and in `source` who wrote it.
- A script that already exists in the user's scripts folder with another checksum is never
  replaced.

## 3. A tool pin (a new third-party tool, or a version bump)

`viwo/data/tools.json` pins every tool: `version`, `license`, optional `on_demand` (installed only
when asked by name), and per OS the `url` (HTTPS only), `size`, `sha256`, `kind` (`zip`, `tar`,
`gz`, `raw`, `msi`, `sfx`), `find` (the file to run), optional `argv` (`{path}`, `{dotnet}`,
`{java}`), `needs`, `from`, `mkdir`. Python packages go under `python` (a pip requirement) or,
when ViWo must never import them (GPL code), under `workers` with a script in
`viwo/data/workers/` (contract doc 10). Rules:

- Compute size and sha256 from the real asset you downloaded and ran. Never pin without both.
- Official releases only (the tool's own GitHub releases or its author's HTTPS site).
- GPL/AGPL tools run as separate processes (`isolation = "subprocess"` on the backend).
- Nothing may ask the user anything: no installer, no elevation; pre-answer first-run dialogs.
- Bump `version` together with its checksum, then `python tools/notices.py` and run
  `VIWO_L5=1 python -m unittest tests.test_thirdparty` once with network access. A Python pin
  also needs its hash locks: `python tools/pin_python.py` (writes `viwo/data/locks/`).

## 4. Code (a plugin, a backend, a fix)

- Python 3.11+, stdlib first. Start with `ARCHITECTURE.md`, then `docs/contract/`.
- An engine plugin is one folder under `viwo/plugins/<engine>/` implementing
  `viwo/contracts/plugin.py` (`EnginePlugin` with a `PluginManifest`, `detect`, slot definitions
  and backends); it is found by scanning, no list to edit. Plugins never import each other or
  the core. Out-of-tree plugins are drop-ins with a `plugin.json` (`docs/plugins.md`). After
  adding or changing slots, run `viwo config generate`.
- Caps are enforced (`loc_caps.ini`, `tools/loc_count.py`): function 40 lines, class 200,
  file 250, params 6, line length 100, JS file 300. Split functions rather than bending them.
- Tests: synthetic fixtures only (nothing from a commercial game); real-tool tests behind
  `VIWO_L5=1`. Fake external tools follow `tests/test_godot.py`.
- Before every commit: `ruff format`, `ruff check`, `python tools/loc_count.py`,
  `python -m unittest discover -s tests -t .`.
- Commit only through `python tools/version.py commit -m "..." [--feature|--major]`: it runs
  the checks, bumps `va.b.c` (c every commit, b per feature, a per finished roadmap), commits
  and tags. A pre-commit hook refuses anything else. Never put model names in commit messages.
- CI runs only on `vN.0.0` tags or by hand (it costs the owner money). Test locally.
- Update the docs with the change: they describe the current state only (`docs/contract/`,
  `docs/contract/CONFORMANCE.md`); history goes into `CHANGELOG.md`.

## Reporting

- Bugs: `viwo diag` writes a zip (logs, run records, tool status, secrets stripped); attach it
  to the bug report template.
- Game requests go through the "game / index request" template; tool requests through "tool
  request".

Be precise, be kind, and remember that every tool here is used by people you will never meet.
