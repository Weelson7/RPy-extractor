# 11. Dynamic and runtime domain

This is the second arm of the orchestrator (doc README): work that **runs or attaches to the game**
rather than reading a copy of it. It covers assets that only exist decoded at runtime (procedural
textures, streamed audio, in-memory-decrypted assets, skinned meshes) and, more broadly, every
capability that needs a live process: debugging, instrumentation and tracing, memory inspection,
runtime hooking, your-own-traffic networking, graphics capture and profiling. Because it touches a
running game, it is the most sensitive arm, so this doc states the model first.

Research notes are in doc 13. Tools named here were checked against their repositories on
2026-11-02; anything marked UNVERIFIED wasn't confirmed.

## 11.1 Model, not boundaries (owner's decision, D22)

ViWo refuses nothing because of what a game is, which backend runs, or what the user intends
(README "Philosophy"). There is **no policy gate** in this arm. The sensitive nature of running
code inside a game is handled the way the philosophy prescribes: a feature switch, warnings, one
opt-in, a reversible journal, and a disclaimer that puts responsibility on the user. The scope
statements a user writes for themselves (offline only, single-player only, no anti-cheat) are their
morals, not something ViWo enforces.

What this arm does:
- runs or attaches to a game **the user drives through ViWo**, on their own machine;
- prefers static extraction (doc 3) and offers runtime work for what static couldn't produce;
- records, for every output file, that it came from a dynamic job (provenance `capture:<job>` /
  `runtime:<job>`).

The one project-level rule is unchanged (philosophy point 5): **ViWo authors no first-party
borderline code** — no anti-cheat evasion, no copy-protection defeat. Such tools, if used, are
pinned community components run as separate processes under the disclaimer.

`dynamic.policy` step, before any launch or attach — **all information and opt-in, none a refusal**:

| Check | Result |
|-------|--------|
| The `runtime` feature flag is enabled in the ini (the shipped `capture` opt-in switch is its first instance; the broader arm generalises it) | off by default; enabling it is one switch |
| The user confirmed once per game (the disclaimer: "I'm responsible for EULA and terms compliance") | ask once |
| Anti-cheat markers found in the game folder | **warn**, name the marker, continue on confirm |
| An anti-cheat service is running (best effort, OS layer) | **warn**, continue on confirm |
| The game is on the bundled online/competitive data list | **warn**, continue on confirm |
| The network is reachable | **warn**, offer the offline launch flags, continue |

Anti-cheat markers and the online/competitive list are **data files** (shipped, versioned), used
only to word the warning; they never block. The only marker verified from source so far is
`NeacLoader.exe` (NetEase); `EasyAntiCheat/`, `BattlEye/`, `start_protected_game.exe` are UNVERIFIED
and need confirming before the warning names them with confidence.

