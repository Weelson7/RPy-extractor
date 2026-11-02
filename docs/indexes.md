# Per-game indexes (`indexes/`)

Owner's decision (1.0): ViWo's knowledge of individual games is **data, not code**, and it is
**community driven**. The `indexes/` folder holds one entry per game and game version:
how to recognize it, which engine plugin opens it, which pinned tools and QuickBMS scripts it
needs, what to know before extracting. ViWo stays small; coverage grows by adding entries.

## Design

- Layout: `indexes/games/<slug>/<game-version>/index.json`, `indexes/scripts/`,
  `indexes/tools/validate.py`, `indexes/README.md`, `indexes/SCHEMA.md`. The folder is laid out
  exactly as the root of the future `vidya_wormhole_indexes` repository, so it can be split out
  without moving anything.
- Code: `viwo/core/indexes.py` (`list_games`, `load_index`, `validate`, `match_game`,
  `install_game`). `install_game` installs the entry's tools through the preflight installer
  (`viwo.core.preflight.install`, pinned and checksummed into `third_party/`) and its scripts into
  `third_party/quickbms/scripts/` (HTTPS only, sha256 verified, an existing script with another
  checksum is never replaced). The QuickBMS plugin loads that folder by default at boot.
- CLI: `viwo install --game <slug> [--game-version V]`.
- Data rules: no secrets in an index (keys travel with requests), no absolute paths, no code.
  Borderline tools stay third-party and under ViWo's disclaimer; an index neither condones nor
  suggests misuse, and the person using an entry is responsible for what they do with it.
- Validation: `python indexes/tools/validate.py` (stdlib only, usable in the indexes repository's
  own CI) and `tests/test_indexes.py` in ViWo (shipped entries must validate).

Starter entries: `freedoom`, `renpy-generic`, `godot-generic`, `unreal-generic`, `skyrim-se`,
`overwatch`, all `game_version = any`, no scripts yet (none could be verified from a trusted HTTPS
source with a checksum tonight; `notes` says so where relevant).

## Splitting it into the `vidya_wormhole_indexes` repository (owner)

```powershell
# 1. create the empty repository on GitHub: Weelson7/vidya_wormhole_indexes (public, no README)
# 2. move the history of indexes/ into its own branch and push it
git subtree split -P indexes -b indexes-main
git push https://github.com/Weelson7/vidya_wormhole_indexes.git indexes-main:main
# 3. replace the folder with the submodule
git rm -r indexes
git submodule add https://github.com/Weelson7/vidya_wormhole_indexes.git indexes
python tools/version.py commit -m "indexes/ becomes the vidya_wormhole_indexes submodule"
# 4. a fresh clone needs: git submodule update --init
```

The portable build copies `indexes/` next to `viwo.exe` (pack it in `packaging/build_portable.py`
once the submodule exists; until then the folder is part of the checkout).

## Releases and versioning of the indexes

- `schema` is bumped only for incompatible changes to `index.json`.
- Tags follow ViWo's major version: a `v1.x` line of tags works with every ViWo `1.y.z`; a new ViWo
  major opens a new line; older lines keep receiving data fixes.
- ViWo pins the submodule commit it ships with (the release notes name it). `viwo install --game`
  never updates the index itself; `git submodule update --remote indexes` does.
- `viwo indexes update` (and 05 SYSTEM > UPDATE INDEXES) fetches the newest release of the
  matching tag line over HTTPS with a checksum, for installs without git (see below).

## Release convention of `vidya_wormhole_indexes` (what `viwo indexes update` expects)

Every release of the indexes repository is a tag `v<major>.<n>` (optionally `.<p>`) whose major
is the ViWo major it targets. The release carries exactly two assets:

- `indexes-v<major>.<n>.zip`: the repository tree (`games/`, `scripts/`, `tools/`, `README.md`,
  `SCHEMA.md`), with or without a single top-level folder;
- `SHA256SUMS.txt`: `sha256sum` output, one line per asset (`<hex>  <name>`).

`viwo indexes update` lists the releases of `Weelson7/vidya_wormhole_indexes` (GitHub API, only
when you ask), takes the newest tag of the `v<major>.*` line, downloads both assets over HTTPS,
checks the zip against `SHA256SUMS.txt`, unpacks it safely into a temporary folder, writes
`VERSION` (the tag), and swaps it in as `indexes/` (the old folder is renamed `indexes.old` until
the new one is in place, then removed). A git checkout of `indexes/` (a `.git` link inside) is
refused: use `git submodule update --remote indexes` there. `GET /api/updates` reports the
installed `VERSION` next to the latest tag.
