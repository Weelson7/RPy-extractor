# 11. Dynamic arm

Work that runs or attaches to the game: GPU frame capture, runtime agents, memory dumps, API
traces, the user's own hook scripts, audio loopback, and the debugger and memory-editor
attach tools (`viwo/core/capture/`,
`viwo/contracts/runtime.py`, `viwo/cli_dynamic.py`, `viwo/api/handlers_capture.py`). CLI arm
`viwo dynamic`: `capture`, `dump`, `trace`, `hook`, `profile`, `agent`, `record`, `attach`. UI:
CAPTURE, RUNTIME.

## 11.1 Model: warnings and one opt-in, no gate (D22)

ViWo refuses nothing because of what a game is or what the user intends. The arm is off until
the user switches it on; what it knows about a game is said as warnings.

| Step | Applies to | Result |
|------|------------|--------|
| `capture` in `[startup] features` (SETTINGS) | capture, dump, trace, hook, profile, agent, record, attach | off by default; off answers `refused` with the hint to enable it |
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
| capture (D1) | `capture.gpu` / `renderdoc` | RenderDoc 1.47 (`renderdoccmd`, `qrenderdoc --py`) | runs the game as a tracked child of `renderdoccmd capture -w`; unattended by default: `rd_trigger.py` takes one frame after `--auto SECONDS` (default 30) and the tree is stopped; `--auto 0` = attended (F12 / PrtScn, then quit); `rd_harvest.py` turns every capture into PNG textures and shader disassembly (both scripts live in `viwo/data/renderdoc/`, outside the package, so `import renderdoc` finds RenderDoc's module, never ViWo's) | the frames themselves (`rdc/*.rdc`, which open in qrenderdoc) and their textures collected into the workspace groups with provenance `capture:<backend>:<stamp>`; files static extraction already produced are not stored twice; run record `capture-<stamp>.json` |
| agent (D2) | `runtime.unreal` / `ue4ss-agent` | UE4SS 3.0.1 | GUI console and bundled mods off; a ViWo Lua mod writes `Mappings.usmap` and `UE4SS_ObjectDump.txt`, then a done file | `.runtime/agent/ue4ss-agent/` |
| agent (D2) | `runtime.unity` / `bepinex-agent` | BepInEx 6 be.785 (IL2CPP) | console off; the first start generates the interop assemblies (BepInEx downloads its Unity base libraries: `network = "download"`) | `.runtime/agent/bepinex-agent/` (interop `*.dll`, `LogOutput.log`) |
| record (D2) | `soundcard-loopback` (no slot) | soundcard (WASAPI loopback, PulseAudio monitor) | `--seconds` of the default output device, 16-bit WAV | `.runtime/audio/loopback-<stamp>.wav` |
| dump (D3) | OS layer `dump_process` | Windows `MiniDumpWriteDump`; Linux `/proc/<pid>/mem` | a full dump of a running process (`--pid` or `--name`) | `.runtime/dump/<pid>-<stamp>/` |
| trace (D3) | `frida-trace` (no slot) | frida-tools 14.11.0 / frida 17.25.2 | `frida-trace -p <pid> -i <glob>...` for `--seconds` | `.runtime/trace/<pid>-<stamp>/trace.log` |
| hook (D4) | the `frida-trace` backend's tool (no slot) | frida-tools 14.11.0 / frida 17.25.2 | `frida -q -t <seconds> -p <pid> -l <the user's script>`: Frida loads the user's own script into the running process and again each time the file is saved; every line it prints is relayed to the console (11.7) | `.runtime/hook/<pid>-<stamp>/hook.log` |
| attach (D3) | `attach.debug` / `x64dbg-gui` | x64dbg (GPL-3, a separate process) | Continue in x64dbg (doc 8.3a) on the game's own process: attached to the one process running the target's executable (or `--pid`), else the game's own executable started under the debugger; a patch made live lands in the real process | - |
| attach (D3) | `attach.memory` / `cheatengine-gui` | Cheat Engine 7.6 | Continue in Cheat Engine with a ViWo table that attaches to the game | `.runtime/cheatengine-gui/<key>/<exe>.CT` |
| attach (D4) | `attach.net` / `mitmproxy-gui` | mitmproxy 12.3.1 | Continue in mitmproxy: its own web interface as a local proxy (regular mode, this machine only) for the game's own HTTP(S) traffic; the user points the game at it and decides about its certificate (11.7) | `.runtime/mitmproxy-gui/<key>/flows.mitm` |

A name matching several running processes answers `needs_decision` (give `--pid`).

**Attach** (`core/capture/attach.py`): the targets are the plugins' analysis targets (doc 6.1)
that an `attach.*` tool accepts. `viwo attach GAME` lists them; `viwo attach GAME --target KEY
[--tool ID] [--pid N] --workspace W [--confirm]` starts the tool as a tracked child and waits
for it. API: `GET /api/runtime/attach?gamePath` -> `{targets (with attach), enabled, problems}`,
`POST /api/runtime/attach {gamePath, targetKey, tool?, pid?, confirm?}` -> `{handoff, label, pid,
target, attached, warnings}` (`attached`: the pid the debugger attached to, 0 when it started the
game). UI: RUNTIME, DEBUGGER AND MEMORY (the pid of RUNNING PROCESS when it is a number).
Every dump, trace, hook and profile run writes a new `<pid>-<stamp>` folder (`_1`, `_2`... for runs in
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

Each kind is a job (`capture`, `agent`, `dump`, `trace`, `hook`, `profile`, `record`) through its route
(`POST /api/capture`, `POST /api/runtime/<kind>`) or `POST /api/jobs`; the CLI runs the same
code (`viwo/core/capture/runtime.py` `run`). Capture steps: POLICY -> CAPTURE -> HARVEST -> GATHER into the workspace -> DIFF against static extraction (by content
hash) -> REPORT. Capture, analysis and extraction jobs add temporary antivirus exclusions for
their folders when `av_exclusions = on` (doc 1, `viwo/core/scan_exclusions.py`).

## 11.5 The game-folder rule

The game folder is only read. An agent installs into a marked patched copy (doc 18), made once
and reused; the copy and the workspace pass the game-folder guard first (doc 3.1). A run on a
process id (dump, trace, hook, profile) and `record` have no game path: their workspace is
refused when it may be a game (a patched copy, or a folder of files that is no ViWo workspace);
a new folder inside a game cannot be told apart there. Attaching to a running process writes nothing into the game. x64dbg debugs the
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

Rung D4 is served by pinned third-party tools only (owner, 2026-11-10): ViWo writes no hook,
overlay or capture code of its own; it starts the tool as a tracked child, like the debuggers.

Shipped: own-traffic inspection, `attach.net` / `mitmproxy-gui` (mitmproxy 12.3.1, MIT):
"Continue in mitmproxy" starts mitmproxy's own web interface as a local proxy on two free ports
of this machine, in regular mode only, and saves every flow in the workspace
(`.runtime/mitmproxy-gui/<key>/flows.mitm`). What the tool cannot do by itself is said, and left
to the user: pointing the game or the system proxy at it; trusting mitmproxy's certificate
authority to see HTTPS (the user's own choice, for the current user, no elevation; the workbook
says how and to remove it after); a game that pins its certificates cannot be read this way.
Not used, because they need elevation (the minimal-prompts rule): mitmproxy's per-process
capture mode, and raw packet capture (Wireshark needs an administrator-installed driver).

Shipped: the user's own hook script, `hook.inject` (`viwo hook --pid|--name --script FILE
[--seconds S] --workspace W`, `/api/runtime/hook {pid|name, scriptPath, seconds}`, RUNTIME, RUN
HOOK SCRIPT; `core/capture/hook.py`). The tool is the pinned Frida's own command line, a separate
process started from `third_party/python` (`python -m frida_tools.repl -q -t SECONDS -p PID -l
SCRIPT`): Frida attaches to the running process, loads the script, loads it again each time the
file is saved (its own hot reload) and detaches after the seconds. ViWo relays every line Frida
prints to the console as it comes and keeps them in `.runtime/hook/<pid>-<stamp>/hook.log`.
ViWo ships no script and no loader: the script is the user's, for example
`Process.enumerateModules().forEach(m => console.log(m.name, m.base));`. An anti-cheat service running on the
machine is said as a warning before the script loads (never a gate, 11.1). It attaches only (it
never starts the game), asks for no elevation (a process Frida may not open answers Frida's own
refusal) and sits behind the `capture` switch like the trace, which attaches the same way. It
has no slot: one tool, the dependency the `frida-trace` backend declares. A refused attach ends
the run at once with Frida's words. On Windows Frida's process can stay about 30 s after it
detached, so ViWo stops it 10 s after the script's time; an error the script threw is then in
the console and the log, and fails the run only where Frida exits by itself.

Open: `hook.overlay`. Checked on 2026-11-10, neither candidate can be wired within the rules:

- Special K (Windows; `SK_26_10_10`, `SpecialK.7z`, GPL-3.0, two DLLs, 6,150,167 bytes, sha256
  `4dcaf920740cbae2fc8cdf75f7b5ed6aa72280fdbf1cfa9e3d5eb53f23f38fcd`) is not pinned. With no setting of the
  user's it switches on its "CAPCOM DRM workaround" for every executable signed by CAPCOM
  (`src/config.cpp`: it copies the game's `steam_api64.dll` and loads the copy), and ViWo
  neither authors nor switches on a copy-protection workaround (11.1): pinning it is the
  owner's call. Besides: its licence screen shows inside the game on the first start and must be
  clicked, it fetches from its own servers, and it is loaded from the game's folder, so it
  would need a whole patched copy like the D2 agents.
- MangoHud (Linux; `v0.8.4`, `MangoHud-0.8.4.r0.g992103e.tar.gz`, MIT, 10,282,346 bytes, sha256
  `aa0b2a009552f5e7c50baabf361267a79ea5e5c0fea440786f3b202d51f57753`): the release tarball installs into `/usr`
  through `sudo` (`mangohud-setup.sh`), and its Vulkan layer manifests name
  `/usr/lib/mangohud/...`, so it does not run from `third_party/` without elevation or without
  ViWo rewriting the manifests. A `mangohud` the user installed with their distribution could
  be started as the game's wrapper, unpinned; not built, and not verifiable on Windows.
- ReShade ships only as an installer.

## 11.8 Patcher / isolation

Cold and live patching (doc 16.2b T1-T3, 18.8) work even when the target defends itself
(self-checksums, anti-debug) or holds fragile state, and TPM-gated local logic can be met with a
virtual TPM, by running the target behind an isolation boundary and driving the edit there. The
boundary is a pinned or located third-party VM, emulator or VMI tool run as a separate process;
ViWo authors no hypervisor, driver or evasion code (CLAUDE.md). The arm is general: nothing in it
depends on the game, the language the program is written in or the guest OS; what is specific
is a slot backend (the tier), a Volatility plugin folder (what an OS looks like) or a patch set.

**State.** T1 (VirtualBox) and T2 (QEMU) run against the real hypervisors (L5:
`tests/test_isolation_real.py`, `test_isolation_real_vbox.py`, `test_isolation_real_media.py`,
on a boot-sector guest and on a long-mode guest with page tables of its own). T3 (LibVMI) is
unit-tested with fakes; its real run needs a bare-metal Linux Xen/KVMi host (a bootable stick).
**No guest operating system has been booted yet**, so finding a program inside a guest OS
(`locate`) and the program dump are proven on fakes and on a real dump whose guest has no OS
(said, not guessed), not on a real Windows or Linux guest.

**Contract** (`viwo/contracts/patcher.py`, a thin contract): a `PatcherBackend` in an
`isolation.<tier>` slot has `ready(os)` (can it run here?) and `start(target, ctx, *,
snapshot=False)`, which boots or attaches the target and returns a `PatchSession`. The session is
the live handle: `suspend`/`resume`, `read_mem`/`write_mem` (addresses as the guest's vCPU sees
them), `physical()` (guest physical memory with the guest stopped: `read(pa, n)`, `write(pa,
data)`, raising `MemoryFault`; None when the tier cannot reach it), `snapshot`/`rollback`, `dump`
and `close`; `record()` is what a later call needs to reach it again, `release()` lets go of the
handle without stopping the target, and the backend's `reattach(record, ctx)` rejoins it. The
target's shape rides on `PatchTarget` (`image`: a disk or an installer `.iso`; `memory_mb`,
`cpus`, `network`, `headless`, `halted`, `accel`, `fresh`, `efi`, `share`, `gpu`, `args`);
`cpu_paging()` says vCPU 0's page-table root and paging mode where the tier can read them
(VirtualBox: its console's `r cr3`; QEMU: the monitor's `info registers`). A live edit
is **atomic** — suspend → `write_mem` → `read_mem` to verify → resume — in
`core.isolation.atomic_write`. When an edit cannot land the backend reports **which `Wall`** it
hit (`server_side`, `vm_detected`, `remote_attestation`, `integrity_check`, `not_ready`) rather
than failing blind (owner: never silent). A readback that does not match is an `integrity_check`
wall, and so are bytes the target puts back once it runs again (a journalled edit is read once
more half a second after the resume). A page not in guest RAM is a `not_ready` wall that says so.

**Tiers** (slot family `isolation`):

| Tier | Slot / backend | Tool (licence) | What it does | State |
|------|----------------|----------------|--------------|-------|
| T1 | `isolation.vbox` / `vbox` | VirtualBox 7.x `VBoxManage` (base package, GPL-3.0; NOT the Extension Pack), located | boots a **copy** of the image in the session folder (VirtualBox rewrites a disk's header once it registers it, so the user's image is never attached: converted to VDI by `qemu-img` or `convertfromraw`, a VDI/VMDK/VHD copied with a new UUID; an `.iso` boots as an installer with a new empty 64 GB disk), kept between sessions with its snapshots (`--fresh` discards it). No network unless asked (NAT). UEFI with a **virtual TPM 2.0** when asked (`efi`). **Live snapshots** on hardware acceleration; rollback powers off, restores and starts again. Memory goes through the VM's own **gdb stub** on loopback (`--guest-debug-provider gdb`): found on the real thing, it halts the vCPUs while a client is connected and lets them go when it leaves (a VBoxManage pause stays a pause), it reads but does not write (`M`/`X` refused), and its console (`qRcmd`, whose last character it drops, so a space is sent after) reads and writes **physical** memory (`db`/`eb`/`eq` on `%%` addresses) and the control registers. So every T1 access is physical: an address is walked through vCPU 0's paging (CR0/CR3/CR4/EFER) or a located process's. `debugvm dumpvmcore` writes an ELF core. A `share` folder is a read-only VirtualBox shared folder (the guest needs Guest Additions; their CD is attached, a failure is said) | **real**: VirtualBox 7.2.22, long-mode guest (copy booted and image untouched, page walks on CR3 and on a given DTB, journal and undo, pause seen to stop the guest, live snapshot and rollback, ELF core, stop; UEFI + TPM 2.0, installer and share in the VM's own settings) |
| T2 | `isolation.qemu` / `qemu` | QEMU `qemu-system-x86_64` (GPL-2.0), pinned, on demand | runs the guest behind a closed boundary and drives it from outside through QEMU's own two channels, both on loopback only: **QMP** (`qmp.py`: stop/cont, savevm/loadvm, dump-guest-memory, quit) and the **gdbstub** (`gdb.py`, a first-party stdlib client: memory with the guest stopped; **physical** memory in QEMU's `Qqemu.PhyMemMode`, which is QEMU-wide, so it is switched off before the connection goes and at the start of every virtual access). The image is **never written**: a qcow2 overlay beside the session takes every change and is kept between sessions (`--fresh` discards it); an installer `.iso` boots read-only with a new empty qcow2 disk (`qemu_media.py`). `efi` boots QEMU's own edk2 with its variables in the session folder; **QEMU on Windows has no virtual TPM** (no swtpm), which is said (a guest that insists on one: T1). A `share` folder becomes a read-only CD (`share.py`: ISO 9660 + UDF 2.60 + Rock Ridge + Joliet written by pycdlib, synthetic ISO names so no name is refused, full names in UDF/Rock Ridge, Joliet cut to 64 bytes and kept unique; rebuilt only when the folder changed). No network unless asked. The accelerator is hardware (**WHPX** on Windows, **KVM** on Linux) when it really starts, else **TCG**, and which one is said; **WHPX cannot save a snapshot**, so a session started with a snapshot runs on TCG. No `-cpu` is forced. QEMU serves one QMP client at a time: a second action meanwhile answers `busy` | **real**: QEMU 11.1 (boot-sector guest: read, atomic write, journal, undo, snapshot/rollback on TCG, pause/resume, dump, stop, WHPX; long-mode guest: physical mode and page walk; UEFI, installer and share seen in `query-block`, the share's files read back by full name; `locate` on a real dump says the guest has no OS) |
| T3 | `isolation.vmi` / `libvmi` | LibVMI (LGPL-3.0; DRAKVUF's introspection layer), located on the host, with `virsh` or `xl` | attaches to a **running** Xen or KVMi domain by name (`--domain`, on KVM also `--kvmi-socket`), never boots or destroys it, and leaves it running when the session closes. Guest physical memory through the host's LibVMI (`libvmi_io.py`, a worker: LibVMI's own physical-memory calls through ctypes in a process of their own, JSON lines on stdin/stdout, one LibVMI instance per access batch); pause/resume, snapshot/rollback by the hypervisor (`virsh suspend/resume/snapshot-create-as/snapshot-revert`; `xl pause/unpause/save -c/destroy+restore`); the RAM image read through the same worker (every chunk up to LibVMI's highest physical
address; a chunk it cannot read is zeros and is said), so a KVMi domain dumps like a Xen one. A raw address is not translated (T3 reads no vCPU register): locate the program first. Off a bare-metal Linux host (Windows, WSL2) it is not ready and says why | unit-tested with a fake LibVMI worker and fake `virsh`/`xl`; the real run needs the host |

**Programs inside a guest** (`core/isolation/guest.py`, `paging.py`; any tier whose session has
`physical()`). `locate` dumps the guest's RAM beside the session, runs **Volatility 3** on it (a
worker: `viwo/data/workers/memory.py`, Volatility's own command line with its cache under
`third_party/volatility3/`, plus ViWo's plugin `viwo_guest.Guest` from
`viwo/data/workers/volatility/`) and removes the image. The plugin lists every process with the
root of its page tables (its DTB), the paging mode, and **every file mapped in it** whatever its
kind (Windows: the loader's list, then file-backed VADs; Linux: file-backed VMAs grouped by
file) — so it holds for any program language and both OS families. Without a name `locate`
lists the processes; with a name or pid it keeps that one as the session's view
(`.runtime/isolation/view.json`). From then on `patch` writes through **that process's own page
tables** (the x86 page walk, `paging.py`: x64 with 1 GB and 2 MB pages, PAE, legacy 32-bit,
paging off), live over the tier's physical memory, whichever process the vCPU runs and on any
vCPU, and takes **each module's live base** from the view by file name (ASLR), so `--base` is no
longer needed (it still wins when given). A write spanning pages is translated whole before any
byte moves. An edit at a raw address (nothing located) is pinned to vCPU 0's address space of
that moment for its write, its readbacks and its journal entry. The journal keeps which address
space each edit was written in, and `undo` puts bytes back only where they are still the ones it
wrote (anything else is no longer ViWo's to overwrite); a session's start and stop clear the
journal. An edit whose old bytes cannot be read is not written (it could never be undone). `dump --program` writes every module of the located process as files (Volatility's own
dumper: `windows.dlllist --dump`, `linux.elfs --dump`) into `.runtime/isolation/dumps/<name>/`.
Volatility fetches a Windows kernel's symbols from Microsoft's symbol server the first time it
sees that kernel; a Linux guest needs a symbol table of its exact kernel in Volatility's cache.
A new OS family is a Volatility plugin, not a change to ViWo.

**Scylla dump-to-patch** (`core/isolation/scylla.py`, `attach.dump` / `scylla-gui`): "Continue in
Scylla" attaches to the running game and dumps its in-memory image to a reconstructed PE (IAT
rebuilt) in the workspace, which then feeds the cold-patch flow (patch sets). Scylla (NtQuery/
Scylla 0.9.8, GPL-3.0) is GUI-only with no reliable CLI, so it is a launch-and-guide handoff like
the debugger — opened as a tracked child, the console saying the steps — never a faked automation.
It is an attach-family tool, so it rides `viwo attach` / RUNTIME behind the `capture` switch (11.1).
Pinned in `tools.json` (the `.rar` release, 1,009,540 bytes, sha256
`48a4338d999ec5f33b5964c51893a04fc9e2d104b0c7786f50751f7db5dcbe52`, unpacked with 7-Zip).

The GDB remote serial client is first-party on purpose: it is a wire-protocol speaker (packets
`$…#cc`, `m`/`M`, `qRcmd`, `\x03` interrupt, `c` continue; an unasked stop reply is taken, a
trailing NUL dropped), not hypervisor, driver or evasion code (CLAUDE.md), and it keeps the
dependency to the hypervisor alone — no gdb binary need be located.

