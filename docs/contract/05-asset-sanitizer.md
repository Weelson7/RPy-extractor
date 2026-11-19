# 5. Asset sanitizer (cleanup)

Extracted assets come out messy: empty files, engine junk, wrong extensions, duplicates, formats
nothing opens. The sanitizer finds them and applies only what the user accepts, with a journal
for undo (`viwo/core/sanitizer.py`, `viwo/core/sanitizer_rules.py`, `viwo/core/sanitizer_convert.py`
for the rules that write files, `viwo/core/sanitizer_journal.py`; the rule types every rule
subclasses, core's and the plugins', in `viwo/contracts/sanitizer.py`). It is a tool over a
workspace, never a stage of an extraction. CLI `viwo sanitize`; UI CLEANUP, run as a job of kind
`cleanup`.

## 5.1 Scope

- **Phase 1, safe (recipe `phase1-safe`, the default):** zero-byte files, engine and OS junk
  (`.import`, `.meta`, `.tmp`, `.bak`, `thumbs.db`, `desktop.ini`, `.ds_store`), extensions fixed
  from magic bytes, exact duplicates by hash, decode health checks (report only). Nothing lossy.
- **Phase 2, lossless open-format copies:**
  - `phase2-convert` (`core.convert`): a workspace file whose extension a bound `decode.*` slot
    reads, with a lossless decoder (`Decoder.lossless`, doc 8.3; video, which re-encodes, is
    left out), gets the copy that decoder writes (DDS to PNG, game audio to WAV, a plugin's
    textures and models to PNG and glTF): the same decoders an extraction runs, with the same
    failover. The copy lands where DECODE puts it (the extension's group folder, the collision
    rule) with a provenance entry `decode:<backend>:<file>:<output>`, so an edited copy goes back
    through the round trip (doc 18.3) like a decoded one. The original stays.
  - `phase2-replace` (`core.convert_replace`): the same copy, then the original moves to the
    workspace trash (after the copy is in place; a failed copy trashes nothing).
  - Left out, by design: a file a decoder already read (its provenance says so: an extraction
    decoded it, or an earlier apply), an empty file (phase 1's), and a plugin's slot when the
    workspace's run records name other plugins (a `.json` of a Unity game is no CR2W file); a
    workspace without a run record that names a plugin (a converted folder of the user's) gets
    every bound slot.
- **Phase 3, opt-in:**
  - `phase3-audio` (`core.transcode_audio`, LOSSY): WAV, FLAC and AIFF to Opus, 128 kb/s, in Ogg
    (`.ogg`). `phase3-video` (`core.transcode_video`, LOSSY): AVI, MKV, MOV, WMV, MPEG, OGV, WebM,
    FLV and Bink 1 to H.264/AAC MP4 (`-crf 23`, `+faststart`). Both run the pinned ffmpeg of the
    `media.encode` slot as a separate process, write a copy (placed and recorded as above, origin
    `transcode:ffmpeg:<file>:<output>`) and keep the original.
  - `phase3-renumber` (`core.renumber`): the files of one folder named `<prefix><number>` with
    one extension, two or more, renamed to contiguous zero-padded numbers in their numeric
    order, from the lowest one (`a1 a3 a10` -> `a01 a02 a03`; the width is the widest of the
    digits found and of the last number). Each rename lowers a number, so none lands on a name
    another member still holds. A number held twice leaves the sequence as it is, said in a
    report-only finding.

Rules:

1. Plan first (read-only), then apply only accepted findings; one undo token restores the batch.
2. Lossy actions are never in a default recipe and never run automatically after extraction.
   A lossy rule (`SanitizerRule.lossy`) marks its recipe `lossy` and each finding `lossy`;
   apply's `all-safe` never takes a lossy finding: it runs only when the user picks it (its
   index, or `all` on a plan of the lossy recipe the user chose).
3. The safe recipe holds every rule that is `default_enabled` and not lossy; a phase 2-3 rule is
   not `default_enabled` and runs only in the recipe that names it.
4. Engine-specific rules come from plugins (`EnginePlugin.sanitizer_rules()`, ids
   `<plugin id>.<name>`), subclasses of the rule types in `viwo/contracts/sanitizer.py`. Built
   in: `renpy.cache` (junk, cost 1): a non-empty `.rpyb` file, the caches Ren'Py writes under
   `game/cache/` and rebuilds when they are missing, goes to the trash.
5. A rule that cannot act now says why (`unready()`: no lossless decode slot bound, ffmpeg not
   bound): in the recipe list and in the plan's `warnings`, never an empty plan alone.

## 5.2 Contract

```text
SanitizerRule                         core rule or plugin rule
  rule_id         "core.zero_byte", "<plugin id>.<name>"
  category        health | identity | dedupe | normalize | transcode | naming | junk
  cost            1 (header) .. 10 (transcode); rules run in cost order
  default_enabled in the safe recipe; lossy: rewrites content with loss
  applies_to(path) -> bool            cheap: suffix only
  inspect(path, ctx) -> [finding]     read-only
  unready() -> reason | ""            why it cannot act now
  fix(finding, ctx) -> origin         actions convert | replace | transcode: writes into
                                      ctx.cache, returns the provenance origin; raises OSError
BatchRule (dedupe, renumber): inspect_all(paths, ctx, earlier) -> [finding]; runs last, sees
                    earlier findings, never trashes the last copy of a file
RuleContext { workspace, cancel, sink, cache }

finding  { rule, path, severity info|warn|error, message, action, to?, slot?, lossy, size }
action   none | rename | trash | convert | replace | transcode
recipe   { id, name, phase, lossy, rules[], unready }
         phase1-safe (core.zero_byte, core.junk, core.extension, core.duplicate, core.health,
         plugin rules), phase2-convert, phase2-replace, phase3-audio (lossy), phase3-video
         (lossy), phase3-renumber
plan     { planId, recipeId, scanned, findings[] (a page), warnings[], total, offset, limit }
report   { planId, applied, moved[], trashed, converted[] {path, made[], rule, action, lossy},
           failed[], undoToken }
undo     { restored, removed, notRestored[] }
journal  [now, before] a move | {made, sha256} a file the sanitizer wrote
```

- `inspect` never writes. `rename` uses the collision rule (`__N`); `trash` moves the file to
  `.trash/items/<rel>`; `core.health` findings are information and never applied.
- `convert`, `replace` and `transcode`: the rule's `fix` writes into
  `.sanitizer/cache/<plan>/<n>/` (removed after the apply); core moves what it wrote into the
  workspace, appends the provenance entries (`kind: derived`) and journals every file made as
  it lands, then for `replace` trashes the original. A file a decoder or ffmpeg cannot convert
  is named in `failed` with the tool's reason (the spare's and the main's when the spare stood
  in); a spare that stood in for a converted file is a warn event. The report says per file
  what it became (`converted[].made`).
