# 10. Pinned third-party tools

Every third-party tool is pinned in `viwo/data/tools.json` and installed by ViWo into
`third_party/` next to the active `startup.ini` (next to `viwo.exe` in the portable build), and
nowhere else (`viwo/core/thirdparty.py`, `viwo/core/downloads.py`, `viwo/core/workers.py`,
`viwo/core/preflight.py`). The
OS layer only locates tools (doc 1.2). Decision D8: pinned release binaries with checksums, not
vendored sources.

## 10.1 The pin file

```text
tools.json
  tools.<id>      version, license, on_demand?, hidden?, and per OS (windows | linux):
                  url (HTTPS), size, sha256, kind zip|tar|gz|raw|msi|sfx, find (the file to run),
                  argv ({path}, {dotnet}, {java}), needs [ids installed first],
                  from (another entry's folder), mkdir [folders made after install]
  python.<id>     a pip requirement ("UnityPy==1.25.4"); hash lock per platform and CPython in
                  viwo/data/locks/<id>-<os>-<3.x>.txt
  workers.<id>    pip requirements ViWo never imports, a worker script, version, license, on_demand?
```

`sfx` self-extractors are opened by the pinned 7-Zip; `msi` is unpacked with `msiexec /a` (the one
recorded `subprocess` call outside the OS layer). `hidden` entries (the .NET runtime) are not a
dependency of their own. `on_demand` entries (Ghidra, angr) are installed only when asked by name,
or when a feature that needs them is turned on (doc 6.4).

## 10.2 Install

- `viwo install ID...`, `viwo install --all` (everything missing that can be installed),
  `viwo install --game SLUG [--game-version V]` (what an index entry needs, doc 13 and
  `docs/indexes.md`), SYSTEM (INSTALL, INSTALL ALL MISSING), and the startup preflight when
  `auto_install = on` (the default; never `on_demand` entries).
- Download over HTTPS with `User-Agent: ViWo/<version>`, retried when a slow link ends early,
  checked against the pinned size and sha256 before use; a mismatch is refused (`refused:
  checksum mismatch`) and nothing lands.
- Unpack into a temporary folder under `third_party/` with the same member checks as extraction
  (traversal, links), Unix modes applied, then swap into `third_party/<id>/`. A tool that is
  running keeps its folder locked: `busy` with a hint. An antivirus quarantine is reported as a
  failed install with the hint.
- Python pins: `pip install --require-hashes --no-deps --target third_party/python -r <lock>`; no
  lock for this platform and Python means no install, said with the reason
  (`tools/pin_python.py` writes the locks). Not installable in the frozen bundle.
- Worker pins: pip into a fresh `third_party/<id>/`, swapped in, so a pin change never mixes
  versions; run as `python -I viwo/data/workers/<script> --lib third_party/<id>`.
- `[tools]` in the ini wins over `third_party/`, which wins over `PATH`.

## 10.3 Pinned tools

| Group | Pins |
|-------|------|
| archives | `sevenzip` (7-Zip), `unrar`, Python `py7zr`, `unrpa`, `lz4` |
| engines | `repak`, `retoc`, `gdre`, `godotpcktool`, `assetstudiomod` (on the `dotnet` runtime), `unrpyc`, `quickbms`, `datatool` (Windows), `uas` (UnrealAssetScout, Windows), `rpfm-schema-<game>` (RPFM's Total War schemas, data, one per game, on demand), `wolvenkit` (WolvenKit CLI, GPL-3.0, on the `dotnet` runtime), `redscript` (0.5 line, the one with a decompiler; Windows), `cp77-hashes` (WolvenKit path list, data), Python `unitypy` |
| media | `ffmpeg`, `ffprobe`, `vgmstream` |
| analysis | `ghidra` (on demand) and `jdk`, `ilspycmd`, `cpp2il` (Windows), `unluac`, `die`; workers `unicorn`, `angr` (on demand) |
| dynamic | `renderdoccmd` and `rdpython` (qrenderdoc as the harvest Python), `ue4ss` (Windows), `bepinex` (Windows), `x64dbg` (Windows), `cheatengine` (Windows, Scoop's unpacked build), Python `frida-tools`, `soundcard` |
| patching | `keystone` (Windows, `kstool` as a separate process), Python `capstone` |

Versions, licenses and checksums are in `tools.json`; `THIRD_PARTY_NOTICES.md` is generated from
it (`python tools/notices.py`; a test keeps it current).

## 10.4 Rules

1. HTTPS only, official releases (the project's own releases or its author's site; Cheat Engine
   from Scoop's build with Scoop's checksum), size and sha256 from the asset that was tested.
2. Change a version only together with its checksum; then `python tools/notices.py` and the L5
   tests with network access.
3. GPL/AGPL tools run only as separate processes; their backend declares
   `isolation = "subprocess"`.
4. Nothing asks the user anything during install or on a tool's first run: no installer, no
   elevation, no UAC; first-run dialogs are pre-answered off screen (owner's rule).
5. The startup preflight is a job with one event per check and install (`Checking <tool>
   (i/N): found <version>`, `Downloading <file>, KB: x / y`); the landing screen and SYSTEM
   show it.

## 10.5 Updates

`GET /api/updates` (SYSTEM > CHECK FOR UPDATES; never called automatically) reports the latest
ViWo release and the installed and latest per-game indexes. `viwo indexes update` fetches the
newest indexes release (`docs/indexes.md`). Tool pins change only with a ViWo version.