QEMU is **pinned and installed on demand** (doc 10: `viwo install qemu`); it needs no driver and
no elevation. pycdlib (`viwo install pycdlib`, LGPL-2.1, imported) and Volatility 3 (`viwo install
volatility3`, a worker, Volatility Software License) are pinned with hash locks and declared by
the tiers. VirtualBox is **unmanaged / located-only** (doc 10, 16.3): a hypervisor with a kernel
driver and a one-time elevation, which the minimal-prompts and third_party-only rules forbid
installing, so the backend locates the user's own install (the `virtualbox` dependency;
reference build `VirtualBox-7.2.22-175245-Win.exe`, 178,101,352 bytes, sha256
`afd0ff1656cbe04ed88ce619594ae021419d97cce89fa9bdc443e9a963f1713f`). LibVMI and `virsh`/`xl` are
the host's own.

**The cold+live bridge** (`core/isolation/live.py`). One patch recipe applies either way. A patch
set locates an edit in a PE as a **file offset** (`core/patchsets.py`, `core/patch_tools.py`
`address_of`); cold it is written into the patched copy (existing `patchsets.write`), live it is
written at the **virtual address** the same offset loads to, under the atomic suspend → write →
verify → resume. `located_va(data, offset, base)` turns the offset into that address (the PE's
preferred image base, or the module's live base: `--base`, or the located process's map
`{file name: base}`; a module that process has not loaded is a `not_ready` wall); `write_located`
applies one edit and `apply_live` a whole set. In a session a set is **all or nothing**: when one
edit hits a wall the edits already written are put back; every edit that stays is
**journalled** with the bytes it replaced (`.runtime/isolation/journal.jsonl`), and `undo`
restores them newest first.

