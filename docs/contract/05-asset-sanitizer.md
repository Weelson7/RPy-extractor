# 5. Asset sanitizer (Tdarr-style): review and contract

## 5.1 Review of the idea

**My read: promising, with caveats. Not a decision.** It fits right after COLLECT, and v1 already has most
of what it needs: ffmpeg/ffprobe from the merger, the trash and undo model
from sorting, and the per-extension workspace. Extracted game assets come out
messy (wrong extensions, engine-only formats, zero-byte or truncated files,
duplicates), and today you clean that up by hand in the sorting window.

What carries over well from Tdarr:

| Tdarr concept | Here |
|---------------|------|
| Library | the workspace, or any folder you choose |
| Plugin stack / flow | a **Recipe**: an ordered list of **SanitizerRules** |
| Health check (quick / thorough) | `HEALTH` rules: a header check (cheap) or a full decode through ffprobe or Pillow (expensive) |
| Transcode cache, then replace original | fixes are written to `.sanitizer/cache/`, then core swaps them in and the **original goes to `.trash`** |
| Worker pool | a bounded worker count in each recipe (the default is 2, because ffmpeg is heavy) |
| Re-scan library | the sanitizer can be re-run at any time from the workspace panel |

Where game assets differ from Tdarr, and the risks:

1. **Fidelity matters more than file size.** Archivists and modders want the original bytes. So **lossy actions are never in a default recipe**, they are clearly marked, and they're opt-in for each rule.
2. **Planning must come before any change.** Tdarr acts on files as it scans; here that's too risky. The contract **requires a plan first** (read-only), then applying only the actions you accepted. One undo token restores the whole batch.
3. **Engine-specific formats are the real win**, for example Godot `.ctex`/`.stex` to `.png`, Unity `.bytes` audio found by its magic bytes, and RenPy obfuscated or renamed files. These rules come from **plugins**, not core.
4. **Running cost.** A full decode or transcode over 100k files is slow. Rules declare a `cost`, plans run in cost order, and every rule checks the cancel token.
5. **Undo.** v1 sorting undo is kept in memory per session. A sanitizer batch can touch thousands of files, so its undo must be saved to disk (a JSON journal in `.sanitizer/`) and survive a restart.

**Scope (normative since 1.1):**

- **Phase 1 (safe, cheap):** zero-byte files, extension fixes from magic bytes, exact duplicates by hash, junk files (engine `.import` stubs, `.meta`, thumbnails), and decode health checks (report only).
- **Phase 2 (1.x, not shipped in 1.1):** lossless conversions to open formats (`.ctex`→`.png`, `.dds`→`.png`, `.bytes`→`.wav`/`.ogg` once the real format is identified); `fix` writes into `.sanitizer/cache/` and core commits `replace`.
- **Phase 3 (1.x, not shipped in 1.1):** opt-in transcode presets (for example a "web" preset: video to mp4/h264, audio to ogg/opus) and merger-friendly renumbering.

## 5.2 Contract (implemented: `viwo/core/sanitizer_rules.py`, `EnginePlugin.sanitizer_rules()`)

```text
SanitizerRule                         (provider: core or plugin, via sanitizer_rules())
  rule_id         "core.zero_byte", "godot.ctex_to_png"
  owner, category health|identity|dedupe|normalize|transcode|naming|junk
  default_enabled, lossy, cost (1 header .. 10 transcode)
  dependencies() -> [DependencySpec]     # usually slots: media.probe, image.convert
  applies_to(path: Path) -> bool         # cheap: suffix only
  inspect(path, ctx) -> [Finding]        # read-only, may read the head or decode
  fix(finding, ctx) -> FixOutcome        # writes ONLY into ctx.cache; default: report-only

BatchRule (dedupe, numbering): inspect_all(assets, ctx) -> [Finding]

(rules receive the file's `Path` and derive ext, size and head themselves; draft 3's AssetRef record is not built)
Finding   { rule, path, severity info|warn|error, message, action none|rename|trash, to?, size }
Recipe    { id, name, lossy, rules[] }            (1.1: one built-in recipe, phase1-safe)
SanitizePlan   { planId, recipeId, scanned, findings[] (page), total, offset, limit }
SanitizeReport { planId, applied, moved[], trashed, failed[], undoToken }
(JSON keys are camelCase on the wire, like every v1-shaped route; `replace`/`add` actions and
`.sanitizer/cache/` arrive with phase 2.)
```

Rules:

- `inspect` never writes anything.
- `fix` writes only into `.sanitizer/cache/` (phase 2). **Core** commits the result: `replace` (phase 2) moves the original to `.trash` and the cached file into its place, `rename` uses the v1 collision rule (`__N`), and `trash` moves the file to `.trash/items/<rel>`.
- Rules run in `cost` order; per-file rules stop at the first verdict for a file; batch rules (dedupe) run last and see the earlier findings so the last copy of a file is never trashed. Every rule checks the cancel token through the scan step.
- A plan remembers each file's size; `apply` refuses a stale plan (`plan is stale`) when a file changed since the scan.
- A recipe that contains a lossy rule can't be a default recipe and can't run automatically after extraction.
- Each apply writes a journal at `.sanitizer/journal/<plan_id>.json`. Undo follows it in reverse.
- Rules use media and image backends **through slots** (doc 8), never by calling tools directly.

## 5.3 API (additive)

| Route | Body / result |
|-------|---------------|
| `GET /api/sanitizer/recipes` | built-in recipes + saved custom recipes, each listing its rules and whether they are lossy |
| `POST /api/sanitizer/plan` | `{recipeId?, path?, offset?, limit?}` → `SanitizePlan` (`path` = sub-folder of the workspace, contained; `findings` is the page, `total` the count) |
| `POST /api/sanitizer/apply` | `{planId, accept: [findingIndex] \| "all-safe"}` → `SanitizeReport` |
| `POST /api/sanitizer/undo` | `{undoToken}` |

UI: 08 CLEANUP (plan table → accept → apply → undo), run as a job of kind `cleanup` so 04 JOBS
and the status chips show it.
