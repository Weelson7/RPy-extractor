# 18. Round trip: repack and modding (draft)

Decisions taken:
- **Full round trip, repack in Prototype B.**
- **Output is a patched copy of the game.** The original game folder stays read-only, always.
- **The repack strategy is chosen per plugin** (override files vs rebuilding containers).
- **Same-format replacement first.** Reverse conversion (edited PNG → Texture2D / `.ctex`) comes later, engine by engine.

## 18.1 What round trip means here

```
game folder ──extract──▶ workspace ──user edits files──▶ edit set
     │                                                  │
     └──copy──▶ patched copy ◀──pack (plugin strategy)──┘
```

The original never changes. The user gets a separate, runnable patched copy
plus a report of what was changed.

## 18.2 New concepts (added to the glossary)

- **Provenance map:** for every workspace file, where it came from: the chain of containers (game file → archive → nested archive), the member path inside the last container, the backend that produced it, and the original content hash. COLLECT writes it to `.extraction_metadata/provenance.jsonl`. Round trip is impossible without it, and it's also what the "every file traceable" criterion (doc 14.4) asks for.
- **Edit set:** the workspace files whose hash differs from the provenance hash (**modified**), plus files the user explicitly adds with a target path (**added**). Deletions are out of scope at first ❓.
- **Mod strategy** (per plugin, per container):
  - **override:** the engine loads loose files or patch containers on top of the originals (Ren'Py loose files in `game/`; Unreal `*_P.pak` patch paks; others where the engine supports it).
  - **rebuild:** write a new copy of the original container with the edited members replaced (Godot `.pck`, Unity bundles, Ren'Py `.rpa` if override isn't wanted).
- **Patched copy:** a full copy of the game folder in an output location, with overrides added and/or containers rebuilt.

## 18.3 Repack job

A new job kind, `repack` (doc 12):

| Step | Owner | What happens |
|------|-------|--------------|
| POLICY | core | same hard refusals as runtime capture (doc 11.1): online/anti-cheat games are refused. Terms-of-service-sensitive plugins are tested only by the independent operator (doc 17.4b) |
| RESOLVE | core | build the edit set from workspace hashes vs the provenance map; reject edits whose format differs from the original member (same-format rule) unless the plugin declares a converter |
| PLAN | plugin | `repack_plan(edit_set, provenance) -> RepackPlan`: per container, override or rebuild; the plan is shown to the user before anything is written |
| COPY | core + OS layer | copy the game folder to the target. Copy-on-write clones (reflinks) are used where the filesystem supports them, otherwise a full copy. **Never hardlinks**: a later in-place write would change the original ❓ |
| PACK | `pack.*` slots | write override files, or rebuild containers, inside the copy only |
| VERIFY | core | re-extract each packed container with the matching `unarchive.*` slot and check that every edited member has the edited hash and every untouched member keeps its original hash |
| REPORT | core | a run record with the plan, the edits, the backends used, and the verification result |

## 18.4 Interfaces

```text
Packer                       (family: pack)
  pack(original: Path | None, members: {member_path: source_file}, out: Path, ctx) -> Outcome
  supports_rebuild: bool, supports_override: bool

EnginePlugin (new optional hooks)
  mod_strategies() -> [ModStrategy]            # what this engine supports
  repack_plan(edit_set, provenance, options) -> RepackPlan

RepackPlan { items: [ { container, strategy: override|rebuild, slot, members, target_path } ], warnings }
```

## 18.5 Default pack slots (proposal; tool facts from doc 13)

| Slot | Owner | Strategy | Main | Spare | Notes |
|------|-------|----------|------|-------|-------|
| `pack.renpy-override` | renpy | override | core file copy into `game/` | — | Ren'Py loads loose files over archives (to verify per Ren'Py version ❓) |
| `pack.rpa` | renpy | rebuild | `rpa-writer` (ours; we write the pickle index ourselves, so nothing untrusted is unpickled) | `rpatool` (WTFPL; writes RPA-2/3) | |
| `pack.pck` | godot | rebuild | `godotpcktool` (writes PCK v1–v4) | `gdre-tools` (pack support to verify ❓) | encrypted PCKs: rebuilding needs the key |
| `pack.pak` | unreal | override (`_P.pak`) | `repak pack` | `quickbms` reimport (to verify ❓) | signed paks (`.sig`) may refuse to load; reported, not bypassed |
| `pack.unity-bundle` | unity | rebuild | `unitypy` (save the modified file) | `uabea` (`batchimportbundle`) | same-format raw replacement only at first |
| `pack.zip` / `pack.tar` | core | rebuild | stdlib | `sevenzip-cli` | Love2D, NW.js `package.nw` later |
| — | overwatch | — | **not supported** | — | online game, refused by policy |

## 18.6 Rules (proposal)

1. The original game folder is never written to. All writes go to the patched copy's target folder, which must be empty or carry a patched-copy marker (the same ownership rule as workspaces).
2. No signature, integrity or anti-tamper check is bypassed. If a game verifies its data, the report says the patched copy may not load.
3. Same format only, unless a plugin ships a declared converter (later milestones).
4. Every repack is verified by re-extraction before it's reported as successful.

## 18.7 Effect on other documents

- Glossary (doc 0): provenance map, edit set, mod strategy, patched copy.
- Pipeline (doc 3): COLLECT records provenance (needed for Prototype A too, cheaply).
- Slots (doc 8): new `pack.*` family.
- Roadmap (doc 16): new milestone **M9 Round trip** in Prototype B.
- Caps (doc 15): `core/roundtrip` ≤ 450; +150 per plugin for packing; Prototype B target ≤ **9,000** (total cap unchanged at 10,000) ❓.
- Testing (doc 17): round-trip tests (extract → edit a fixture file → repack → re-extract → hashes match; original untouched; untouched members byte-identical).
