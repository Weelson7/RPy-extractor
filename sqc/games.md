# Test games: free titles per engine for the integration run

Install each title into `Test-games/<slug>/` (the folder that holds the game's executable or
data), then run `python tools/integration_games.py` (see 00-README). ViWo only reads these
folders: every run hashes the game folder before and after and fails if anything changed.

Licensing: you download and own each copy under its own license and terms; ViWo extracts for
your personal use on your machine. Distributing what comes out is a separate matter (README,
"Legal and disclaimer"). Online or anti-cheat titles produce warnings in ViWo, never refusals.

Verified on 2026-11-03 from the store pages themselves (price, platform, engine). Sizes are
the store's download sizes. "none verified" means no free title could be confirmed tonight.

| Engine (plugin) | Title | Where | Size | Exercises | Slug |
|---|---|---|---|---|---|
| Ren'Py (`renpy`) | Doki Doki Literature Club! v1.1.1 (Team Salvato), free, name your own price | https://teamsalvato.itch.io/ddlc | 220 MB (Windows) | `.rpa` archives, `.rpyc` scripts (decompile slot), Ren'Py 6.99 game folder layout | `ddlc` |
| Unity (`unity`) | ULTRAKILL Prelude v1.05b (free demo, New Blood / Hakita) | https://hakita.itch.io/ultrakill-prelude | 130 MB | Unity 2019-era `*_Data` folder, `sharedassets*.assets`, `resources.assets`, StreamingAssets, meshes to OBJ | `ultrakill-prelude` |
| Unity (`unity`) | Baldi's Basics Classic Remastered 1.1a (Basically Games), free | https://basically-games.itch.io/baldis-basics-classic-remastered | 135 MB | a second Unity version and asset bundle layout for the UnityPy / AssetStudio pair | `baldi-cr` |
| Godot (`godot`) | My First Godot Game (Thegaminglemon10), free | https://thegaminglemon10.itch.io/my-first-godot-game | 32 MB exe + 447 MB `.pck` | a large standalone `.pck` next to the exe (GDRE Tools main, GodotPckTool spare, PCK round trip) | `godot-first` |
| Godot (`godot`) | GodotOne (aztik7), free, single `GodotOne.exe`. **Checked 2026-11-03:** the itch download is a bare export template (empty PE `pck` section, no `.pck`): no game data to extract; ViWo reports "no PCK data". Use My First Godot Game instead | https://aztik7.itch.io/godotone | 35 MB | PCK embedded in the executable (carve + unpack) | `godotone` |
| Unreal (`unreal`) | Void's Cave DEMO (ZAYgt), Unreal Engine 5, free | https://zaygt.itch.io/voids-cave | 247 MB | UE5 `Content/Paks/*.pak` and, if present, IoStore `.utoc/.ucas` (retoc), AES key lookup in the shipping exe | `voids-cave` |
| Unreal (`unreal`) | The Basement (willgdev), Unreal Engine 5, free; the itch file is `Windows.zip` (project name `UE5Project`) | https://willgdev.itch.io/the-basement | 601 MB | a second UE5 packaging (pak only or IoStore), repak round trip (`_P.pak`) | `the-basement` |
| Doom engine (`doom`) | Freedoom 0.13.0 (BSD-licensed data) | https://github.com/freedoom/freedoom/releases/download/v0.13.0/freedoom-0.13.0.zip | 24 MB (also `freedm-0.13.0.zip`, 11 MB) | IWAD: PNG pictures, WAV sounds, MIDI music, maps; the CI reference game | `freedoom` |
| RPG Maker VX Ace (`rpgmaker`) | Ancient Challenger (RetroToby), free, built with the default assets | https://retrotoby.itch.io/ancient-challenger | 208 MB (`ancientchallenger.exe` self-extractor) | `Game.rgss3a` archive (RGSSAD v3), RTP note: install the VX Ace RTP if the game asks | `ancient-challenger` |
| RPG Maker MV (`rpgmaker` + `electron`) | My first shitty game with RPG Maker MV (Atnash95), free | https://atnash95.itch.io/my-first-shitty-game-with-rpg-maker-mv | 359 MB | MV `www/` tree, encrypted `.rpgmvp/.rpgmvo` media with the key from `System.json`; the game runs on NW.js (`nw.exe`, `package.json`), so the Electron/NW.js detection fires too | `rpgmv-first` |
| KiriKiri (`kirikiri`) | Ubu ver 2.0b (u-b-u), free, built with Kirikiri (per the developer's release post) | https://u-b-u.itch.io/ubu | 733 MB | `data.xp3` and friends (XP3 unencrypted entries; per-title ciphers are reported, not decrypted) | `ubu` |
| Electron / NW.js (`electron`) | none verified as a standalone Electron `app.asar` game; the RPG Maker MV title above ships the NW.js runtime (`package.nw` is a zip, `nw.exe` marker) | | | asar / `.nw` zip handling | (use `rpgmv-first`) |
| Source (`source`) | Team Fortress 2 (Valve), free to play on Steam; online title: **warnings expected** | https://store.steampowered.com/app/440/ | about 15 GB | `tf/tf2_*.vpk` multi-part VPK v2 (`_dir.vpk` + numbered parts), `hl2/*.vpk` | `tf2` (point at `Team Fortress 2/`) |
| Bethesda (`bethesda`) | none verified free. If you own one: Skyrim Special Edition (`Data/*.bsa`, LZ4 entries, needs the `lz4` pin), Fallout 4 (`Data/*.ba2`, textures rebuilt as DDS) | | | BSA 105 / BA2 | `skyrim-se`, `fallout4` |
| Genie (`genie`) | Age of Empires II HD (owner's copy; any AoE I/II install) | | 5.5 GB | `.drs` resource archives: SLP graphics, WAV, BINA | `pass-aoe` |
| Warscape (`warscape`) | Total War: Rome II (owner's copy; Empire through Warhammer share PFH4/PFH5) | | 36 GB | `data/*.pack`: db tables, textures, models, scripts, loc | `pass-total-war-rome-ii` |
| REDengine 4 (`redengine`) | Cyberpunk 2077 (owner's copy) | | 86 GB | `archive/pc/content/*.archive` (RDAR): Kraken segments inflated with the game's own `oo2ext_7_win64.dll`; members by name hash with the CR2W type as extension | `pass-cyberpunk-2077` |
| QuickBMS (`quickbms`) | no title of its own: it serves any archive with a `<ext>.bms` script in `third_party/quickbms/scripts` (indexes supply them per game) | | | script bridge | any |
| Overwatch (`overwatch`, OPERATOR) | Overwatch 2 (Blizzard), free to play via Battle.net; terms-of-service-sensitive: **warnings expected**, real-game run by the operator | https://overwatch.blizzard.com | 50 GB+ | CASC data through DataTool (Windows only), explicit or auto-selected with the reminder | `overwatch` |

Notes
- Prefer the smaller titles first (Freedoom, DDLC, ULTRAKILL Prelude, Godot First, Void's Cave,
  Ancient Challenger, the MV title); together they cover every unarchive and export slot that has
  a tool tonight except Bethesda and Overwatch.
- itch.io pages were read directly for price, platform and "Made with" tags where present. The
  Godot and Kirikiri titles state the engine in the developer's own text; no engine version is
  published for them.
- Self-extracting downloads (`ancientchallenger.exe`) must be run once by you to unpack the game
  into its slug folder; ViWo never runs them.
