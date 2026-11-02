# index.json, schema 1

One object per `games/<slug>/<game-version>/index.json`. Unknown keys are ignored (forward
compatible). Validated by `tools/validate.py` and by ViWo (`viwo.core.indexes.validate`).

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `schema` | int | yes | always `1` |
| `slug` | string | yes | equals the folder name: `^[a-z0-9][a-z0-9-]{0,63}$` |
| `game_version` | string | yes | equals the folder name: `any` or `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` |
| `title` | string | yes | the game's name as people know it |
| `engine` | string | yes | ViWo plugin id (`renpy`, `unity`, `godot`, `unreal`, `doom`, `rpgmaker`, `kirikiri`, `electron`, `source`, `bethesda`, `overwatch`, `quickbms`) or `unknown` |
| `detect` | list of strings | yes, non-empty | relative paths or globs (Python `Path.glob` syntax); **all** must match for the entry to apply |
| `plugins` | list of strings | no | plugin ids to enable for this game (defaults to `[engine]`) |
| `options` | object | no | `{plugin: {key: value}}`; keys matching `key`, `secret`, `password` are rejected |
| `tools` | list of strings | no | dependency ids from ViWo's `tools.json` (or its Python pins) to install |
| `scripts` | list of objects | no | QuickBMS scripts: `{"name": "<ext>.bms", "url": "https://...", "sha256": "<64 hex>", "size": <bytes>, "license": "...", "author": "..."}` |
| `notes` | string | no | what to know: quirks, what does not work yet, reminders |
| `source` | string | no | where the knowledge comes from (URL, wiki, "own testing") |
| `license` | string | no | license of the scripts listed (per-script `license` wins) |

Rules:

- No absolute paths, no `..` in `detect`; script names have no path component and end in `.bms`.
- HTTPS only for script URLs; the checksum is verified before the file is used.
- A script named `<ext>.bms` handles files ending in `.<ext>`; `<ext>.<anything>.bms` also works.
- Entries never contain secrets, keys or anything that defeats protection. Those are not data.
