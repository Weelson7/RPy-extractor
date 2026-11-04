# 5. Asset sanitizer (cleanup)

Extracted assets come out messy: empty files, engine junk, wrong extensions, duplicates. The
sanitizer finds them and applies only what the user accepts, with a journal for undo
(`viwo/core/sanitizer.py`, `viwo/core/sanitizer_rules.py`). It is a tool over a workspace, never
a stage of an extraction. CLI `viwo sanitize`; UI CLEANUP, run as a job of kind `cleanup`.

## 5.1 Scope

- **Shipped (phase 1, safe):** zero-byte files, engine and OS junk (`.import`, `.meta`, `.tmp`,
  `.bak`, `thumbs.db`, `desktop.ini`, `.ds_store`), extensions fixed from magic bytes, exact
  duplicates by hash, decode health checks (report only). Nothing lossy.
- **Open (phase 2):** lossless conversions to open formats (`.ctex` to PNG, `.bytes` audio once
  identified) written into `.sanitizer/cache/` and committed by core as `replace`.
- **Open (phase 3):** opt-in transcode presets and merger-friendly renumbering.

Rules:

1. Plan first (read-only), then apply only accepted findings; one undo token restores the batch.
2. Lossy actions are never in a default recipe and never run automatically after extraction.
3. Engine-specific rules come from plugins (`EnginePlugin.sanitizer_rules()`, ids
   `<plugin id>.<name>`); no built-in plugin ships one today.

## 5.2 Contract

```text
SanitizerRule                         core rule or plugin rule
  rule_id         "core.zero_byte", "<plugin id>.<name>"
  category        health | identity | dedupe | normalize | transcode | naming | junk
  cost            1 (header) .. 10 (transcode); rules run in cost order
  applies_to(path) -> bool            cheap: suffix only
  inspect(path, ctx) -> [finding]     read-only
BatchRule (dedupe): inspect_all(paths, ctx) -> [finding]; runs last, sees earlier findings,
                    never trashes the last copy of a file
RuleContext { workspace, cancel }

finding  { rule, path, severity info|warn|error, message, action none|rename|trash, to?, size }
recipe   { id, name, lossy, rules[] }       built-in: phase1-safe (core.zero_byte, core.junk,
                                            core.extension, core.duplicate, core.health)
plan     { planId, recipeId, scanned, findings[] (a page), total, offset, limit }
report   { planId, applied, moved[], trashed, failed[], undoToken }
```

- `inspect` never writes. `rename` uses the collision rule (`__N`); `trash` moves the file to
  `.trash/items/<rel>`; `core.health` findings are information and never applied.
- A plan remembers each file's size; apply refuses a stale plan (`plan is stale`).
- Each apply writes a journal under `.sanitizer/`; undo follows it in reverse and keeps what it
  could not restore. A cancel anywhere in apply leaves the batch undoable.
- Rules reach media tools only through slots (`media.probe`), never directly.

## 5.3 API and CLI

| Route | Body / result |
|-------|---------------|
| `GET /api/sanitizer/recipes` | the recipes with their active rule ids |
| `POST /api/sanitizer/plan` | `{recipeId?, path?, offset?, limit?}` -> plan (`path` = a contained sub-folder of the workspace) |
| `POST /api/sanitizer/apply` | `{planId, accept: [index] or "all-safe"}` -> report |
| `POST /api/sanitizer/undo` | `{undoToken}` |

`viwo sanitize WORKSPACE` prints the plan; `--apply` applies every safe action; `--undo TOKEN`
undoes an apply.
