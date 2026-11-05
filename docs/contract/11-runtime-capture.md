# 11. Dynamic arm

Work that runs or attaches to the game: GPU frame capture, runtime agents, memory dumps, API
traces, audio loopback, and the debugger and memory-editor attach tools (`viwo/core/capture/`,
`viwo/contracts/runtime.py`, `viwo/cli_dynamic.py`, `viwo/api/handlers_capture.py`). CLI arm
`viwo dynamic`: `capture`, `dump`, `trace`, `profile`, `agent`, `record`, `attach`. UI:
CAPTURE, RUNTIME.

## 11.1 Model: warnings and one opt-in, no gate (D22)

ViWo refuses nothing because of what a game is or what the user intends. The arm is off until
the user switches it on; what it knows about a game is said as warnings.

| Step | Applies to | Result |
|------|------------|--------|
| `capture` in `[startup] features` (SETTINGS) | capture, dump, trace, profile, agent, record, attach | off by default; off answers `refused` with the hint to enable it |
| confirmation once per game folder (`--confirm`, the UI checkbox or confirm box; remembered in `viwo-data/capture/confirmed.json`) | capture, attach | without it: `needs_decision` with the confirmation text (exit 2) |
| anti-cheat markers in the game folder, an anti-cheat service running, a title on the online/competitive list, a `tos_sensitive` plugin detected, the network reachable | capture, attach | warnings in the result and the log; never a refusal |

The markers, services and titles are data (`viwo/data/capture_policy.json`, extended by pull
request), used only to word the warnings. `POST /api/capture/warnings` returns them before a
capture. The executable must be a file inside the game folder (the warnings cover that folder).

ViWo authors no anti-cheat evasion and no copy-protection defeat. The debugger and memory
attach tools (11.2) need only the `capture` switch, never `analysis`.

## 11.2 What ships

| Kind | Slot / backend | Tool | What it does | Output |
|------|----------------|------|--------------|--------|
| capture (D1) | `capture.gpu` / `renderdoc` | RenderDoc 1.47 (`renderdoccmd`, `qrenderdoc --py`) | runs the game as a tracked child of `renderdoccmd capture -w`; unattended by default: `rd_trigger.py` takes one frame after `--auto SECONDS` (default 30) and the tree is stopped; `--auto 0` = attended (F12 / PrtScn, then quit); `rd_harvest.py` turns every capture into PNG textures and shader disassembly (both scripts live in `viwo/data/renderdoc/`, outside the package, so `import renderdoc` finds RenderDoc's module, never ViWo's) | collected into the workspace groups with provenance `capture:<backend>:<stamp>`; files static extraction already produced are not stored twice; run record `capture-<stamp>.json` |
| agent (D2) | `runtime.unreal` / `ue4ss-agent` | UE4SS 3.0.1 | GUI console and bundled mods off; a ViWo Lua mod writes `Mappings.usmap` and `UE4SS_ObjectDump.txt`, then a done file | `.runtime/agent/ue4ss-agent/` |
| agent (D2) | `runtime.unity` / `bepinex-agent` | BepInEx 6 be.785 (IL2CPP) | console off; the first start generates the interop assemblies (BepInEx downloads its Unity base libraries: `network = "download"`) | `.runtime/agent/bepinex-agent/` (interop `*.dll`, `LogOutput.log`) |
| record (D2) | `soundcard-loopback` (no slot) | soundcard (WASAPI loopback, PulseAudio monitor) | `--seconds` of the default output device, 16-bit WAV | `.runtime/audio/loopback-<stamp>.wav` |
| dump (D3) | OS layer `dump_process` | Windows `MiniDumpWriteDump`; Linux `/proc/<pid>/mem` | a full dump of a running process (`--pid` or `--name`) | `.runtime/dump/<pid>-<stamp>/` |
| trace (D3) | `frida-trace` (no slot) | frida-tools 14.11.0 / frida 17.25.2 | `frida-trace -p <pid> -i <glob>...` for `--seconds` | `.runtime/trace/<pid>-<stamp>/trace.log` |
| attach (D3) | `attach.debug` / `x64dbg-gui` | x64dbg (GPL-3, a separate process) | Continue in x64dbg (doc 8.3a) on the game's own process: attached to the one process running the target's executable (or `--pid`), else the game's own executable started under the debugger; a patch made live lands in the real process | - |
| attach (D3) | `attach.memory` / `cheatengine-gui` | Cheat Engine 7.6 | Continue in Cheat Engine with a ViWo table that attaches to the game | `.runtime/cheatengine-gui/<key>/<exe>.CT` |

