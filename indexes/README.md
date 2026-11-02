# Vidya Wormhole indexes

Community data for [ViWo](https://github.com/Weelson7/RPy-extractor): one entry per game and
game version saying how to recognize it, which engine plugin opens it, which pinned tools and
QuickBMS scripts it needs, and what to know before extracting. ViWo reads this folder at
`indexes/` (a git submodule once this lives in its own repository, `vidya_wormhole_indexes`).

## What an index is

```
games/<slug>/<game-version>/index.json     one entry (schema in SCHEMA.md)
scripts/                                   community QuickBMS scripts (pinned by sha256)
tools/validate.py                          validator (stdlib only): python tools/validate.py
```

- `slug`: lowercase letters, digits and dashes (`skyrim-se`, `renpy-generic`).
- `game-version`: a version string, or `any` when the entry applies to every version.
- `detect`: relative paths or globs that must all exist in the game folder.
- `tools`: dependency ids from ViWo's `viwo/data/tools.json` (or its Python pins).
- `scripts`: `<ext>.bms` files pinned by URL (HTTPS only), size and sha256. ViWo installs them
  into `third_party/quickbms/scripts/`; a script whose name already exists with another checksum
  is never replaced.
- `options`: plugin options to apply; secrets (keys named `*key*`, `*secret*`, `*password*`) are
  rejected by the validator. Keys travel with requests, never with data.

Using an entry: `viwo install --game <slug> [--game-version V]` installs the tools and scripts;
`viwo detect` and the web UI report matching entries.

## Contributing

1. Copy an existing entry, keep `schema: 1`, fill every field honestly (`source` says where the
   knowledge comes from; `notes` says what does not work yet).
2. Pin scripts by their real sha256 and size; never point at a mirror you do not control.
3. Run `python tools/validate.py` and open a pull request. Entries are data: no code is accepted
   here. Borderline tools stay third-party and are covered by ViWo's disclaimer (README of ViWo,
   "Legal and disclaimer"); the index neither condones nor suggests misuse, and the person using
   an entry is responsible for what they do with it.

## Releases and versioning

- `schema` is bumped only for incompatible changes to `index.json`.
- Tags follow ViWo's major version: `v1.x` entries work with ViWo 1.y.z. A new ViWo major gets a
  new tag line; older lines keep receiving data fixes.
- ViWo pins the submodule commit it ships with; `viwo install --game` never fetches the index
  itself, only what the entry points at.
