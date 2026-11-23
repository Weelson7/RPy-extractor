# Test games: free titles per engine for the integration run

Install each title into `Test-games/<slug>/` (the folder that holds the game's executable or
data), then run `python tools/integration_games.py` (see 00-README and 17-ctf). ViWo only reads
these folders: every run hashes the game folder before and after and fails if anything changed.

**Installed on 2026-11-23 (main checkout's `Test-games/`): only `freedoom` (Freedoom 0.13.0:
`freedoom1.wad`, `freedoom2.wad`) and `chocolate-doom/engine` (Chocolate Doom, for SQC-RT-LOAD).**
Every other title of the table is not installed any more: the checks that need one are NOT RUN
until it is installed again from the address given.

Licensing: you download and own each copy under its own license and terms; ViWo extracts for
your personal use on your machine. Distributing what comes out is a separate matter (README,
"Legal and disclaimer"). Online or anti-cheat titles produce warnings in ViWo, never refusals.

Verified on 2026-11-03 from the store pages themselves (price, platform, engine). Sizes are the
store's download sizes. "none verified" means no free title has been confirmed for that engine.
The slug is the folder name and the key of the title's flags in `ctf.json` (never rename one:
the reports are keyed by it); which titles carry flags is listed under the table.

| Engine (plugin) | Title | Where | Size | Exercises | Slug |
|---|---|---|---|---|---|
| Ren'Py (`renpy`) | Doki Doki Literature Club! v1.1.1 (Team Salvato), free, name your own price | https://teamsalvato.itch.io/ddlc | 220 MB (Windows) | `.rpa` archives, `.rpyc` scripts (decompile slot), Ren'Py 6.99 game folder layout | `DDLC-1.1.1-pc` |
| Unity (`unity`) | ULTRAKILL Prelude v1.05b (free demo, New Blood / Hakita) | https://hakita.itch.io/ultrakill-prelude | 130 MB | Unity 2019-era `*_Data` folder, `sharedassets*.assets`, `resources.assets`, StreamingAssets, meshes to OBJ | `ultrakill-prelude` |
| Unity (`unity`) | Baldi's Basics Classic Remastered 1.1a (Basically Games), free | https://basically-games.itch.io/baldis-basics-classic-remastered | 135 MB | a second Unity version and asset bundle layout for the UnityPy / AssetStudio pair | `baldi-cr` |
| Unity (`unity`) | Burning Snow 1.0.4, free (its store page was not recorded) | | 20 MB | a small Unity build: textures, a level's meshes, text assets | `BURNING_SNOW_1_0_4` |
| Godot (`godot`) | My First Godot Game (Thegaminglemon10), free | https://thegaminglemon10.itch.io/my-first-godot-game | 32 MB exe + 447 MB `.pck` | a large standalone `.pck` next to the exe (GDRE Tools main, GodotPckTool spare, PCK round trip) | `godot-first` |
| Godot (`godot`) | GodotOne (aztik7), free, single `GodotOne.exe`: a bare export template (empty PE `pck` section, no `.pck`); ViWo reports "no PCK data" | https://aztik7.itch.io/godotone | 35 MB | the plain "no PCK data" answer | `godotone` |
| Godot (`godot`) | MAD game, free (its store page was not recorded): a bare export template like GodotOne | | 30 MB | the "no PCK data" answer on a second template | `godot-mad` |
| Unreal (`unreal`) | Void's Cave DEMO (ZAYgt), Unreal Engine 5, free | https://zaygt.itch.io/voids-cave | 247 MB | UE5 `Content/Paks/*.pak` and IoStore `.utoc/.ucas` (retoc), AES key lookup in the shipping exe | `voids-cave` |
| Unreal (`unreal`) | The Basement (willgdev), Unreal Engine 5, free; the itch file is `Windows.zip` (project `UE5Project`) | https://willgdev.itch.io/the-basement | 601 MB | a second UE5 packaging, repak round trip (`_P.pak`) | `the-basement` |
| Doom engine (`doom`) | Freedoom 0.13.0 (BSD-licensed data) | https://github.com/freedoom/freedoom/releases/download/v0.13.0/freedoom-0.13.0.zip | 24 MB | IWAD: PNG pictures, WAV sounds, MIDI music, maps; the CI reference game | `freedoom` (installed) |
| Doom engine to run it | Chocolate Doom 3.1.0 (GPL-2.0, run as its own process) | https://github.com/chocolate-doom/chocolate-doom/releases/download/chocolate-doom-3.1.0/chocolate-doom-3.1.0-win32.zip (sha256 `240909f7d161dbc71793dc79bb3e43100bf6cee5a2e3fcf8d1b2451fc47ff1ee`) | 8 MB | only for SQC-RT-LOAD | `chocolate-doom/engine` (installed) |
| RPG Maker VX Ace (`rpgmaker`) | Ancient Challenger (RetroToby), free, built with the default assets | https://retrotoby.itch.io/ancient-challenger | 208 MB (`ancientchallenger.exe` self-extractor) | `Game.rgss3a` (RGSSAD v3); install the VX Ace RTP if the game asks | `ancient-challenger` |
| RPG Maker MV (`rpgmaker` + `electron`) | My first shitty game with RPG Maker MV (Atnash95), free | https://atnash95.itch.io/my-first-shitty-game-with-rpg-maker-mv | 359 MB | MV `www/` tree, encrypted `.rpgmvp/.rpgmvo` with the key from `System.json`; NW.js runtime | `rpgmv-first` |
| KiriKiri (`kirikiri`) | Ubu ver 2.0b (u-b-u), free, built with Kirikiri (per the developer's release post) | https://u-b-u.itch.io/ubu | 733 MB | `data.xp3` and friends (unencrypted entries; per-title ciphers reported) | `ubu` |
| Electron / NW.js (`electron`) | none verified as a standalone Electron `app.asar` game; the RPG Maker MV title above ships the NW.js runtime | | | asar / `.nw` zip handling | (use `rpgmv-first`) |
| Source (`source`) | Team Fortress 2 (Valve), free to play on Steam; online title: **warnings expected** | https://store.steampowered.com/app/440/ | about 15 GB | `tf/tf2_*.vpk` multi-part VPK v2, `hl2/*.vpk` | `tf2`; the games pass copies a 0.9 GB subset as `pass-team-fortress-2` |
| Bethesda (`bethesda`) | none verified free. If you own one: Skyrim Special Edition (`Data/*.bsa`, LZ4 entries), Fallout 4 (`Data/*.ba2`) | | | BSA 105 / BA2 | `skyrim-se`, `fallout4` |
| Genie (`genie`) | Age of Empires II HD (owner's copy; any AoE I/II install) | | 5.5 GB | `.drs` archives: SLP graphics to PNG sheets with the game palette, WAV, BINA | `pass-aoe` |
| Warscape (`warscape`) | Total War: Rome II (owner's copy) | | 36 GB | `data/*.pack`: db tables, textures, models, scripts, loc | `pass-total-war-rome-ii` |
| REDengine 4 (`redengine`) | Cyberpunk 2077 (owner's copy) | | 86 GB | `archive/pc/content/*.archive` (RDAR), Kraken via the game's Oodle DLL; names from `cp77-hashes` | `pass-cyberpunk-2077` |
| TaleWorlds (`taleworlds`) | Mount & Blade II: Bannerlord (owner's copy) | | 92 GB | `Modules/*/AssetPackages/*.tpac`: LZ4 segments, textures as DDS | `pass-mount-blade-2-bannerlord` |
| Unity IL2CPP (`unity`) | Schedule I (owner's copy) | | 7.4 GB | IL2CPP player, `global-metadata.dat`, Cpp2IL stubs; the memory ceiling (SQC-SAFE-09) | `pass-schedule-i` |
| Unity IL2CPP (`unity`) | Approximately Up (owner's copy, with BepInEx plugins and a modkit zip) | | 5.5 GB | a second IL2CPP title | `pass-approximately-up-build-25884550` |
| Ren'Py (`renpy`) | Returning to Mia (owner's copy; ships as zipped game data) | | 18 GB | RPA archives inside the zip: JPEG frames, MP3 tracks, decompiled scripts | `pass-zipped-game-data` |
| QuickBMS (`quickbms`) | no title of its own: it serves any archive with a `<ext>.bms` script | | | script bridge | any |
| Overwatch (`overwatch`, OPERATOR) | Overwatch 2 (Blizzard), free to play via Battle.net; terms-of-service-sensitive: **warnings expected**, real-game run by the operator | https://overwatch.blizzard.com | 50 GB+ | CASC data through DataTool (Windows only) | `overwatch` |
| AGS (`ags`), Defold (`defold`), GameMaker (`gamemaker`), LÖVE (`love2d`), TyranoScript (`tyranoscript`), Wolf RPG (`wolfrpg`), XNA/FNA/MonoGame (`xna`) | none verified here: no free title has been checked for these engines | | | the readers and ways back of 04 and 09 run on fixtures only | |
| Android (`android`) | none verified: no APK, bundle or OBB from a store or a build tool has been run (static arm only, no device) | | | APK/bundle/OBB, binary XML, `resources.arsc`, signing | |
| Desktop frameworks (`qt`, `chromium`, `dotnet`, `java`, `pyfrozen`) | none verified as a game here (doc 13.8: the owner's own software is the reference) | | | `.rcc`, Chromium `.pak`, managed resources, jars, PyInstaller | |

Flags (`ctf.json`, `17-ctf.md`)
- With flags, free titles (SQC-CTF-01, eleven): `DDLC-1.1.1-pc`, `freedoom`, `ultrakill-prelude`,
  `baldi-cr`, `BURNING_SNOW_1_0_4`, `voids-cave`, `the-basement`, `rpgmv-first`, `ubu`, `godotone`,
  `godot-mad`.
- With flags, the owner's library through the games pass (SQC-CTF-02, eight): `pass-aoe`,
  `pass-approximately-up-build-25884550`, `pass-schedule-i`, `pass-total-war-rome-ii`,
  `pass-cyberpunk-2077`, `pass-mount-blade-2-bannerlord`, `pass-zipped-game-data`,
  `pass-team-fortress-2`.
- Listed without flags: `godot-first`, `ancient-challenger`, a free `tf2` install, and the
  owner-only or operator rows (`skyrim-se`, `fallout4`, `overwatch`).
- Plugins with no real-game title here at all: Bethesda, QuickBMS, a standalone Electron
  `app.asar` game, RPG Maker XP, AGS, Defold, GameMaker, LÖVE, TyranoScript, Wolf RPG, XNA, Android,
  the desktop frameworks.

Notes
- Prefer the smaller titles first (Freedoom, DDLC, ULTRAKILL Prelude, Godot First, Void's Cave,
  Ancient Challenger, the MV title).
- itch.io pages were read directly for price, platform and "Made with" tags where present.
- Self-extracting downloads (`ancientchallenger.exe`) must be run once by you to unpack the game
  into its slug folder; ViWo never runs them.
