# 15. Code size caps (strict, non-blank, non-comment lines)

Normative for 1.1, enforced by `tools/loc_count.py` (reads `loc_caps.ini` through
`tools/caps_ini.py`) as an L0 gate (`tests/test_pipeline.py::test_loc_caps`). **History:**
draft 3 (2026-11-02) set the numbers from a measurement of v1 and the prototype scope; the
budgets below are the ones in force after the 1.0 and 1.1 scope the owner approved.

## 15.1 What counts (counting rules)

1. **Format first, then count.** Code is formatted with `ruff format` (line length **100**) before counting. Long lines, `;`-joined statements and packed one-liners cannot dodge the caps; a line over 100 characters is itself a cap failure.
2. **Python:** a line counts if it holds any token other than comments, blank lines and indentation. The counter uses `tokenize`, not regexes. Multi-line strings count on every line, **except docstrings** (the first string of a module, class or function), which are excluded so documentation is not discouraged.
3. **JS / CSS / HTML:** non-blank lines that are not purely `//`, `/* */` or `<!-- -->` comments.
4. **Other glue languages:** none exist (the CUE4Parse wrapper is deferred, doc 13); the rule for them stays "non-blank, non-comment lines".
5. **Counted trees:** `viwo/` (product), `tests/` (test caps and the floor), `tools/` (its own budget). **Excluded:** `third_party/`, `indexes/`, `examples/`, `sqc/fixtures/`, `packaging/`, docs and data files. Generated code does not exist yet; when it does, it is marked generated and listed in the caps file as excluded.
6. The counter is split in two small modules: `tools/loc_count.py` (counting and checks) at most **120** counted lines and `tools/caps_ini.py` (caps-file schema, exceptions, expiry) at most **120**; both live under the `tools` budget.

## 15.2 v1 baseline (measured 2026-11-02)

| Scope | Counted LoC |
|-------|-------------|
| Python, all of `RPy-extractor/` | **4,395** (4,144 without docstrings) |
| Largest files | `media_merger/service.py` 517 · `extract.py` 384 · `api/sorting_handlers.py` 356 · `unity/discovery.py` 285 · `api/media_merger_handlers.py` 283 · `startup.py` 271 · `sorting.py` 251 |
| Largest functions (approximate spans) | `build_media_merger_output` ~172 · `build_merged_video` ~164 · `export_unitypy_assets` ~133 · `UnityExtractor.extract` ~118 · `startup_dependency_preflight` ~101 · `extract_assets` ~100 |
| Web | `app.js` 1,879 · `styles.css` 1,030 · `index.html` 288 |

v1 was removed in prototype A; the baseline is kept as the reference the caps were set against.

## 15.3 Product caps (Python, excluding tests)

**Granularity caps** (hard; the L0 gate fails):

| Unit | Cap |
|------|-----|
| Function or method | **40** |
| Class | **200** |
| File (module) | **250** |
| File in `contracts/` | **150** |
| Function parameters | **6** (more → a dataclass or spec object); not applied to tests |
| Line length | **100** |

**Package budgets** (hard total per prefix; the split inside is free). The budgets live in
`loc_caps.ini [budgets]` as path prefixes, coarser than draft 3's per-subpackage table so that
moving code between `core/pipeline`, `core/wiring` and friends needs no budget edit:

| Prefix | Budget | Notes |
|--------|--------|-------|
| `viwo` (whole product) | 10,800 | this line **is** the hard ceiling (draft 3 said 10,000). 1.0/1.1 (installer, indexes, capture and settings views, add-ons, diagnostics) and 1.2 (contract types, conformance kit, `media.probe` and `image.convert` slots, run-record context, `slots --check`) raised it with the owner's approval, reasons on the line |
| `viwo/contracts` | 900 | interfaces + value types only |
| `viwo/os` | 900 | both OS layers and their shared base |
| `viwo/core` | 5,400 | pipeline, wiring, jobs, workspace, curation, merger, sanitizer, carve, decode, capture, round trip, survey, installer, indexes, diagnostics |
| `viwo/backends` | 600 | core-owned backends |
| each built-in plugin (`viwo/plugins/<id>`) | 100-700 | one line per plugin: generic 100, unity 700, renpy/godot/unreal 500, the rest 200-300 |
| `viwo/cli.py` | 400 | `cli_extra.py` and `cli_format.py` count under `viwo` |
| `tools` | 600 | counter, caps reader, version tool, notices, games runner, coverage check |

`viwo/api` has no separate line: it is bounded by the product total. Every raise carries its
reason as an inline comment on the budget line.

**Web** (`loc_caps.ini [web]`): every JS module at most **300** counted lines; `viwo/web` total
5,400 (js + css + html). The v1 ratchets (`app.js`, `styles.css`, `index.html`) ended when v1
was removed; nothing is ratcheted today.

## 15.4 Test caps

| Unit | Cap |
|------|-----|
| Test file | 400 |
| Test function | 60 |
| Fixture builders and fake tools | live inside the test files under the same caps |

Tests have no total budget. Instead, a **floor**, enforced by the counter: test LoC ≥ 0.6 ×
(`viwo/contracts` + `viwo/core`). 1.1 measures about 0.9.

## 15.5 Exceptions and raises

- They live in `loc_caps.ini`:

  ```ini
  [exceptions]
  ; path = cap | reason | expires at vX.Y  (or a milestone name, reviewed at that milestone)
  viwo/core/merger/filtergraph.py = 300 | ffmpeg graph builder; split planned | expires at v1.3
  ```
  An exception raises the **file cap** of that exact path. At most **3 active exceptions** at a time; one whose version has been reached (compared with `viwo.__version__`) fails the L0 gate until it is removed or renewed; a milestone-named expiry is reviewed at that milestone.
- The caps file itself is validated: unknown sections or keys, non-integer values, a malformed exception line or a missing cap are L0 failures (`tests/test_l0_static.py`).
- Ratchets: none since v1 was removed; the `[web]` and `[budgets]` numbers are hard caps.
- Raising a package budget is a contract change: the new value and its reason go on the budget line, and the reason on that line is the record. A commit whose point is the raise names the budget in its message; a raise that a feature needs ships with that feature's commit (the 1.2 raise did, unnamed: the reason is on the line).

## 15.6 Why these numbers

- **40 per function and 250 per file** are tight but workable for glue code. Orchestration code that does not fit is usually doing two jobs.
- The **total cap (10.8k since 1.2)** is about 2.5× v1, for: two OS layers, a core that is an actual framework, thirteen plugins, a CLI, jobs, sanitizer, capture, installer and indexes. The pressure stays on "wrap, don't reimplement".
- **Plugin budgets of 300-700** force plugins to stay glue. If a plugin needs more, the work probably belongs in an external tool or a shared core helper.
