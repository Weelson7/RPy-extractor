# 18. Authoring: round trip, patching and mods

This is the third arm of the orchestrator (doc README): turning what the static (doc 6) and
dynamic (doc 11) arms found into something that ships. It covers asset **round trip** (edit assets,
repack into a runnable patched copy), **binary patch sets** (byte- and assembly-level edits to a
binary the user owns, with update-resilient signatures), and the **mod runtime framework** a user's
mod is packaged into. The original game folder is read-only throughout; output is always a separate,
marked copy.

Decisions taken:
- **Full round trip, repack in Prototype B.**
- **Output is a patched copy of the game.** The original game folder stays read-only, always.
- **The repack strategy is chosen per plugin** (override files vs rebuilding containers).
- **Same-format replacement first.** Reverse conversion (edited PNG → Texture2D / `.ctex`) comes later, engine by engine.
- **Binary patch sets and mod packaging** (18.8, 18.9) are later rungs, same patched-copy rule.

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
| POLICY | core | same warnings-and-opt-in as the dynamic arm (doc 11.1): online/anti-cheat/competitive games produce a warning and one confirmation, never a refusal (D22). Terms-of-service-sensitive plugins are tested only by the independent operator (doc 17.4b) |
| RESOLVE | core | build the edit set from workspace hashes vs the provenance map; reject edits whose format differs from the original member (same-format rule) unless the plugin declares a converter |
| PLAN | plugin | `repack_plan(edit_set, provenance) -> RepackPlan`: per container, override or rebuild; the plan is shown to the user before anything is written |
| COPY | core + OS layer | copy the game folder to the target. Copy-on-write clones (reflinks) are used where the filesystem supports them, otherwise a full copy. **Never hardlinks**: a later in-place write would change the original ❓ |
| PACK | `pack.*` slots | write override files, or rebuild containers, inside the copy only |
| VERIFY | core | re-extract each packed container with the matching `unarchive.*` slot and check that every edited member has the edited hash and every untouched member keeps its original hash. A packer with its own `verify` (Unity bundles, RPG Maker MV: no `unarchive.*` route back) checks the edited members only; the report then carries the note "untouched members were not re-verified" (1.2.1) |
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
| — | overwatch | — | no packer shipped | — | static-only plugin; a dynamic/online title warns, never refuses (doc 11.1) |

## 18.6 Rules (proposal)

1. The original game folder is never written to. All writes go to the patched copy's target folder, which must be empty or carry a patched-copy marker (the same ownership rule as workspaces).
2. ViWo authors no integrity- or anti-tamper-defeating code (philosophy point 5). When a game verifies its data, the report says plainly that the patched copy may not load, and names the check if `analysis.native` identified it (doc 6, temp.md §14). Working around it, if the user chooses to, is a third-party tool or community script under the disclaimer, never first-party.
3. Same format only, unless a plugin ships a declared converter (later milestones).
4. Every repack is verified by re-extraction before it's reported as successful.

## 18.7 Effect on other documents

- Glossary (doc 0): provenance map, edit set, mod strategy, patched copy.
- Pipeline (doc 3): COLLECT records provenance (needed for Prototype A too, cheaply).
- Slots (doc 8): new `pack.*` family.
- Roadmap (doc 16): new milestone **M9 Round trip** in Prototype B.
- Caps (doc 15): `core/roundtrip` ≤ 450; +150 per plugin for packing; the product total is the `viwo` budget line of `loc_caps.ini` (10,800 since 1.2, doc 15.3).
- Testing (doc 17): round-trip tests (extract → edit a fixture file → repack → re-extract → hashes match; original untouched; untouched members byte-identical).

## 18.8 Binary patch sets (temp.md §9, §16)

Editing a binary the user owns is the same shape as asset round trip: resolve a change, write only
into a patched copy, verify. A new `patch.*` family and a job kind `patch`:

```text
PatchSet
  base        the binary and its original content hash (from the extraction provenance)
  edits       [ { at: AddressRef, original_bytes, new_bytes, note } ]
  AddressRef  file_offset | rva | { signature, disp }     # signature = AOB pattern
```

| Step | Owner | What happens |
|------|-------|--------------|
| RESOLVE | core | turn each `AddressRef` into a file offset against the base; a `signature` AddressRef is resolved by scanning for the AOB pattern, so the patch survives updates and rebases |
| PLAN | core | show the diff (offset, original → new, disassembly of both via `analysis.native` where available) before anything is written |
| APPLY | `patch.bytes` | write the edits into a **copy** of the binary in the patched-copy target only |
| VERIFY | core | re-read the patched copy: every edited range has the new bytes, every untouched byte is unchanged; the original binary's hash is unchanged |
| EXPORT | core | emit the patch in portable forms: a byte diff, an AOB-signature patch (resilient to the next game version), and a human-readable report |

Slots: `patch.bytes` (our writer; byte- and, with a pinned runtime assembler such as Keystone or
asmjit as a **library** the writer calls, assembly-level edits), `patch.sig` (generate an AOB
signature for a chosen address so the address resolves after an update; pairs with `analysis.diff`,
doc 6). Code caves and new-section injection are expressed as `edits` that append a section to the
copy. ViWo writes the diff mechanics; it authors no protection- or integrity-defeating edit — the
edits are the user's, and any that targets a protection is the user's choice under the disclaimer.

## 18.9 Mod runtime framework (temp.md §19)

What a finished mod ships inside. ViWo does not author the hooks a mod uses (those are pinned
libraries, doc 11.2); it **packages** the mod and gives it the scaffolding that stops every mod
reinventing the same plumbing:

- a **mod loader** with load order and dependency resolution;
- a **stable API layer** over the raw hooks so two mods don't patch the same function blindly
  (conflict detection between mods);
- config files, in-game UI (through the overlay, doc 11.2), logging;
- a crash handler with minidumps and symbolication of the user's own mod code, using the symbol/
  header artifacts the static arm exported (doc 6.3);
- an update checker tied to the game version, using the AOB signatures from 18.8 and `analysis.diff`
  so offsets survive patches.

This is a packaging and SDK concern, built from the artifacts the other two arms produce; it adds a
`mod.package` slot and reuses the patched-copy output rule. It is a late roadmap rung (doc 16),
Python- and manifest-driven like the rest of the plugin system (doc 2.8).