A name matching several running processes answers `needs_decision` (give `--pid`).

**Attach** (`core/capture/attach.py`): the targets are the plugins' analysis targets (doc 6.1)
that an `attach.*` tool accepts. `viwo attach GAME` lists them; `viwo attach GAME --target KEY
[--tool ID] [--pid N] --workspace W [--confirm]` starts the tool as a tracked child and waits
for it. API: `GET /api/runtime/attach?gamePath` -> `{targets (with attach), enabled, problems}`,
`POST /api/runtime/attach {gamePath, targetKey, tool?, pid?, confirm?}` -> `{handoff, label, pid,
target, attached, warnings}` (`attached`: the pid the debugger attached to, 0 when it started the
game). UI: RUNTIME, DEBUGGER AND MEMORY (the pid of RUNNING PROCESS when it is a number).
Every dump, trace and profile run writes a new `<pid>-<stamp>` folder (`_1`, `_2`... for runs in
the same second) and every recording a new WAV: a run never reads or overwrites an earlier run's.

## 11.3 Runtime agents

```text
RuntimeAgent (family runtime; owned by the engine's plugin)
  accepts(copy, exe) -> ""  or why not
  install(copy, exe, ctx) -> [extra launch args]   agent and settings into the copy; every first-run
                                                   question pre-answered; leftovers of a previous run removed
  finished(copy, exe) -> bool
  outputs(copy, exe) -> [Path]
```

Core (`viwo/core/capture/agents.py`): pick the agent of the plugin that detects the game, make or
reuse a patched copy (default `<workspace>.agent-copy` beside the workspace, `--copy` to choose),
install the agent, start the copy windowed as a tracked child, report progress every 30 s, stop
it when the agent is finished or at `--timeout`, copy the outputs into the workspace. An
unfinished run is said with what was found. Files the OS refuses to copy into the patched copy
are named (`notCopied`).

## 11.4 Jobs

Each kind is a job (`capture`, `agent`, `dump`, `trace`, `record`) through its route
(`POST /api/capture`, `POST /api/runtime/<kind>`) or `POST /api/jobs`; the CLI runs the same
code (`viwo/core/capture/runtime.py` `run`). Capture steps: POLICY -> CAPTURE -> HARVEST -> GATHER into the workspace -> DIFF against static extraction (by content
hash) -> REPORT. Capture, analysis and extraction jobs add temporary antivirus exclusions for
their folders when `av_exclusions = on` (doc 1, `viwo/core/scan_exclusions.py`).

## 11.5 The game-folder rule

The game folder is only read. An agent installs into a marked patched copy (doc 18), made once
and reused. Attaching to a running process writes nothing into the game. x64dbg debugs the
game's own process, not a copy (live patching needs the real process): what the user then
patches in the debugger, or writes back to a file from it, is the user's own action in the tool.

## 11.6 Network and offline

Every backend declares `network`. RenderDoc fetches nothing; ViWo sets `VIWO_OFFLINE=1` for the
launched game and warns when the network is reachable. DataTool and BepInEx declare `download`.

## 11.7 Rung D4

Shipped: CPU profiling (`profile.sample`, `viwo profile --pid|--name --seconds --workspace`,
`/api/runtime/profile`, RUNTIME). The OS layer samples every thread's instruction pointer
(`sample_threads`: Windows SuspendThread + GetThreadContext about every millisecond, no
administrator rights; Linux `perf record`, which needs perf_event_paranoid <= 1); each sample is
placed in its module and named after the nearest export below it. `.runtime/profile/<pid>-<time>/`
holds `hotspots.json` and `hotspots.txt`: hot spots, modules and threads as shares of the samples.
Tracy profiles only games built with it, so it is not the backend.

Open: a hook loader with hot reload (`hook.inject`), an in-game overlay (`hook.overlay`),
own-traffic network tooling (`net.*`: capture with a dissector, a proxy between the user's client
and their own server). The network plaintext capture and the DLL injection loader are the owner's
call and are not authored by the assistant.