- A plan remembers each file's size; apply refuses a stale plan (`plan is stale`).
- Plan, apply and undo write into the workspace (`.sanitizer/`, moves): a folder that may be a
  game (a game the guard knows, a patched copy, or files without the ViWo workspace marker) is
  refused first (doc 3.1).
- Each apply writes a journal under `.sanitizer/journal/`; undo follows it in reverse: a move
  goes back, a file made is removed (and its provenance entry dropped) while its bytes are still
  the ones made. An edited copy, or what could not be restored, stays in the journal and is
  named in `notRestored`, so a later undo can finish. A cancel anywhere in apply leaves the
  batch undoable.
- Rules reach media tools only through slots (`decode.*`, `media.probe`, `media.encode`), never
  directly.

## 5.3 API and CLI

| Route | Body / result |
|-------|---------------|
| `GET /api/sanitizer/recipes` | every recipe with its rule ids in play, `phase`, `lossy`, `unready` |
| `POST /api/sanitizer/plan` | `{recipeId?, path?, offset?, limit?}` -> plan (`path` = a contained sub-folder of the workspace) |
| `POST /api/sanitizer/apply` | `{planId, accept: [index] or "all-safe" or "all"}` -> report (`all-safe` leaves lossy findings) |
| `POST /api/sanitizer/undo` | `{undoToken}` -> undo |

`viwo sanitize WORKSPACE [--recipe ID]` prints the plan (the safe recipe without `--recipe`);
`--apply` applies every action of the plan: of a lossy recipe only when `--recipe` names it;
`--undo TOKEN` undoes an apply. The text form lists what each file became; failures and the
recipe's `warnings` are envelope warnings.
