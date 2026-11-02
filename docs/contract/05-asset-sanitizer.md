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

**Proposed scope:**

- **Phase 1 (safe, cheap):** zero-byte files, extension fixes from magic bytes, exact duplicates by hash, junk files (engine `.import` stubs, `.meta`, thumbnails), and decode health checks (report only).
- **Phase 2:** lossless conversions to open formats (`.ctex`→`.png`, `.dds`→`.png`, `.bytes`→`.wav`/`.ogg` once the real format is identified).
- **Phase 3:** opt-in transcode presets (for example a "web" preset: video to mp4/h264, audio to ogg/opus) and merger-friendly renumbering.

## 5.2 Contract

```text
SanitizerRule                         (provider: core or plugin, via sanitizer_rules())
  rule_id         "core.zero_byte", "godot.ctex_to_png"
  owner, category health|identity|dedupe|normalize|transcode|naming|junk
  default_enabled, lossy, cost (1 header .. 10 transcode)
  dependencies() -> [DependencySpec]     # usually slots: media.probe, image.convert
  applies_to(asset: AssetRef) -> bool    # cheap: ext/size/magic only
  inspect(asset, ctx) -> [Finding]       # read-only, may decode
  fix(finding, ctx) -> FixOutcome        # writes ONLY into ctx.cache; default: report-only

BatchRule (dedupe, numbering): inspect_all(assets, ctx) -> [Finding]

AssetRef  { path, rel, ext, size, head }
Finding   { rule_id, asset, severity info|warn|error, message, action, group }
Action    { kind none|rename|replace|add|trash, target, lossy, params }
Recipe    { recipe_id, name, rule_ids[], rule_options{}, max_workers }
SanitizePlan   { plan_id, recipe_id, findings[], scanned, skipped }
SanitizeReport { plan_id, applied, failed[], trashed, undo_token }
```

Rules (proposed):

- `inspect` never writes anything.
- `fix` writes only into `.sanitizer/cache/`. **Core** commits the result: `replace` moves the original to `.trash` and the cached file into its place, `rename` uses the v1 collision rule (`__N`), and `trash` moves the file to `.trash`.
- A recipe that contains a lossy rule can't be a default recipe and can't run automatically after extraction.
- Each apply writes a journal at `.sanitizer/journal/<plan_id>.json`. Undo follows it in reverse.
- Rules use media and image backends **through slots** (doc 8), never by calling tools directly.

## 5.3 API (additive)

| Route | Body / result |
|-------|---------------|
| `GET /api/sanitizer/recipes` | built-in recipes + saved custom recipes, each listing its rules and whether they are lossy |
| `POST /api/sanitizer/plan` | `{recipeId, path?}` → `SanitizePlan` (paged findings) |
| `POST /api/sanitizer/apply` | `{planId, accept: [findingIndex] \| "all-safe"}` → `SanitizeReport` |
| `POST /api/sanitizer/undo` | `{undoToken}` |

UI: a new workspace panel next to the Sorting Window and Media Merger
(plan table → accept → apply). This is the first new UI piece, and the
existing panels don't change.
