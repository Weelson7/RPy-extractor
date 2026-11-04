# 9. Startup wiring from an ini file

What ViWo loads at startup (OS layer, plugins, which backend is main or spare in each slot, tool
paths, server settings) is declared in one ini file (`viwo/core/wiring/ini.py`,
`viwo/core/wiring/boot.py`). A distro is an ini file. Parsing uses the stdlib `configparser`.

## 9.1 Files and precedence

```
startup.ini                  the active file (default; `viwo --ini PATH` picks another)
distros/<os>-<profile>.ini   twelve generated files (`viwo config generate`)
```

Precedence, lowest to highest:

1. built-in defaults (slot defaults of doc 8.4, plugin defaults);
2. the one `base =` file named in `[startup]` (a single level; chains and loops are errors);
3. the ini itself;
4. global CLI flags: `--os`, `--profile` (that distro's plugin set over the ini's), `--features
   a,b`.

The effective configuration, with the source of every value (`default`, `base`, `ini`, `cli`),
is returned by `viwo --json info` and `GET /api/distro`. `viwo --verbose <command>` also prints it.

## 9.2 Format

```ini
; UTF-8 (a BOM is tolerated). Comments start with ; or #, also inline.
; Booleans: on/off, true/false, yes/no, 1/0. Keys are case-insensitive.

[startup]
contract         = 1.1           ; optional; the major must match this ViWo
base             = distros/windows-mixed.ini
os               = auto          ; auto | linux | windows
profile          = mixed         ; renpy | unity | unreal | godot | custom | mixed
features         = extraction, sorting, merger   ; + capture, analysis (opt-in)
auto_install     = on            ; install missing pinned tools into third_party/ at startup
strict_preflight = off           ; on: `viwo serve` exits 4 when a plugin slot has no backend
av_exclusions    = on            ; workspace, source and temp skip the antivirus during a job

[plugins]
generic     = on                 ; always on
overwatch   = off                ; built-ins are on unless switched off
custom_dirs = user_plugins       ; comma-separated, relative to the ini
hello       = on                 ; drop-ins are opt-in (also custom.<id> = on)

[slots]
; <slot_id> = <main> [, <spare>]      "none" leaves a position empty
unarchive.7z   = sevenzip-cli, py7zr
export.unity   = unitypy, assetstudiomod-cli

[tools]
; <dependency id> = path to the executable (relative to the ini); wins over third_party/
sevenzip = C:/Program Files/7-Zip/7z.exe

[options.quickbms]
scripts = C:/tools/quickbms/scripts   ; plugin options; secrets are refused here

[server]
host      = 127.0.0.1
port      = 8081
workspace = viwo-data/workspace
merged    = viwo-data/merged
logs      = viwo-data/logs
temp      = viwo-data/tmp
```

`profile` in the ini is informational; `--profile` applies a profile's plugin set.

## 9.3 Boot sequence

| # | Step | Failure behaviour |
|---|------|-------------------|
| 1 | `viwo` (or `Start.py` -> `viwo serve`) parses the global flags | usage error: exit 2 |
| 2 | load the ini and its base, validate, apply `--profile` / `--features` | bad file or contract major: exit 2 with the reason |
| 3 | locate `third_party/` next to the ini and activate its Python packages | - |
| 4 | select the OS layer (`auto` = host), check `is_supported_host()` | unsupported: exit 3 |
| 5 | register enabled built-ins, drop-ins and entry-point plugins; run `configure()` | a bad plugin is disabled and listed in the problems |
| 6 | bind slots: defaults + `[slots]`, tools from `[tools]` and `third_party/`, promotion | an unbound slot is a problem, not an error |
| 7 | `viwo serve`: run the preflight (checks; installs when `auto_install = on`), rebind | `strict_preflight = on` and a plugin slot unbound: exit 4 |
| 8 | start the HTTP server | port in use: a clear error |

The web UI's landing screen runs the same preflight as a job (kind `preflight`).

## 9.4 Validation

- Unknown sections or keys in `[startup]` / `[server]`: a problem, then ignored.
- An unknown plugin id, slot id or backend id, or a backend that does not serve the slot's
  family: a problem for that entry only; the default is used (`/api/distro` lists it).
- `contract` with another major: exit 2.
- A key in `[options.*]` containing `key`, `secret`, `password` or `token`: refused with a problem.
- Paths are relative to the ini's folder.
- `viwo config check FILE...` applies the rules strictly (file names of distros, known sections,
  plugins, slots and backends, no secrets) and exits 2 on any problem; a test keeps the generated
  distros in sync with the registry.

## 9.5 Not implemented

`[slot_policy]` (policies other than failover), `[hooks]` lifecycle hooks, and the CLI flags
`--plugin <id>=on|off` / `--slot <slot>=<main>[,<spare>]` are open (CONFORMANCE).

## 9.6 Relationship to the UI

- `GET /api/distro`: the effective ini with sources, the bindings (main, spare, promoted,
  unbound) and the problems.
- 11 SETTINGS edits features, startup switches, plugins, tool paths, options and slots, writes
  `startup.ini` key by key (`viwo/core/wiring/settings.py`) and applies the change by reloading
  the runtime (`App.reload()`); a running job finishes on the bindings it started with. No
  restart.
