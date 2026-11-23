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
- Download over HTTPS with `User-Agent: ViWo/<version>`, checked against the pinned size and
  sha256 before use; a mismatch is refused (`refused: checksum mismatch`) and nothing lands.
  A link that drops is picked up where it stopped (a Range request; from the start when the
  server sends the whole file again) for as long as each try brings the file further; three
  tries in a row that do not end it, named by what ended the last (`the connection dropped
  (...)` with "check the connection", or `the server answered HTTP 503 ...` with "the server is
  failing: try again later"). An HTTP error answer is never taken for a drop: a 4xx fails at
  once with its status and a hint (`the URL answers HTTP 404 Not Found (url)`: "the release may
  have moved; report it"); a 5xx is tried again like a drop. A download without a pinned size
  (an indexes release) knows the file is whole from the server's Content-Length or
  Content-Range, else from a body that ends cleanly (or a 416 whose length is what came); a
  body that drops is resumed or ends in a named failure, never returned as a whole file.
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
| dynamic | `renderdoccmd` and `rdpython` (qrenderdoc as the harvest Python), `ue4ss` (Windows), `bepinex` (Windows), `x64dbg` (Windows), `cheatengine` (Windows, Scoop's unpacked build), `mitmproxy` (its portable build), `scylla` (Windows, NtQuery/Scylla 0.9.8, GPL-3.0, the dump-to-patch handoff; the `.rar` release unpacked with 7-Zip), Python `frida-tools`, `soundcard` |
| patching | `keystone` (Windows, `kstool` as a separate process), Python `capstone` |

Versions, licenses and checksums are in `tools.json`; `THIRD_PARTY_NOTICES.md` is generated from
it (`python tools/notices.py`; a test keeps it current).

**The isolation tiers' tools (doc 11.8).** QEMU is pinned and installed on demand like Ghidra
(`viwo install qemu`, never by the startup preflight): it needs no driver and no elevation
(WHPX when Windows offers it, else TCG). The Windows pin is Stefan Weil's build, the one qemu.org
links: `qemu-w64-setup-20260811.exe` (QEMU 11.1.0, GPL-2.0), 206,615,928 bytes, sha256
`f98a8aeb5f7faea9765b6dee28316c266cd179d80354a2fed8e50176f9a2e59f` (checked against the
publisher's sha512), an NSIS installer that 7-Zip unpacks without running it (1.2 GB unpacked).
On Linux the distribution's package is located. A user's own QEMU wins through `VIWO_QEMU` or
`[tools] qemu`. Two pinned packages serve the arm, both with hash locks: **pycdlib** 1.22.0
(LGPL-2.1, imported; `viwo install pycdlib`) writes the read-only CD a QEMU guest gets for a
shared folder, and **Volatility 3** 2.28.2 (Volatility Software License, a worker run as its own
process; `viwo install volatility3`, on demand) finds programs inside a guest from its RAM image.
VirtualBox, LibVMI and `virsh`/`xl` are located, never installed.

**Located-only (unmanaged, doc 16.3).** VirtualBox needs a kernel driver and a one-time
elevation, which the minimal-prompts and third_party-only rules forbid ViWo installing. So ViWo
does not download it: it locates the user's own install (`virtualbox` -> `VBoxManage`). It is not
in `tools.json`. The base-package build the backend targets is recorded for provenance:
VirtualBox 7.2.22-175245 (GPL-3.0 for 7.x; NOT the Extension Pack),
`VirtualBox-7.2.22-175245-Win.exe`, 178,101,352 bytes, sha256
`afd0ff1656cbe04ed88ce619594ae021419d97cce89fa9bdc443e9a963f1713f`.

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