> Comparable tools set their own expectations (RenderDoc's README says it is "intended for debugging
> your own programs", and RenderDoc makes itself detectable). ViWo surfaces those facts as warnings;
> it does not adopt them as gates.

## 11.2 Slot families in this arm (doc 8)

Every backend declares `license` (GPL/AGPL ⇒ subprocess), `network` (offline flags on by default),
`parses_untrusted_in_process`, and `touches_running_game: true` so the core routes it through the
journal (11.5) and the `dynamic.policy` step.

| Family | What it does | Main | Spare | temp.md |
|--------|--------------|------|-------|---------|
| `capture.gpu` | frame capture, draw-call/texture/mesh/RT inspection, shader disasm (DXBC/DXIL/SPIR-V) | RenderDoc (MIT) | apitrace (old APIs), PIX (D3D12) | §11 |
| `capture.audio` | decoded/streamed audio to WAV (buffer hook, then loopback) | Frida buffer dump | OS loopback (WASAPI/PipeWire), OBS (lossy, flagged) | §11, §12 |
| `runtime.<engine>` | an engine agent dumps live objects, or dumps data that improves static extraction | Unity: BepInEx + our dump plugin · Unreal: UE4SS (`.usmap`/headers) · Ren'Py: `.rpy`/console · Godot: `override.cfg` | MelonLoader (offline flag) / Frida | §5, §11 |
| `debug.session` | software/hardware/memory breakpoints, tracepoints, watchpoints, stepping, call-stack unwind, attach/launch-suspended, first-chance exceptions | x64dbg (GUI; scripted where possible) | WinDbg (`cdb` headless), LLDB/GDB | §6 |
| `debug.record` | record/replay and time-travel traces | WinDbg TTD (Windows) | rr (Linux) | §6 |
| `trace.calls` | function-call tracing with args/returns; hook the script engine | Frida | DynamoRIO, Intel Pin | §8, §13 |
| `trace.api` | Win32/DirectX/file-I/O/socket API monitoring | Process Monitor | API Monitor | §8 |
| `trace.coverage` | code-coverage collection and overlay onto the disassembly; A/B coverage diff | DynamoRIO `drcov` → Lighthouse | Pin | §8 |
| `memory.scan` | value scan with refine passes, float/vector tolerance, "what writes/reads this" | Cheat Engine (`ceserver`) | Frida scripts | §7 |
| `memory.struct` | live struct/class reconstruction, pointer-chain scanning | ReClass.NET | CE dissector | §7 |
| `memory.dump` | dump the full process or a region; diff snapshots between states | OS layer / Frida | — | §7 |
| `hook.inject` | load a user DLL (LoadLibrary, manual map, proxy DLL such as `dinput8`/`version`) and hot-reload it | our loader | community loaders | §9 |
| `hook.overlay` | in-game console/overlay (ImGui via D3D/Vulkan hooks) | community overlay lib | — | §9 |
| `net.capture` | packet capture with a game-protocol dissector, on the user's own traffic | Wireshark/`tshark` + Lua dissector | — | §10 |
| `net.proxy` | proxy/replay between the user's own client and their own/self-hosted server; read plaintext before encryption on their own client | mitmproxy / our proxy | Frida send/recv hook | §10 |
| `profile.sample` | CPU sampling of hot loops, frame-time, lock/contention | Tracy (injected) | Superluminal/VTune (user-run) | §20 |

Runtime **hooking frameworks** themselves (MinHook, Detours, PolyHook, SafetyHook) and the runtime
assemblers (Keystone, asmjit) are pinned libraries a user's mod links against; ViWo packages and
loads the mod (doc 18), it does not author the hooks. `net.*` is explicitly scoped by the user to
their own traffic and their own or self-hosted servers; ViWo neither widens nor narrows that.

Many of these are GUI-first (x64dbg, Cheat Engine, ReClass.NET, the RenderDoc viewer, Wireshark).
They are offered as **interactive handoffs** (doc 8.3a): "open in x64dbg" builds the launch-suspended
or attach spec, "inspect in RenderDoc" opens the harvested capture, each as a tracked child
subprocess inside ViWo's process tree. A handoff that runs code in the game goes through
`dynamic.policy` and the journal like any dynamic backend; one that only opens a captured file does
not. ViWo prepares the session; the interactive work happens in the tool.

## 11.3 Two kinds of asset capture

| Kind | How | Engine-agnostic? | Examples |
|------|-----|------------------|----------|
| **Graphics API capture** | record frames at the API level, pull textures/meshes/shaders from the capture | yes | RenderDoc (D3D11/12, Vulkan, GL 3.2+, GLES; no D3D9/10, no legacy GL), apitrace (D3D9/old GL), PIX (D3D12) |
| **Engine runtime agents** | a loader or mod framework runs inside the game and dumps objects | no, one per engine | BepInEx (LGPL-2.1) + UnityExplorer (GPL-3.0), MelonLoader (Apache-2.0); UE4SS (MIT; dumps mappings/headers that help CUE4Parse); Ren'Py console or a `.rpy` hook; Godot `override.cfg` (autoload injection UNVERIFIED) |
| Generic process tools | memory and function hooks | yes | Frida (wxWindows Licence): decoded audio buffers and similar |
| Last resort | record the system audio output | yes | WASAPI loopback / PipeWire monitor, OBS. Lossy, flagged |

On Unreal a runtime agent (UE4SS) is mostly a way to **improve static extraction** (its `.usmap`
mappings make CUE4Parse work on games without type info), so "runtime" does not always mean
"capture assets at runtime" — it often feeds the static arm (doc 6).

## 11.4 Job structure

A dynamic job (doc 12), separate from extraction. Kind `capture`, `runtime`, `debug`, `trace`,
`memory`, `hook`, `net` or `profile`; the steps generalise the capture pilot:

| Step | Owner | What happens |
|------|-------|--------------|
| POLICY | core | the warnings and opt-in in 11.1 (none refuses) |
| SETUP | core + backend | install agents or a user DLL through a **journal** (11.5), or work on a copy of the game |
| LAUNCH / ATTACH | OS layer + backend | the OS layer starts the game under the backend, or attaches to a process the user points at. On Linux, Windows games go through Proton/Wine; injection there is largely UNVERIFIED |
| INTERACT | user + backend | the user plays, breakpoints hit, scans refine, frames/scenes trigger a capture; or a scripted trigger where the backend supports it |
| HARVEST | backend | turn backend output into plain files/artifacts in staging (RenderDoc replay → png/obj, agent dumps → files, traces → logs, scans → address lists) |
| GATHER | core | move harvested asset files into the workspace (as COLLECT does), origin `capture:`/`runtime:`; analysis-style artifacts go under `.analysis/` or `.dynamic/` |
| DIFF | core | for asset jobs, compare with the latest static extraction by content hash to show what runtime found that static didn't (perceptual hashing for textures is open) |
| RESTORE | core | undo every journaled change to the game folder and verify hashes match again |
| REPORT | core | run record, with which method produced each file |

Interfaces (same slot model as doc 8):

```text
DynamicBackend          (families capture.*, runtime.*, debug.*, trace.*, memory.*, hook.*, net.*, profile.*)
  touches_running_game: true
  launch(spec: LaunchSpec, ctx) -> Session        # or attach(pid, ctx)
  Session.trigger(...) / .step() / .scan(...) / .stop()
  harvest(session, staging, ctx) -> HarvestReport
  install(game_root, journal, ctx) -> Outcome      # agents/DLLs only; journaled, reversible
  uninstall(journal, ctx) -> Outcome

LaunchSpec { executable, args, env, working_dir, via: native|proton|wine, offline_flags, attach_pid? }
```

The OS layer gains `os.launch`: how to start a game (native/Proton/Wine), watch its process tree,
attach to a pid, and set up audio loopback, all of which differ between Windows and Linux.

## 11.5 The game-folder rule, revised

Doc 0 says the game folder is read-only. Dynamic agents (BepInEx, MelonLoader, UE4SS, a Ren'Py
`.rpy` hook, Godot `override.cfg`, an injected proxy DLL) work by **adding files to the game
folder**. Two ways to reconcile that, both already in the capture pilot:

1. **Journaled overlay:** every file written or replaced is recorded with its hash; RESTORE removes
   or restores each one and checks the hashes. A startup check finishes any restore interrupted by a
   killed process. This is the only sanctioned way core touches a game folder (`core/capture/journal.py`).
2. **Copy the game:** work on a copy in scratch. Safe, costly for large games; an ini option.

Overlay by default, with the startup-restore check; copy mode as an option. Attaching to a process
the user launched themselves touches no files at all and skips SETUP/RESTORE.

## 11.6 Risks and open questions

- **Legal and terms of service:** even offline, many EULAs forbid this tooling. ViWo makes use
  responsible, not allowed; that stays the user's, stated plainly (disclaimer).
- **Hidden network access** by backends (MelonLoader's remote API, DataTool's keyring/CDN). Every
  backend declares `network`; offline flags are on by default.
- **Copyleft:** UnityExplorer, BepInEx, Diaphora, Cheat Engine, DynamoRIO vary; GPL/AGPL run as
  separate components, never linked into the core.
- **Proton/Wine** behaviour for injection and debugging is UNVERIFIED.
- **Prototype scope stays narrow:** the shipped pilot is RenderDoc texture capture on an owned or
  openly licensed game (doc 14); the other families are the roadmap (doc 16), one path at a time.
