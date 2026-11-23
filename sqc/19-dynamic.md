# 19 Dynamic arm: debugger, memory, trace, hook, profile, agents, sound

Area code `DYN`. Contract doc 11 (`viwo attach`, `dump`, `trace`, `hook`, `profile`, `agent`,
`record`; RUNTIME). Preconditions: `capture` in `[startup] features` (SETTINGS > FEATURES, or
`--features "extraction,capture"`: quote the list in PowerShell), the tools `viwo install x64dbg
cheatengine frida-tools soundcard ue4ss bepinex`. Nothing in this file may show a first-run dialog:
a dialog is a FAIL (owner's rule). RenderDoc capture is 11-capture; isolation is 22-isolation.

A process of your own to attach to (no game needed), which opens a file twice a second:

```powershell
$p = Start-Process python -ArgumentList '-c','"import time; [time.sleep(0.5) or open(r''C:\sqc\beat'',''w'').close() for _ in range(7200)]"' -PassThru -WindowStyle Hidden; $p.Id
```

`<pid>` below is that id. Attach only to processes you started or own.

## SQC-DYN-01 (P0) Continue in x64dbg, on the game's own process

Steps:
1. Game not running: `viwo attach <repo>\Test-games\chocolate-doom\engine --target chocolate-doom-exe --workspace C:\sqc\_ws\d --confirm`
2. Start the game yourself, then the same command (or RUNTIME > DEBUGGER AND MEMORY > LIST TARGETS > `X64DBG`).

Expected: 1: x64dbg opens with `chocolate-doom.exe - PID ... - Module: ntdll.dll` in its title,
paused at the system breakpoint, the path the game folder's own exe (no copy); no release-notes or
first-run window, also on a fresh `third_party\x64dbg`. 2: x64dbg attaches to the running process
(`attached` in the result is its pid); a byte patched in x64dbg's memory view changes the running
game; both close with ViWo (tracked children).

## SQC-DYN-02 (P0) Continue in Cheat Engine

Steps: as SQC-DYN-01 with `--tool cheatengine-gui` (or `CHEAT ENGINE` in RUNTIME).

Expected: Cheat Engine opens `.runtime\cheatengine-gui\chocolate-doom-exe\chocolate-doom.CT` with no
CEShare setup and no "execute this table's Lua" question; start the game: Cheat Engine attaches to
it within a second (its process label shows the exe).

## SQC-DYN-03 (P0) Memory dump and API trace

Steps:
1. `viwo --features extraction dump --pid <pid> --workspace C:\sqc\_ws\d`
2. `viwo dump --name python.exe --workspace C:\sqc\_ws\d` (several python processes run)
3. `viwo dump --pid <pid> --workspace C:\sqc\_ws\d`
4. `viwo trace --pid <pid> --workspace C:\sqc\_ws\d --functions CreateFileW --seconds 25`
5. The same with `--seconds 8`.

Expected: 1: `viwo: refused: the dynamic arm is off`, hint `add capture to [startup] features in
the ini (SETTINGS)`, exit 3. 2: `viwo: needs_decision: N running process(es) named 'python.exe'`,
hint `give --pid`, exit 2. 3: `{pid, dump: ...\.runtime\dump\<pid>-<stamp>\<pid>.dmp, size,
outputDir}` (tens of MB for a Python process), exit 0. 4: `trace.log` under
`.runtime\trace\<pid>-<stamp>\` with dozens of `CreateFileW` lines (`events` > 0). 5: Frida needs
several seconds to attach: a short run may catch nothing; the result must then say so (an empty
trace is said, never silent).

## SQC-DYN-04 (P0) Unreal runtime agent: mappings and object dump

Steps: `viwo agent <repo>\Test-games\voids-cave --exe "<repo>\Test-games\voids-cave\Void's Cave.exe" --workspace C:\sqc\_ws\ag --timeout 150`;
then `viwo agent <repo>\Test-games\chocolate-doom\engine --exe <game>\chocolate-doom.exe --workspace C:\sqc\_ws\ag2`.

Expected: the game opens windowed (640x360) with no UE4SS console, closes by itself after about
25 s; `finished: true`; `.runtime\agent\ue4ss-agent\` holds `Mappings.usmap` (about 1.3 MB) and
`UE4SS_ObjectDump.txt`; `C:\sqc\_ws\ag.agent-copy` is the patched copy; the game folder hashes are
unchanged. The Doom engine: `viwo: unavailable: no runtime agent for this game (doom)`, hint `Unity
(BepInEx) and Unreal (UE4SS) have one`, no copy made.

## SQC-DYN-05 (P1) Unity IL2CPP runtime agent

Steps: on an IL2CPP game whose files Windows Defender does not hold: `viwo agent <game> --exe
<game>\<Game>.exe --workspace W`.

Expected: windowed, no BepInEx console; `.runtime\agent\bepinex-agent\` holds the interop assemblies
(`Assembly-CSharp.dll` among them) and `LogOutput.log`. A Mono game answers `unavailable: ... a Mono
build`. Files Defender holds are listed under `notCopied`.

## SQC-DYN-06 (P1) Audio loopback

Steps: play any sound; `viwo record --workspace C:\sqc\_ws\d --seconds 5`.

Expected: a WAV `.runtime\audio\loopback-<stamp>.wav`, `peak` above 0. Without a usable soundcard
package: `unavailable` naming what is missing.

## SQC-DYN-07 (P0) Your own hook script (Frida)

Steps:
1. `mods.js` = `Process.enumerateModules().slice(0, 2).forEach(m => console.log(m.name, m.base));`
2. `viwo hook --pid <pid> --script mods.js --seconds 30 --workspace C:\sqc\_ws\d`; after about 15 s
   append `console.log("again");` to `mods.js` and save.
3. `viwo hook --pid 999999 --script mods.js --seconds 10 --workspace C:\sqc\_ws\d`

Expected: 1-2: `Frida loads mods.js into process <pid> for 30 s`, `Save ...mods.js while it runs and
Frida loads it again`; the modules line by line within seconds of the start; after the save the
lines come again with `again`; the run ends by itself (about 30 s + 10 s), the process keeps
running; `N line(s) from mods.js: ...\.runtime\hook\<pid>-<stamp>\hook.log` holds the same lines.
3: `Failed to attach: unable to find process with pid 999999` relayed, `viwo: failed: Frida could
not run mods.js in process 999999`, exit 1, within seconds. The same on a running game (the game
keeps running).

## SQC-DYN-08 (P0) Attach targets, the confirmation and the switch

Steps:
1. `viwo --json attach <repo>\Test-games\chocolate-doom\engine`
2. Delete `viwo-data\capture\confirmed.json`; `viwo attach <game> --target chocolate-doom-exe --workspace C:\sqc\_ws\att`
3. `viwo --features "extraction,analysis" attach <game> --target chocolate-doom-exe --workspace C:\sqc\_ws\att --confirm`

Expected: 1: targets `chocolate-doom-setup-exe` and `chocolate-doom-exe`, each with
`x64dbg-gui/attach.debug`, `cheatengine-gui/attach.memory`, `mitmproxy-gui/attach.net`. 2:
`viwo: needs_decision: confirm before capturing`, the confirmation text as hint (plus `the network
is reachable: go offline before launching if the game allows it`), exit 2, nothing launched. 3:
`viwo: refused: runtime capture is off`, hint `add capture to [startup] features in the ini
(SETTINGS)`, exit 3.

## SQC-DYN-09 (P1) CPU profile

Steps: `viwo profile --pid <pid> --seconds 5 --workspace C:\sqc\_ws\d`; read `hotspots.txt`.

Expected: `{pid, samples, top, outputDir}`; `hotspots.txt` lists `HOT SPOTS`, `MODULES`, `THREADS` as
shares; samples are taken about every millisecond per thread (doc 11.7): a 5 s run of a one-thread
process holds thousands of samples.

## SQC-DYN-10 (P1) Continue in mitmproxy (own traffic)

Steps: RUNTIME > LIST TARGETS on a game > `MITMPROXY`; point the game (or the system proxy) at the
proxy it names.

Expected: mitmproxy's own web interface opens on two free ports of this machine, regular mode; flows
are saved in `.runtime\mitmproxy-gui\<key>\flows.mitm`; what it cannot do alone (the proxy setting,
trusting its certificate) is said; no elevation is asked.

## SQC-DYN-11 (P0) RUNTIME: a run as a job, cancelled from JOBS

Preconditions: `viwo serve` with `capture` on.

Steps: RUNTIME > RUNNING PROCESS: `<pid>`, functions `CreateFileW`, seconds `40`, `TRACE CALLS`;
click the `RUNNING API TRACE` chip; `CANCEL JOB` on that job; then `RECORD SOUND` with no usable
soundcard package.

Expected: the chip `RUNNING API TRACE` links to JOBS, which shows that job with `CANCEL JOB`; the
job ends `CANCELLED` within seconds and `CANCEL JOB` disappears; RECORD SOUND without soundcard:
error box `RECORD FAILED // TOOL NOT INSTALLED`, hint `INSTALL soundcard in SYSTEM →`, `Open SYSTEM
→`, `code: unavailable`.

## Results

| ID | Result | Version | Notes | Tester | Date |
|----|--------|---------|-------|--------|------|
| SQC-DYN-01 | NOT RUN | 1.36.0+search+apk (unreleased) | needs eyes on x64dbg's window and a running game | agent | 2026-11-23 |
| SQC-DYN-02 | NOT RUN | 1.36.0+search+apk (unreleased) | needs eyes on Cheat Engine and a running game | agent | 2026-11-23 |
| SQC-DYN-03 | FAIL (step 5) | 1.36.0+search+apk (unreleased) | steps 1-4 PASS on a Python process of my own (dump 43,506,673 bytes; trace 90 events in 25 s). Step 5: an 8 s trace answered `events: 0` with an empty `trace.log` and no warning. Dump, trace and profile print no progress line at all (their job log in JOBS reads `this job wrote no log lines`) | agent | 2026-11-23 |
| SQC-DYN-04 | PASS (no-agent step) / NOT RUN (Unreal) | 1.36.0+search+apk (unreleased) | the Doom engine answer as written, no copy made; no Unreal game installed here | agent | 2026-11-23 |
| SQC-DYN-05 | NOT RUN | 1.36.0+search+apk (unreleased) | needs a Unity IL2CPP game | agent | 2026-11-23 |
| SQC-DYN-06 | BLOCKED | 1.36.0+search+apk (unreleased) | the pinned soundcard here sits in a `third_party\python` built for another CPython (numpy does not import under 3.10): `viwo: unavailable: audio capture needs soundcard` while `viwo slots` lists soundcard `found` | agent | 2026-11-23 |
| SQC-DYN-07 | PASS (own process) / NOT RUN (game) | 1.36.0+search+apk (unreleased) | lines 4 s after the start; the save reloaded the script (twice: one save, two change events); bad pid refused with Frida's words in about 3 s | agent | 2026-11-23 |
| SQC-DYN-08 | PASS | 1.36.0+search+apk (unreleased) | Chocolate Doom engine folder. The attach-off message says `runtime capture is off` where dump says `the dynamic arm is off` | agent | 2026-11-23 |
| SQC-DYN-09 | FAIL | 1.36.0+search+apk (unreleased) | 24 samples in 5 s (one thread). Each round lists the system's threads (`viwo/os/_win_probe.py` 77, `threads_of`): 170 ms per call here, so about 5 rounds a second, not one a millisecond | agent | 2026-11-23 |
| SQC-DYN-10 | NOT RUN | 1.36.0+search+apk (unreleased) | needs a game with web traffic and eyes on mitmproxy | agent | 2026-11-23 |
| SQC-DYN-11 | FAIL | 1.36.0+search+apk (unreleased) | headless Edge: the chip read `RUNNING API TRACE` and linked to `#jobs`, but JOBS showed an older job (the latest when the page loaded), `CANCEL JOB` hidden; after picking the running row by hand `CANCEL JOB` showed, the job was `CANCELLED` in 1 s and the button went. RECORD SOUND box as written | agent | 2026-11-23 |
