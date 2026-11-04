# 15. Code size caps

Enforced by `tools/loc_count.py` (reads `loc_caps.ini` through `tools/caps_ini.py`) as an L0
gate (`tests/test_pipeline.py::test_loc_caps`) and by `tools/version.py commit` before every
commit. The numbers below mirror `loc_caps.ini`; the ini is the source.

## 15.1 Counting rules

1. **Format first:** `ruff format` (line length 100) before counting; a line over 100 characters
   is itself a failure.
2. **Python:** a line counts if it holds any token other than comments, blank lines and
   indentation (the counter uses `tokenize`). Docstrings (the first string of a module, class or
   function) are excluded; other multi-line strings count on every line.
3. **JS / CSS / HTML:** non-blank lines that are not purely `//`, `/* */` or `<!-- -->` comments.
4. **Counted trees:** `viwo/` (product), `tests/` (test caps and the floor), `tools/` (its own
   budget). Excluded: `third_party/`, `indexes/`, `examples/`, `sqc/fixtures/`, `packaging/`,
   docs and data files (`viwo/data/`).

## 15.3 Product caps

**Granularity** (`[caps]`, hard):

| Unit | Cap |
|------|-----|
| function or method | 40 |
| class | 200 |
| file | 250 |
| file in `viwo/contracts/` | 150 |
| parameters per function | 6 (not applied to tests) |
| line length | 100 |
| JS file | 300 |

**Budgets** (`[budgets]`, hard totals per path prefix; the split inside is free):

| Prefix | Budget | Used at 1.6.0 |
|--------|--------|---------------|
| `viwo` (whole product) | 13,900 | 13,870 |
| `viwo/core` | 6,900 | 6,780 |
| `viwo/contracts` | 900 | 744 |
| `viwo/os` | 900 | 533 |
| `viwo/backends` | 600 | 187 |
| `viwo/cli.py` | 400 | 153 |
| each built-in plugin `viwo/plugins/<id>` | 100 (generic) to 700 (unity); one line each | see `loc_caps.ini` |
| `tools` | 900 | 875 |
| `viwo/web` (`[web]`, js + css + html) | 5,400 | 5,071 |

`viwo/api` and the `cli_*.py` modules count only under the `viwo` total. Every raise carries its
reason as an inline comment on the budget line.

## 15.4 Test caps

Test file 400, test function 60; fixture builders and fake tools live inside the test files
under the same caps. No total budget; instead a **floor**: test LoC >= 0.6 x (`viwo/contracts` +
`viwo/core`) (7,264 against a floor of 4,514 at 1.6.0).

## 15.5 Exceptions and raises

- `[exceptions]` in `loc_caps.ini`: `path = cap | reason | expires at vX.Y` raises the file cap of
  that exact path; at most 3 active; one whose version has been reached fails the gate until it
  is removed or renewed. None is active.
- The caps file is validated: unknown sections or keys, non-integer values, a malformed exception
  line or a missing cap fail L0 (`tests/test_l0_static.py`).
- Raising a budget is a contract change: the new value and its reason go on the budget line.

## 15.6 Why

40 lines per function and 250 per file are tight but workable for glue: orchestration code that
does not fit is usually doing two jobs. Plugin budgets of 100-700 keep plugins as glue; work
that needs more belongs in an external tool or a shared core helper. The pressure stays on
"wrap, don't reimplement".