**The session** (`core/isolation/session.py`). `start` boots (or, T3, attaches) the target under
a tier and leaves it running; its record (`.runtime/isolation/session.json`: the tier and the
backend's `record()`) lets every later action rejoin it, from the CLI or the API alike: `status`
(with the located program), `pause`, `resume`, `snapshot`, `rollback`, `locate`, `dump`
(`.runtime/isolation/dumps/`), `patch`, `undo`, `stop`. One session per workspace (a second
`start` answers `busy`); a record whose guest has gone is removed and said, and a located
process does not outlive its session. With no `--tier` the first ready tier by number is used.

**CLI / API** (doc 12.4). `viwo isolate` (or `--list`) lists the tiers and whether each can run
here. `viwo isolate start --workspace W (--image I | --domain D [--kvmi-socket S]) [--tier T]
[--snapshot] [--memory MB] [--cpus N] [--network] [--headless] [--halted] [--accel A] [--fresh]
[--efi] [--gpu] [--share DIR]` boots and holds a session; `viwo isolate
status|pause|resume|snapshot|rollback|undo|stop --workspace W [--name N]`, `viwo isolate locate
[--process NAME|PID]`, `viwo isolate dump [--name N] [--program]`, `viwo isolate deploy|restore --guest-dir DIR
[--patchset P] [--guest-user U]` (password from `VIWO_GUEST_PASSWORD`) and `viwo isolate patch --exe E
--patchset P [--base ADDR] [--snapshot] [--wait S] [--hold S]` act on it from another terminal. `viwo isolate EXE --patchset P
--workspace W` is the one-shot form: start, patch, close. `GET /api/runtime/isolation` →
`{tiers, enabled}`; `POST /api/runtime/isolation {action?, tier?, image?, exePath?, patchSet?,
base?, name?, snapshot?, memory?, cpus?, network?, headless?, halted?, accel?, fresh?, efi?,
gpu?, share?, domain?, kvmiSocket?, guestDir?, guestUser?, guestPassword?, process?, program?, wait?, hold?}` runs one
action (no `action`: the one-shot
form). A tier that cannot run here answers `unavailable` with exactly what it needs (never
silent). RUNTIME > ISOLATION PATCHER (`web/js/views/isolation.js`) has every option: the tiers
and their readiness, the image, tier, accelerator, memory, CPUs, network, window, UEFI + TPM,
base snapshot, fresh disk, the T3 domain, the shared folder, START to STOP, LOCATE, DUMP RAM,
DUMP PROGRAM, PATCH and UNDO.

**Holding up in a real guest** (`core/isolation/patching.py`, the `patch` action). Before a set
is written the located program is checked (an image header still at its base, `guest.present`;
`status` shows it as `present`): one that restarted is located again by name (ASLR moved it),
one that is gone is said, with the hint that a program refusing to run in a VM ends like this.
`patch --snapshot` takes a whole-guest snapshot first (`pre-patch-<time>`), so `rollback` also
undoes state the program derived from the bytes; when the program is gone once patched (a check
that exits), the guest goes back to that snapshot by itself and the result says so. `--wait S` tries the set again once a second
while its pages are not in guest RAM, so it lands as soon as the code loads. `--hold S` watches
the written bytes for S seconds and writes them again whenever the program puts them back, each
revert counted and said. `locate` records how many other processes map each module of the
program, and patching such a module says that its pages change for them too. `--gpu` gives a
VirtualBox guest VMSVGA with 3D on the host's GPU; QEMU on Windows has no 3D path, which is said.

**Cold, inside the guest** (`core/isolation/coldguest.py`; `deploy`, `restore`). The same set
written into the guest's own files before the program runs, so a check that runs once at start
sees the patched file: every file the set touches is pulled through the tier's channel into the
guest's files (`get_file`/`put_file` on the session: VirtualBox `guestcontrol copyfrom/copyto`
with a guest account, which needs Guest Additions; QEMU's guest agent, `qga.py`, over a
virtio-serial channel every QEMU session now gets on loopback, which needs `qemu-ga` in the
guest; T3 has none and says so), kept as the original once, staged in
`.runtime/isolation/cold/`, patched there by the cold writer (located, verified byte for byte)
and pushed back; a set that does not plan clean writes nothing. `restore` pushes the originals
back. The guest password comes from `VIWO_GUEST_PASSWORD` (CLI) or the request (API), is used for
that call and is never kept, logged or said (masked in an error).

**Limits** (the walls the arm does not lift): no GPU passthrough on either tier (VirtualBox's 3D
is a translation layer, enough for apps, not for heavy Direct3D/Vulkan games); nothing hides the
VM from a program that looks for one (that would be detection evasion, never first-party);
kernel anti-cheat does not start in a guest; logic a server enforces stays enforced; licensing
bound to hardware or a TPM sees a different machine; a one-time check that runs before the code
can be reached in RAM is out of reach of a live patch (use the cold patch); a self-check that
exits rather than reverting ends the program. `locate` dumps the whole guest RAM (seconds to
minutes for a large guest).
