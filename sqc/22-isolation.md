# 22 Isolation sessions (`viwo isolate`, `/api/runtime/isolation`, RUNTIME)

> Covers v1.36.0; the isolation arm is being extended by the owner and this file is revised when
> that lands.

Area code `ISO`. Contract doc 11.8 (`viwo/core/isolation/session.py`, `live.py`, `qemu.py`,
`qemu_session.py`, `viwo/cli_isolate.py`, `viwo/api/handlers_isolation.py`, RUNTIME > ISOLATION
PATCHER). A session boots a guest behind a tier and leaves it running; every other action rejoins
it from the record `<ws>\.runtime\isolation\session.json`. The guest image is never written (a
qcow2 overlay beside the session takes every change). A live patch is the cold patch set's located
offset written at its virtual address under suspend, write, verify, resume, and journalled.

Preconditions: QEMU (`viwo install qemu`, or `VIWO_QEMU` / `[tools] qemu =` pointing at your own
`qemu-system-x86_64.exe`; `qemu-img.exe` beside it gives the kept overlay). No guest operating
system is needed: a 512-byte boot sector that spins in place, with a marker the BIOS loads at
`0x7C10`, and a "program" file holding the same marker at the same offset (outside a PE a patch
set's offset is its address):

```powershell
mkdir C:\sqc\_iso\prog
python -c "s=bytearray(512);s[0:2]=b'\xeb\xfe';s[16:36]=b'VIWO-MARK-0123456789';s[510:512]=b'\x55\xaa';open(r'C:\sqc\_iso\boot.img','wb').write(bytes(s)+bytes((1<<20)-512))"
python -c "d=bytearray(0x8000);d[0x7c10:0x7c24]=b'VIWO-MARK-0123456789';open(r'C:\sqc\_iso\prog\raw.bin','wb').write(d)"
Set-Content -Encoding ascii C:\sqc\_iso\mark.patch.json '{"schema": 1, "title": "mark", "patches": [{"file": "raw.bin", "offset": "0x7c10", "original": "56 49 57 4F 2D 4D 41 52", "patched": "50 41 54 43 48 45 44 21"}]}'
(Get-FileHash C:\sqc\_iso\boot.img).Hash > C:\sqc\_iso\boot.sha
```

Always pass `--tier qemu`: with VirtualBox installed the default (the first ready tier by number)
is T1 VirtualBox, which registers a VM. Always `viwo isolate stop` what you start. Terminal 1 holds
the session; the other steps run in terminal 2.

## SQC-ISO-01 (P0) The tiers and their readiness

Steps: `viwo isolate`; `viwo --json isolate --list`.

Expected: `tiers` lists `isolation.qemu` / `qemu` (tier 2), `isolation.vbox` / `vbox` (tier 1),
`isolation.vmi` / `libvmi` (tier 3), each with `requirement`, `ready`, `wall`, `detail`; QEMU
`ready: true` when found; on Windows libvmi `ready: false`, `wall: "not_ready"`, detail `a
bare-metal Linux KVM/Xen host with DRAKVUF/LibVMI (not available on Windows)`; VirtualBox ready only
when `VBoxManage` is found. Exit 0. Listing needs no workspace and no feature switch.

## SQC-ISO-02 (P0) Requests that cannot run are refused by name

Steps:
1. `viwo isolate status`
2. `viwo isolate status --workspace C:\sqc\_ws\iso`
3. `viwo isolate frobnicate --workspace C:\sqc\_ws\iso`
4. `viwo isolate start --tier nope --image C:\sqc\_iso\boot.img --workspace C:\sqc\_ws\iso`

Expected: 1: `viwo: invalid_request: give --workspace <folder>`, exit 2. 2: `viwo: not_found: no
isolation session runs in this workspace (none was started here)`, exit 1. 3: `not_found:
executable not found: frobnicate`, hint `or an action name` (anything not an action is the one-shot
form's executable), exit 1. 4: `invalid_request: no isolation tier 'nope'`, hint `vbox|qemu|libvmi`,
exit 2.

## SQC-ISO-03 (P0) Start a TCG session that holds; status, pause, resume; one session per workspace

Steps:
1. Terminal 1: `viwo isolate start --tier qemu --image C:\sqc\_iso\boot.img --workspace C:\sqc\_ws\iso --headless --memory 64 --cpus 1 --accel tcg --snapshot`
2. Terminal 2: `viwo --json isolate status --workspace C:\sqc\_ws\iso`; then `pause`, `status`, `resume`.
3. Terminal 2: the command of step 1 again.

Expected:
- 1: `QEMU disk: new overlay on the raw image; the image itself is not written`, `QEMU started on
  tcg; network closed; control on loopback`, `Isolation session is up; viwo isolate stop (or
  closing the guest) ends it`; the command keeps running; `session.json` (tier, qmp and gdb ports,
  accel, pid, image) and `qemu\overlay.qcow2` appear under `C:\sqc\_ws\iso\.runtime\isolation\`.
  No window opens (headless).
- 2: `running: true`, `accel: "tcg"`; after `pause` `running: false` (also in `status`); after
  `resume` `running: true`.
- 3: `viwo: busy: a session already runs in this workspace`, hint `isolate stop`, exit 1.

## SQC-ISO-04 (P0) Live patch, journal, dump, undo, snapshot and rollback

Preconditions: the session of SQC-ISO-03 runs.

Steps (terminal 2, workspace `C:\sqc\_ws\iso`):
1. `viwo --json isolate snapshot --name clean --workspace C:\sqc\_ws\iso`
2. `viwo --json isolate patch --exe C:\sqc\_iso\prog\raw.bin --patchset C:\sqc\_iso\mark.patch.json --workspace C:\sqc\_ws\iso`; read `.runtime\isolation\journal.jsonl`.
3. `viwo isolate dump --name p1 --workspace C:\sqc\_ws\iso`; `viwo search C:\sqc\_ws\iso\.runtime\isolation\dumps\p1.elf --text "PATCHED!K-0123" --quiet`
4. `viwo --json isolate undo --workspace C:\sqc\_ws\iso`; dump `u1`; search `u1.elf` for `VIWO-MARK-0123`.
5. The patch of step 2 again; `viwo --json isolate rollback --name clean --workspace C:\sqc\_ws\iso`; dump `r1`; search `r1.elf` for `VIWO-MARK-0123`.
6. `viwo isolate dump --name ../x ...`; `viwo isolate rollback --name nosuch ...`

Expected:
- 1: `{"tier": "qemu", "action": "snapshot", "snapshot": "clean"}`.
- 2: `written: true`, `journalled: 1`, the result `ready`, `wall: "none"`; the journal holds one line
  `{"addr": 31760, "old": "5649574f2d4d4152", "new": "5041544348454421", ...}` (`0x7C10`).
- 3: the dump `p1.elf` is the guest RAM as an ELF core (about 84 MB for 64 MB of RAM); the search
  finds 1 hit of `PATCHED!K-0123`.
- 4: `restored: 1, edits: 1`, the journal file is gone; `u1.elf` holds the marker again (1 hit).
- 5: `rollback: "clean"`; `r1.elf` holds the marker (1 hit).
- 6: `invalid_request: a dump name is letters, digits, _ . -` (exit 2); `failed: Error: Snapshot
  'nosuch' does not exist in one or more devices` (QEMU's words, exit 1).

## SQC-ISO-05 (P0) Stop; the image untouched; the overlay kept

Steps: `viwo --json isolate stop --workspace C:\sqc\_ws\iso`; then `status`; compare
`(Get-FileHash C:\sqc\_iso\boot.img).Hash` with `boot.sha`; list `.runtime\isolation\`.

Expected: `stopped: true`; terminal 1 ends with its JSON (`started: true`, ..., `ended: "guest"`),
exit 0; `status` answers `not_found` as in SQC-ISO-02 step 2; no `qemu-system-x86_64` process left;
the image hash unchanged; `qemu\overlay.qcow2` and `dumps\` kept; `session.json` gone.

## SQC-ISO-06 (P1) Hardware acceleration and what it cannot do

Steps: terminal 1: the start of SQC-ISO-03 without `--accel tcg` and without `--snapshot`; terminal 2:
`status`; `viwo isolate snapshot --name s1 --workspace C:\sqc\_ws\iso`; `patch` as in SQC-ISO-04;
`undo`; `stop`.

Expected: `QEMU disk: overlay kept from before (overlay.qcow2)`; `QEMU started on whpx` (Windows with
the Windows Hypervisor Platform; `kvm` on Linux; else `tcg` and the reason said); `snapshot` answers
`viwo: unavailable: this accelerator cannot save state (WHPX): start the session with a snapshot or
TCG`, exit 1; the live patch is written under WHPX; `undo` restores it; `stop` ends terminal 1.

## SQC-ISO-07 (P1) `--fresh` and the one-shot form

Steps:
1. `viwo isolate C:\sqc\_iso\prog\raw.bin --patchset C:\sqc\_iso\mark.patch.json --tier qemu --image C:\sqc\_iso\boot.img --workspace C:\sqc\_ws\iso2 --headless --memory 64 --cpus 1 --accel tcg`
2. Terminal 1: the start of SQC-ISO-03 with `--fresh`; terminal 2: `stop`.

Expected: 1: one command starts the guest, writes the set (`written: true`, result `ready`, `wall:
none`) and closes it: exit 0, no QEMU process left, no `session.json` left in `iso2`. 2: `QEMU disk:
new overlay on the raw image` (the kept overlay discarded).

## SQC-ISO-08 (P0) API: `GET` and `POST /api/runtime/isolation`

Preconditions: `viwo serve`; an active workspace (say `C:\sqc\_ws\api1`). Calls with the token.

Steps:
1. `GET /api/runtime/isolation`
2. `POST {"action": "status"}`; `POST {"action": "start", "memory": "lots"}`; `POST {"action": "start", "tier": "nope", "image": "C:\\sqc\\_iso\\boot.img"}`
3. `POST {"action": "start", "tier": "qemu", "image": "C:\\sqc\\_iso\\boot.img", "memory": 64, "cpus": 1, "headless": true, "accel": "tcg", "snapshot": true}`; then `{"action": "status"}`; the same start again.
4. `POST {"action": "patch", "exePath": "C:\\sqc\\_iso\\prog\\raw.bin", "patchSet": "C:\\sqc\\_iso\\mark.patch.json"}`; `{"action": "undo"}`; `{"action": "stop"}`
5. `POST {"tier": "qemu", "image": "...", "exePath": "C:\\nope.exe"}` (no action: the one-shot form)

Expected: 1: `{success, tiers, enabled}` (the three tiers of SQC-ISO-01; `enabled` mirrors the
`capture` switch, which isolation does not need). 2: `not_found` (no session), `invalid_request`
`pid, base, memory and cpus must be numbers`, `invalid_request` `no isolation tier 'nope'`. 3:
`started: true`, `accel: "tcg"`, the server owns the guest; `running: true`; then `busy`. 4: `written:
true`, `journalled: 1`; `restored: 1`; `stopped: true`; no QEMU process left. 5: `not_found`
`Executable not found`, hint `an absolute path`. Every failure is a `[FAILED] POST
/api/runtime/isolation: ...` line in the log.

## SQC-ISO-09 (P0) RUNTIME > ISOLATION PATCHER

Preconditions: `viwo serve`; no session in the active workspace.

Steps: DYNAMIC arm > RUNTIME, panel `ISOLATION PATCHER`.
1. Read the panel; `LIST TIERS`.
2. `STATUS`.
3. Empty `GUEST DISK IMAGE`, `START`.
4. `GUEST DISK IMAGE` `C:\sqc\_iso\boot.img`, `START`; `STATUS`; `PAUSE`; `RESUME`; `SNAPSHOT`;
   `ROLLBACK`; `UNDO`; `STOP`.

Expected:
- 1: badge `COLD + LIVE`, the note (image never written, no network unless asked, the same patch set
  written live and journalled, `viwo isolate` has every option); buttons `LIST TIERS`, `BROWSE`,
  `START STATUS PAUSE RESUME SNAPSHOT ROLLBACK UNDO STOP`. The table: `T2 qemu READY —`, `T1 vbox
  READY —` (when VirtualBox is installed), `T3 libvmi NOT READY a bare-metal Linux KVM/Xen host with
  DRAKVUF/LibVMI (not available on Windows)`.
- 2: error box `STATUS FAILED // NOT FOUND`, `no isolation session runs in this workspace (none was
  started here)`, `code: not_found`.
- 3: toast `NOTE Enter the guest disk image first.`; nothing starts.
- 4: the panel's key/values follow each action (`STARTED true`, `TIER`, `ACCEL`...; `RUNNING
  false/true`; `SNAPSHOT base`; `ROLLBACK base`; `RESTORED`, `EDITS`; `STOPPED true`). START from the
  UI always asks for a base snapshot (so it runs on TCG), with the default 4096 MB and 2 CPUs and a
  guest window (the UI has no headless, memory or CPU fields; the CLI has them). With VirtualBox
  installed and no tier field, START picks the first ready tier: check which tier answers before
  running step 4 on a machine with VirtualBox.

## Results

| ID | Result | Version | Notes | Tester | Date |
|----|--------|---------|-------|--------|------|
| SQC-ISO-01 | PASS | 1.36.0+search+apk (unreleased) | QEMU 11.1 of the pinned set via `[tools] qemu`; VirtualBox 7.2.22 installed here, so `vbox` is ready too | agent | 2026-11-23 |
| SQC-ISO-02 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-ISO-03 | PASS | 1.36.0+search+apk (unreleased) | `busy` exits 1 | agent | 2026-11-23 |
| SQC-ISO-04 | PASS | 1.36.0+search+apk (unreleased) | dump 84,018,259 bytes; each state checked by searching the dump. Seen: after `rollback` the journal still holds the rolled-back edit (it survives `stop`; the next session's `undo` then reports `restored: 2, edits: 2`) | agent | 2026-11-23 |
| SQC-ISO-05 | PASS | 1.36.0+search+apk (unreleased) | image hash unchanged, overlay 2.5 MB kept | agent | 2026-11-23 |
| SQC-ISO-06 | PASS | 1.36.0+search+apk (unreleased) | started on `whpx`; snapshot refused as written; patch and undo written under WHPX | agent | 2026-11-23 |
| SQC-ISO-07 | PASS | 1.36.0+search+apk (unreleased) | the one-shot also prints `Isolation session is up; viwo isolate stop ... ends it` though it closes by itself | agent | 2026-11-23 |
| SQC-ISO-08 | PASS | 1.36.0+search+apk (unreleased) | live server on port 8192 | agent | 2026-11-23 |
| SQC-ISO-09 | PASS (steps 1-3) / NOT RUN (step 4) | 1.36.0+search+apk (unreleased) | steps 1-3 in headless Edge; step 4 NOT RUN: the UI's START opens a 4 GB guest with a window and no tier choice (VirtualBox is installed here, which must not be started), needs a person | agent | 2026-11-23 |
