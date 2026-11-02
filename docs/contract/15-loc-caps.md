# 15. Code size caps (strict, non-blank, non-comment lines)

Proposal. The numbers are set from a measurement of v1 (15.2) and the
prototype scope (doc 14). They are meant to be **enforced by CI**, not
treated as guidelines. Every number is open to discussion before it's locked.

## 15.1 What counts (counting rules)

To keep the count objective and hard to game:

1. **Format first, then count.** Code is formatted with a pinned formatter (proposed: `ruff format`, line length **100**) before counting. Long lines, `;`-joined statements and packed one-liners can't be used to dodge the caps.
2. **Python:** a line counts if it holds any token other than comments, blank lines and indentation. The counter uses `tokenize`, not regexes. Multi-line strings count on every line, **except docstrings** (the first string of a module, class or function), which are excluded so documentation isn't discouraged ❓.
3. **JS / CSS / HTML:** non-blank lines that aren't purely `//`, `/* */` or `<!-- -->` comments.
4. **Other glue languages** (C# for the CUE4Parse wrapper and the Unity dump plugin): non-blank lines that aren't purely comments.
5. **Excluded from the product count:** `third_party/` (vendored), generated code (for example Kaitai output, which must be marked as generated and listed in the caps file), fixtures data, docs. Tests have their own caps (15.4).
6. One counter, in the repository, at most **120 counted lines** itself, run as an L0 test gate (doc 17).

## 15.2 v1 baseline (measured 2026-11-02)

| Scope | Counted LoC |
|-------|-------------|
| Python, all of `RPy-extractor/` | **4,395** (4,144 without docstrings) |
| Largest files | `media_merger/service.py` 517 · `extract.py` 384 · `api/sorting_handlers.py` 356 · `unity/discovery.py` 285 · `api/media_merger_handlers.py` 283 · `startup.py` 271 · `sorting.py` 251 |
| Largest functions (approximate spans) | `build_media_merger_output` ~172 · `build_merged_video` ~164 · `export_unitypy_assets` ~133 · `UnityExtractor.extract` ~118 · `startup_dependency_preflight` ~101 · `extract_assets` ~100 |
| Web | `app.js` 1,879 · `styles.css` 1,030 · `index.html` 288 |

So v1 already breaks the per-file and per-function caps below in several
places. Under the caps, the migration has to **split** these files and
functions, not copy them.

## 15.3 Product caps (Python, excluding tests)

**Granularity caps** (hard; CI fails):

| Unit | Cap |
|------|-----|
| Function or method | **40** |
| Class | **200** |
| File (module) | **250** |
| File in `contracts/` | **150** |
| Function parameters | **6** (more → a dataclass or spec object) |

**Package budgets** (hard total per package; the split inside is free):

| Package | Budget | Notes |
|---------|--------|-------|
| `contracts/` | 900 | interfaces + value types only; the scratchpad draft was about 850 |
| `kernels/_shared` | 300 | the common base of both kernels |
| `kernels/linux` | 500 | |
| `kernels/windows` | 500 | |
| `core/pipeline` (stages, identify/carve, unpack loop, collect) | 900 | replaces v1 `extraction_core` (≈440) + orchestration |
| `core/wiring` (ini, boot, registries, slot binder) | 700 | new |
| `core/jobs` (runner, events, run records) | 350 | new |
| `core/workspace` (layout, curation: sorting, groups, trash, undo) | 800 | replaces v1 `sorting.py` + sorting handler logic (≈600) |
| `core/merger` | 650 | v1 ≈800 across service + handlers; must shrink |
| `core/sanitizer` (runner + phase 1 rules) | 400 | |
| `core/capture` (policy, journal, diff) | 400 | S7 |
| `api/` | 700 | thin adapters; v1 `extract.py` + `api/` ≈1,550, so most of that logic moves to core |
| `cli/` | 400 | |
| `backends/` (core-owned backends) | 1,200 | ≤ **150** per backend |
| each built-in plugin (`renpy`, `godot`, `unreal`), including its backends | 500 | |
| `plugins/unity`, including its backends | 700 | v1 Unity is ≈1,000. The placeholder "slices" and the meaningless completeness ratio get cut (doc 0.4) |
| `plugins/overwatch` (custom showcase) | 300 | |
| **Total Python product, hard cap** | **10,000** | |
| **Prototype target** (end of the roadmap's M9) | **≤ 8,000** | |

**Other languages:**

| Item | Cap |
|------|-----|
| CUE4Parse .NET wrapper (C#), deferred | 400 |
| Unity runtime dump plugin (C#, S7+) | 300 |
| `web/app.js` | **ratchet at 1,879**: may only shrink. New UI goes in separate modules of ≤ 300 each |
| `web/styles.css` | ratchet at 1,030 |
| `web/index.html` | ratchet at 288 |
| Total new web code during the prototype | 900 |

## 15.4 Test caps

| Unit | Cap |
|------|-----|
| Test file | 400 |
| Test function | 60 |
| Fixture builder (makes a synthetic RPA, PCK, pak…) | 150 each |
| Fake backend or fake kernel | 120 each |

Tests have no total budget. Instead, a **floor**: test LoC should be at least
0.6 × product LoC for `contracts/` + `core/`.

## 15.5 Exceptions

- They live in `loc_caps.ini` (the same ini approach as the rest):

  ```ini
  [caps]
  function = 40
  file = 250
  ; ...
  [budgets]
  core/pipeline = 900
  ; ...
  [exceptions]
  ; path = new cap | reason | expires at milestone
  core/merger/filtergraph.py = 300 | ffmpeg graph builder; split planned | M9
  [ratchet]
  web/app.js = 1879
  ```
- At most **3 active exceptions** at a time. Every exception has an **expiry milestone**, and CI fails once it has passed.
- Ratchets only move down. Each PR that touches a ratcheted file lowers the stored number to the new count automatically.
- Raising a package budget is a contract change: it needs its own commit, stating the reason in the caps file.

## 15.6 Why these numbers

- **40 per function and 250 per file** are tight but workable for glue code. Orchestration code that doesn't fit is usually doing two jobs.
- The **total cap (10k)** is about 2.3× v1, for: two kernels, a core that's an actual framework, five plugins, a CLI, jobs, sanitizer and capture. The prototype target of 8k keeps pressure on "wrap, don't reimplement".
- **Plugin budgets of 500** force plugins to stay glue. If a plugin needs more, the work probably belongs in an external tool or a shared core helper.
