# 1. Kernel contract (Linux / Windows)

The kernel is the **only** layer that may contain OS-specific code. It is
split into five small parts so each one can be faked in tests and replaced on
its own.

```text
Kernel
  kernel_id        "linux" | "windows"
  display_name
  is_supported_host() -> bool
  process : ProcessRunner
  tools   : ToolLocator
  installer : PackageInstaller
  shell   : DesktopShell
  fs      : FileSystemPolicy
```

## 1.1 ProcessRunner

```text
max_command_length -> int
python_executable  -> str
run(argv, *, cwd=None, env=None, timeout=None, cancel=None) -> ProcessResult
ProcessResult { returncode, stdout, stderr, timed_out, ok }
```

- Output is always decoded as UTF-8 with `errors=replace`, the same as v1 `runtime.run` and `startup.run`.
- `run` never raises because of a non-zero exit code. It raises `FileNotFoundError` only when the program can't be started at all.
- On timeout or cancel, `run` kills the **whole process tree**. Ghidra, AssetRipper and umodel all start child processes. On Windows this uses a job object or `taskkill /T`; on Linux, a process group.
- `max_command_length` is 32767 on Windows (the CreateProcess limit) and derived from `ARG_MAX` on Linux. Code that builds long command lines, such as the ffmpeg filtergraph in the merger, must check this value and switch to file-based arguments when it's exceeded. That's the general fix behind the v1 commit "Fix media merger WinError 206".

## 1.2 ToolLocator

```text
locate(spec: DependencySpec) -> ToolLocation | None      # no side effects
known_install_dirs(spec) -> [Path]
status(spec, owner) -> DependencyStatus
ToolLocation { dep_id, path, argv_prefix, source: path|known_dir|env|python|config }
```

`argv_prefix` is what goes in front of the tool's own arguments. Examples:
`[python, -m, unrpa]`, `["C:\\Program Files\\7-Zip\\7z.exe"]`, and
`["cmd", "/c", "...\\analyzeHeadless.bat"]`.

Search order (proposed):

1. user config override (`config.json` → `tools.<dep_id>`)
2. `spec.env_var` (for example `GHIDRA_INSTALL_DIR`)
3. `PATH`, trying each name from `spec.executable_candidates(kernel_id)`, with the kernel adding `.exe`, `.bat` and `.cmd` itself on Windows
4. `known_install_dirs`

| | Windows kernel | Linux kernel |
|--|--|--|
| known dirs | `%ProgramFiles%`, `%ProgramFiles(x86)%`, scoop `apps/*/current`, chocolatey `lib/*/tools`, `%LOCALAPPDATA%\Programs` | `/usr/bin`, `/usr/local/bin`, `/opt/*`, `~/.local/bin`, flatpak exports |
| python module | `python -m <module>` / import check | same |

> Fixes v1 F4: `startup._check_7zip_installed` finds 7-Zip in Program Files
> and reports it as available, but `extraction_core.archive` only looks in
> `PATH`, so `.7z` extraction then fails. With this contract, one locator is
> used for both the status check and actual tool calls.

## 1.3 PackageInstaller

```text
available_installers() -> [installer_id]      # preference order
install(spec) -> InstallOutcome { dep_id, attempted, ok, installer, detail }
install_hint(spec) -> str
```

- **Windows:** `pip`, then `winget`, `choco`, `scoop` (the same chain as v1 `install_7zip_best_effort`).
- **Linux:** `pip` (with a `--user` fallback, as in v1 `ensure_python_module`). System packages (`apt`, `dnf`, `pacman`) **only get a hint**.
- The installer never asks for elevated privileges (no sudo, no UAC prompt). When that would be needed, it returns `attempted=false` with a hint.
- It only runs when the distro has `auto_install=true`.

## 1.4 DesktopShell

```text
open_folder(path) -> (ok, error)
pick_folder(title, initial) -> Path | None
pick_file(title, initial, file_types) -> Path | None
```

- These replace v1 `common.open_folder_in_explorer` (`os.startfile` / `open` / `xdg-open`) and the `tkinter` dialogs in `session_handlers.browse_folder` and `media_merger_handlers.browse_overlay_sound`.
- On a headless host they may return `None`. The UI already falls back to typing a path.
- Linux dialog fallback order: tkinter, then `zenity`, then `kdialog`, then `None`.

## 1.5 FileSystemPolicy

```text
case_sensitive -> bool
path_key(path) -> str                 # dedupe key; casefolded on Windows
sanitize_filename(raw, fallback) -> str
is_valid_filename(name) -> bool       # used for sorting-window rename
long_path(path) -> Path               # \\?\ prefix on Windows
```

Windows rules: no `\ / : * ? " < > |` or control characters, no trailing dot
or space, no reserved names (`CON`, `NUL`, `COM1`…), and names of at most 255
characters. Linux rules: no `/` or NUL, and not `.` or `..`.

This replaces three different v1 rules: Unity `exporters._safe_name`, the
sorting rename check (`"/" in name or "\\" in name or ":" in name`), and the
merger's `_safe_output_name`.

## 1.6 What changes between the kernels

| Concern | Windows kernel | Linux kernel |
|--|--|--|
| Game layouts seen | `.exe`, `*_Data`, `UnityPlayer.dll`, `*-Win64-Shipping.exe` | `.x86_64`, `.sh`, `UnityPlayer.so`, Proton prefixes (`steamapps/compatdata`) holding Windows builds |
| Case sensitivity | insensitive | **sensitive**, so engine markers must be matched case-insensitively through the GameProbe (v1 F2) |
| Executable suffix | `.exe`, `.bat`, `.cmd` added automatically | none; the executable bit is checked |
| Command line limit | 32767 | large |
| Open folder | `os.startfile` | `xdg-open` |
| Installers | pip, winget, choco, scoop | pip; others hint-only |

## 1.7 Conformance checks (every kernel must pass)

- `max_command_length > 0`.
- `sanitize_filename` returns a name that passes `is_valid_filename` for a fixed set of bad inputs: empty, `.`, `..`, `CON`, `nul.txt`, `a/b`, `a\b`, `x:y`, trailing dots or spaces, control characters, NUL, Unicode, and 300-character names.
- `path_key` returns the same key for the same path, and on a case-insensitive filesystem it ignores case.
- `locate()` never installs or downloads anything. Tests check this with a recording fake installer.
