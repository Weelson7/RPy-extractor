# 9. Startup wiring from an `.ini` file

What the app loads at startup (OS layer, profile, plugins, which backend is main
or spare in each slot, tool paths, lifecycle hooks) is declared in an
**`.ini` file**. A distro *is* an ini file. Parsing uses Python's stdlib
`configparser`, so no new dependency is needed.

`config.json` keeps the v1 server settings (host, port, paths) without change
(doc 4.5). The ini only controls **what gets wired in**.

> **Prototype scope (after review):** one flat `startup.ini` with `[startup]`, `[plugins]`, `[slots]`, `[tools]`. Deferred until after the prototype: `base =` layering, the 12 shipped distro files, CLI `--slot/--plugin` overrides and lifecycle `[hooks]`. OS and profile stay selectable with `--os/--profile`. The full model below is the target.

## 9.1 Files and precedence

```
RPy-extractor/
  config.json                server + paths (v1, unchanged)
  startup.ini                the active startup file (user-editable)
  distros/
    linux-renpy.ini   windows-renpy.ini
    linux-unity.ini   windows-unity.ini
    linux-unreal.ini  windows-unreal.ini
    linux-godot.ini   windows-godot.ini
    linux-custom.ini  windows-custom.ini
    linux-mixed.ini   windows-mixed.ini
```

Precedence, lowest to highest (proposed):

1. built-in defaults (slot defaults from doc 8.4, plugin defaults)
2. the `base =` file named in `[startup]` (for example `distros/windows-unity.ini`)
3. `startup.ini`, or the file given with `viwo --ini <path>` (`Start.py` passes its flags to `viwo serve`)
4. command-line flags: `--os`, `--profile`, `--plugin <id>=on|off`, `--slot <slot>=<main>[,<spare>]`

Only one level of `base =` is allowed, to avoid include chains. The
**effective** configuration, with the source of every value (default, base,
ini or cli), is logged at boot and returned by `GET /api/distro`.

## 9.2 Format

```ini
; startup.ini: startup wiring for ViWo
; Encoding UTF-8 (a BOM is tolerated). Comments start with ; or #.
; Booleans: on/off, true/false, yes/no, 1/0. Keys are case-insensitive.

[startup]
contract         = 1.0
base             = distros/windows-mixed.ini
OS layer           = auto          ; auto | linux | windows
profile          = mixed         ; renpy | unity | unreal | godot | custom | mixed
features         = extraction, sorting, merger, sanitizer   ; + analysis
auto_install     = off           ; v1 did unpinned installs at boot (F19); off is the new default
strict_preflight = off           ; on = refuse to start if an enabled plugin lacks a REQUIRED dep

[plugins]
generic     = on                 ; always forced on
renpy       = on
unity       = on
unreal      = off
godot       = on
custom_dirs = ./plugins          ; comma-separated
custom.mygame = on               ; custom plugins are opt-in by id

[slots]
; <slot_id> = <main> [, <spare>]      "none" leaves a position empty
unarchive.7z   = sevenzip-cli, py7zr
unarchive.rar  = unrar-cli, sevenzip-cli
unarchive.rpa  = rpa-safe, unrpa
export.unity   = unitypy, assetstudiomod-cli
media.encode   = ffmpeg

[slot_policy]
default        = failover        ; failover | main_only | supplement
; export.unity = supplement   ; post-prototype (D7)

[tools]
; explicit tool locations (ToolLocator step 1, doc 1.2), keyed by DEPENDENCY id
; (one tool can serve several backends, e.g. sevenzip serves four slots)
sevenzip        = C:\Program Files\7-Zip\7z.exe
ghidra          = /opt/ghidra_12.2/support/analyzeHeadless

[options.unreal]
engine_version = UE5.3           ; plugin options; secrets are NOT allowed here

[hooks]
; lifecycle hooks: module:function, resolved inside custom_dirs only
after_plugins =
before_server =
```

## 9.3 Boot sequence (proposed)

| # | Step | Reads | Failure behavior |
|---|------|-------|------------------|
| 1 | `viwo` (or `Start.py` → `viwo serve`) parses `--ini/--os/--profile/...` | argv | usage error → exit 2 |
| 2 | Load ini layers (9.1), validate, build `StartupConfig` | ini files | syntax error → exit 2 with file:line |
| 3 | Load `config.json`, set up logging | config.json | v1 behavior (defaults) |
| 4 | Select OS layer (`auto` = host), check `is_supported_host()` | `[startup] OS layer` | unsupported → exit 3 |
| 5 | Hook `after_os` | `[hooks]` | hook error → warning |
| 6 | Register enabled built-in plugins; discover, validate and register custom plugins | `[plugins]` | bad plugin → disabled, shown in `/api/plugins` |
| 7 | Hook `after_plugins` | | warning |
| 8 | Bind slots: defaults + `[slots]` + `[slot_policy]` + `[tools]`; resolve with `os.tools`; optionally auto-install; promote spares | | unbound slot → warning |
| 9 | Preflight report (dependency statuses, bindings) | | `strict_preflight=on` and a REQUIRED dep missing → exit 4 |
| 10 | Hook `before_server` | | warning |
| 11 | Start the HTTP server | config.json | v1 behavior |
| 12 | Hook `on_shutdown` on Ctrl+C or exit | | ignored |

Exit codes: 0 ok, 2 bad configuration, 3 unsupported OS layer, 4 strict
preflight failed. In v1, a missing unrpa always exits with 1.

## 9.4 Validation rules

- Unknown sections or keys → **warning**, then ignored. This keeps older ini files working.
- Unknown plugin id, slot id or backend id → **error for that entry only**. The default is used instead, and the problem is listed in `/api/distro.problems`.
- A backend bound to a slot whose family it doesn't serve → the same as above.
- `contract` with a different major version → exit 2.
- Values that look like secrets (keys named `*key*`, `*secret*`, `*password*`) in `[options.*]` → refused with a warning. Secrets travel only with requests (doc 4.5).
- Paths are resolved relative to the ini file's own folder.

## 9.5 Lifecycle hooks

```text
hook(ctx: StartupContext) -> None
StartupContext (read-only views): config, OS layer, plugins, bindings, log(message)
hook points: after_os, after_plugins, before_server, on_shutdown
```

- Hooks are resolved only from modules inside `custom_dirs`. That's the same trust boundary as custom plugins (doc 2.8).
- Hooks can read the startup state and log messages. They **cannot** change the bindings. Wiring changes go through the ini, so the effective config stays the one that was logged.
- A hook that raises an error is logged as a warning, and startup continues.

## 9.6 Relationship to the UI

- `GET /api/distro` returns the effective ini (with the source of every value), the bindings (main, spare, promoted, unbound) and any problems.
- Editing the wiring from the UI is planned for later. When it comes, the UI will write `startup.ini`, and the change takes effect after a restart. Nothing is re-wired while the app is running in contract 1.0.
