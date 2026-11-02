# 11. Runtime capture (draft)

Scope decision: runtime capture is **in scope**. It covers assets that only
exist decoded while the game runs: procedurally generated textures, streamed
audio, encrypted assets whose key is only applied in memory, and meshes after
skinning. This is the most sensitive part of the framework, so this doc
starts with the boundaries and then sketches the structure.

Research notes are in doc 13. Tools named here were checked against their
repositories on 2026-11-02; anything marked UNVERIFIED wasn't confirmed.

## 11.1 Boundaries (proposal)

What the framework would do:
- capture from a game **the user launches through the framework**, on their own machine, for offline or single-player use;
- prefer static extraction, and offer runtime capture for what static extraction couldn't produce;
- record, for every output file, that it came from a capture (provenance).

What the framework would **not** do, with no override flag:
- **Bypass, hide from, or work around anti-cheat** in any way. When anti-cheat markers or drivers are detected, or the game is listed as online or competitive, capture is **refused**.
- Use global hooks (for example RenderDoc's global hook, which needs Secure Boot turned off), attach to processes it didn't start, or install kernel drivers.
- Modify the game folder without an exact, reversible journal (11.4).

Comparable tools set similar expectations. RenderDoc's README says it is
"intended for debugging your own programs only", and RenderDoc deliberately
makes itself detectable. BepInEx, MelonLoader, UE4SS and UnityExplorer don't
publish any restrictions, so the framework would have to set its own.

Proposed preconditions, checked by a `capture.policy` step before any launch:

| Check | Result if it fails |
|-------|--------------------|
| The `capture` feature flag is enabled in the ini | refuse |
| The user confirmed once per game: "local, offline, single-player; I'm responsible for EULA compliance" | ask |
| Anti-cheat markers are found in the game folder | **refuse** |
| An anti-cheat service is running (best effort, through the kernel) | **refuse** |
| The game is on a built-in list of online/competitive titles (data file, not code) | **refuse** |
| The network is reachable | warn and suggest going offline (best effort) |

Anti-cheat markers: the only one verified from source so far is
`NeacLoader.exe` (NetEase, which DataTool itself checks for). Common names
such as `EasyAntiCheat/`, `BattlEye/` and `start_protected_game.exe` are
UNVERIFIED and need confirming before the list is relied on. The list would
be data, shipped and versioned in the repo.

> Example: **Overwatch** has anti-cheat and is online-only, so runtime capture
> would always be refused for it. Its showcase plugin is static-only (doc 14).

## 11.2 Two kinds of capture

| Kind | How | Engine-agnostic? | Examples |
|------|-----|------------------|----------|
| **Graphics API capture** | record one or more frames at the graphics API level, then pull textures and meshes from the capture | yes | RenderDoc (MIT; D3D11/12, Vulkan, GL 3.2+, GLES; **no D3D9/10, no legacy GL**), apitrace (covers D3D9 and old GL), PIX (D3D12, Windows) |
| **Engine runtime agents** | a loader or mod framework runs code inside the game and dumps objects | no, one per engine | Unity: BepInEx (LGPL-2.1) + UnityExplorer (GPL-3.0), MelonLoader (Apache-2.0). Unreal: UE4SS (MIT; dumps mappings and headers that help static tools like CUE4Parse). Ren'Py: developer console, or a `.rpy` hook dropped in `game/`. Godot: `override.cfg` (documented); whether it can inject an autoload is UNVERIFIED |
| Generic process tools | memory and function hooks | yes | Frida (wxWindows Library Licence): decoded audio buffers and similar |
| Last resort | record the system audio output | yes | WASAPI loopback (Windows) / PipeWire monitor (Linux), OBS. Lossy, so it's flagged as such |

A useful observation: on Unreal, a runtime agent (UE4SS) is mostly a way to
**improve static extraction** (its `.usmap` mappings make CUE4Parse work on
games without type info). So "runtime" doesn't always mean "capture assets at
runtime".

## 11.3 Proposed structure

A capture is a **job** (doc 12) of kind `capture`, separate from extraction:

| Step | Owner | What happens |
|------|-------|--------------|
| POLICY | core | the checks in 11.1 |
| PREPARE | core + agent backend | for engine agents: install the agent with a **journal** (11.4), or work on a copy of the game |
| LAUNCH | kernel + backend | the kernel starts the game under the capture backend. On Linux, Windows games go through Proton/Wine; whether injection tools work there is largely UNVERIFIED ❓ |
| CAPTURE | user + backend | interactive: the user plays to the scene and triggers a capture from the UI, the CLI or a hotkey; or a scripted trigger where the backend supports it |
| HARVEST | backend | turn capture files into plain files in staging (RenderDoc replay → png/obj, agent dumps → files) |
| COLLECT | core | same as extraction COLLECT, with origin `capture:<job>` |
| DIFF | core | compare with the latest static extraction by content hash, to show **what capture found that static extraction didn't**. Perceptual hashing for textures is an open question ❓ |
| RESTORE | core | undo every journaled change to the game folder, and verify the files match again |
| REPORT | core | run record, with which method produced each file |

Interfaces (same slot model as doc 8):

```text
CaptureBackend          (families capture.gpu, capture.memory, capture.audio)
  launch(spec: LaunchSpec, ctx) -> CaptureSession
  CaptureSession.trigger(frames=1) / .stop()
  harvest(session, staging, ctx) -> HarvestReport

RuntimeAgent            (family runtime.<engine>)
  install(game_root, journal, ctx) -> Outcome      # journaled, reversible
  commands() -> [AgentCommand]                     # e.g. "dump textures", "dump usmap"
  run(command, ctx) -> Outcome
  uninstall(journal, ctx) -> Outcome

LaunchSpec { executable, args, env, working_dir, via: native|proton|wine, offline_flags }
```

The kernel would gain one part, `kernel.launch`, covering how to start a game
(native, Proton or Wine), how to watch its process tree, and how to set up
audio loopback, since all of that differs between Windows and Linux.

## 11.4 The game folder rule, revised

Doc 0 says the game folder is never modified. Runtime agents (BepInEx,
MelonLoader, UE4SS, a Ren'Py `.rpy` hook, Godot `override.cfg`) all work by
**adding files to the game folder**. There are two ways to reconcile that:

1. **Journaled overlay:** every file written or replaced is recorded with its hash; RESTORE removes or restores each one and checks the hashes. Cheap, but risky if the process is killed mid-session (a restore runs at the next startup).
2. **Copy the game:** work on a copy in scratch. Safe, but expensive for large games.

Suggestion: the overlay by default, with a startup check that finishes any
unfinished restore, and copy mode as an ini option ❓.

## 11.5 Default slots (proposal)

| Slot | Main | Spare | Notes |
|------|------|-------|-------|
| `capture.gpu` | RenderDoc (`renderdoccmd capture`, replay through its Python module) | apitrace (older APIs) | the RenderDoc Python module must be built for one exact Python version, so it probably runs as a separate helper process |
| `capture.gpu-d3d12` | RenderDoc | PIX `pixtool` (Windows) | |
| `runtime.unity` | BepInEx + a small dump plugin of ours | MelonLoader (with its offline flag; by default it contacts a remote API) | UnityExplorer is interactive, so it's for manual use only |
| `runtime.unreal` | UE4SS (mapping/header dumps fed into static extraction) | Frida | UE4SS only ships Windows binaries |
| `runtime.renpy` | `.rpy` hook / developer console | Frida | |
| `runtime.godot` | `override.cfg` (UNVERIFIED for this use) | Frida | |
| `capture.memory` | Frida | — | |
| `capture.audio` | kernel loopback (WASAPI / PipeWire) | OBS | lossy, flagged |

Ninja Ripper is proprietary, Windows-only and gated behind a paid tier, so it
isn't proposed as a backend.

## 11.6 Risks and open questions

- **Legal and terms of service:** even offline, many EULAs forbid this kind of tooling. The framework can make use responsible but can't make it allowed; that stays the user's responsibility, stated plainly.
- Hidden network access by backends (MelonLoader's remote API, DataTool's remote keyring and CDN). Proposal: every backend declares its network use, and offline flags are on by default.
- Copyleft: UnityExplorer and BepInEx are GPL/LGPL, so they run as separate components, never linked into the core.
- Proton and Wine behavior for injection tools is UNVERIFIED.
- Prototype scope: probably **one** path only, RenderDoc texture capture on a test game we own or one that is openly licensed (doc 14).
