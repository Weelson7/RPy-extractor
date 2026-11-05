# 1. OS layer (Linux / Windows)

The OS layer is the only layer with OS-specific code (`viwo/contracts/os.py`, implemented by
`viwo/os/linux.py`, `viwo/os/windows.py` and their shared base `viwo/os/_shared.py`). macOS has no
OS layer (D6). Each part can be faked in tests.

```text
OS
  os_id                  "linux" | "windows"
  is_supported_host() -> bool         (boot exits 3 when false)
  process : ProcessRunner
  tools   : ToolLocator
  fs      : FileSystemPolicy
  shell   : DesktopShell
  config_home() / data_home() -> Path  per-user homes (APPDATA / LOCALAPPDATA; XDG on Linux)
  exclude_from_scan(paths) -> (added, note);  include_in_scan(paths) -> bool
  pids_of(image) -> [pid];  dump_process(pid, out) -> Path;  pid_alive(pid) -> bool
```

## 1.1 ProcessRunner

```text
max_command_length -> int            Windows 32767; Linux from SC_ARG_MAX
python_executable  -> str
run(argv, cwd=None, timeout=None, cancel=None, env=None, on_line=None) -> ProcessResult
launch(argv, cwd=None, env=None) -> Child { pid, alive(), kill() }
running_images() -> {lowercase image names}
ProcessResult { returncode, stdout, stderr, timed_out, ok }
```

- Output is decoded as UTF-8 with `errors=replace` and read through pump threads; `run` returns
  when the process exits even if a grandchild still holds the pipes.
- `run` never raises for a non-zero exit; it raises `FileNotFoundError` only when the program
  cannot start. `on_line` receives every output line as it arrives (tool progress events).
- Timeout or cancel kills the **whole process tree** (Windows `taskkill /T /F`; Linux a process
  group and `SIGKILL`) and returns `timed_out=True`.
- `launch` starts a GUI tool or a game as a tracked child (handoffs, doc 8.3a; capture and agents,
  doc 11) and returns at once; every launched child is killed when ViWo exits.
- Code that builds long command lines (the merger's ffmpeg filtergraph) checks
  `max_command_length` and switches to file arguments when it is exceeded.

## 1.2 ToolLocator

```text
locate(spec: DependencySpec) -> ToolLocation | None      no side effects, never installs
known_install_dirs(spec) -> [Path]
ToolLocation { dep_id, argv_prefix, path, source: config|env|python|path|known_dir }
```

`argv_prefix` goes in front of the tool's own arguments: `["C:\...\7z.exe"]`, `["cmd", "/c",
"call", "...\analyzeHeadless.bat"]` (batch files; `call` keeps a quoted path with spaces), or a
runtime prefix such as `dotnet <dll>` / `java -jar <jar>` for pinned tools.

Search order:

1. overrides: the ini `[tools]` section, then tools installed in `third_party/` (the boot merges
   both; `[tools]` wins);
2. `spec.env_var`;
3. Python dependencies: an import check, invoked as `python -m <module>`;
4. `PATH`, each name of `spec.executables_for(os_id)`, with `.exe`, `.bat`, `.cmd` added on
   Windows;
5. `known_install_dirs`: Windows `%ProgramFiles%`, `%ProgramFiles(x86)%`, `%LOCALAPPDATA%\Programs`,
   `%LOCALAPPDATA%`, `%ProgramData%`, scoop `apps/*/current` and `shims`, chocolatey; Linux
   `/usr/bin`, `/usr/local/bin`, `/opt/*`, `~/.local/bin`, flatpak exports.

One locator serves both the status report and the tool calls.

## 1.3 Installation is not an OS-layer concern

Pinned downloads live in core (`viwo/core/thirdparty.py`, doc 10). The OS layer never installs,
never asks for elevation and never runs a package manager.

## 1.4 DesktopShell

```text
open_folder(path) -> (ok, error)                       Windows os.startfile; Linux xdg-open
pick_folder(title, initial) -> Path | None             tkinter
pick_file(title, initial, patterns) -> Path | None     tkinter
```

On a headless host the pickers return `None` and the UI falls back to a typed path.

## 1.5 FileSystemPolicy

```text
case_sensitive -> bool
path_key(path) -> str                 dedupe key; casefolded on Windows
sanitize_filename(raw, fallback) -> str
is_valid_filename(name) -> bool       sorting-window rename, merger output names
long_path(path) -> Path               \\?\ prefix on Windows
```

Windows rules: no `\ / : * ? " < > |` or control characters, no trailing dot or space, no reserved
names (`CON`, `NUL`, `COM1`...), at most 255 characters. Linux rules: no `/` or NUL, not `.` or `..`.
Every filename ViWo makes from untrusted text goes through this policy; member paths from
archives go through `contracts.workspace.safe_member` and `inside` (doc 7).

## 1.6 What differs between the OS layers

| Concern | Windows | Linux |
|---------|---------|-------|
| Game layouts | `.exe`, `*_Data`, `UnityPlayer.dll`, `*-Win64-Shipping.exe` | `.x86_64`, `.sh`, `UnityPlayer.so`, Proton prefixes holding Windows builds |
| Case | insensitive | sensitive: the GameProbe matches names case-insensitively and returns case-preserved paths |
| Executable suffix | `.exe`, `.bat`, `.cmd` added | none |
| Process list | Toolhelp32 snapshot (non-ASCII names) | `/proc` |
| Memory dump | `MiniDumpWriteDump` (full minidump); a failed dump leaves no file | readable `/proc/<pid>/mem` mappings plus `regions.json` |
| Scan exclusions | Windows Defender cmdlets, only when ViWo runs elevated; otherwise one note and scanning stays on | no-op |

## 1.7 Conformance (`tests/test_os_layer.py`, both filesystem policies run on any host)

- `max_command_length > 0`.
- `sanitize_filename` returns a name that passes `is_valid_filename` for: empty, `.`, `..`, `CON`,
  `nul.txt`, `a/b`, `a\b`, `x:y`, trailing dots or spaces, control characters, NUL, Unicode, and
  300-character names.
- `path_key` is stable for one path and ignores case on a case-insensitive filesystem.
- `locate()` never installs or downloads anything.
