"""The isolation arm's command (doc 11.8, 12): `viwo isolate` lists the tiers, `viwo isolate start`
boots a target behind one (VirtualBox, QEMU, DRAKVUF/LibVMI) and holds it until the guest ends or
Ctrl+C, and every other action (status, pause, resume, snapshot, rollback, dump, patch, undo,
stop, and `locate` to find a program inside the guest) is run from another terminal against the
session the workspace records. `viwo isolate EXE`
is the one-shot form: start, apply `--patchset` live, close. `patch` writes the
same patch set the cold `viwo patch` writes into a copy into the guest (core.isolation.live)."""

import time
from pathlib import Path

from viwo.contracts.errors import Envelope, ViwoError

GUEST = (
    "memory_mb", "cpus", "network", "headless", "halted", "accel", "fresh", "efi", "share", "gpu",
)  # fmt: skip


def isolate_command(command) -> None:
    """viwo isolate (T4) arguments: an action and what it needs."""
    from viwo.core.isolation.session import ACTIONS

    iso = command("isolate", "run a target behind an isolation boundary and patch it live (T4)")
    names = " | ".join(("list", "start", *ACTIONS))
    iso.add_argument("action", nargs="?", default="list", help=f"{names}, or an executable")
    iso.add_argument("--list", action="store_true", help="only list the tiers and their readiness")
    iso.add_argument("--halted", action="store_true", help="start: stopped at the first step")
    iso.add_argument("--workspace", type=Path, help="where .runtime/isolation/ lands")
    iso.add_argument("--tier", default="", help="vbox | qemu | libvmi (default: the first ready)")
    iso.add_argument("--image", type=Path, help="start: guest disk image (never written)")
    iso.add_argument("--exe", type=Path, help="patch: the program the patch set is located in")
    iso.add_argument("--patchset", type=Path, help="patch: a patch set (*.patch.json)")
    iso.add_argument("--base", type=lambda s: int(s, 0), default=0, help="live module base (ASLR)")
    iso.add_argument("--name", default="", help="snapshot, rollback, dump: its name")
    iso.add_argument(
        "--snapshot", action="store_true", help="start: a base snapshot; patch: one first"
    )
    iso.add_argument("--gpu", action="store_true", help="start: 3D acceleration (vbox)")
    iso.add_argument("--wait", type=float, default=0, help="patch: seconds to wait for pages")
    iso.add_argument("--hold", type=float, default=0, help="patch: seconds to keep it written")
    iso.add_argument("--memory", dest="memory_mb", type=int, default=4096, help="guest RAM in MB")
    iso.add_argument("--cpus", type=int, default=2, help="guest CPUs")
    iso.add_argument("--network", action="store_true", help="start: give the guest a network")
    iso.add_argument("--headless", action="store_true", help="start: no guest window")
    iso.add_argument("--accel", default="", help="start: whpx | kvm | tcg (default: picked)")
    iso.add_argument("--fresh", action="store_true", help="start: discard the earlier overlay")
    iso.add_argument("--pid", type=int, default=0, help="an already-running process to attach")
    iso.add_argument("--efi", action="store_true", help="start: UEFI (VirtualBox adds a vTPM 2.0)")
    iso.add_argument("--share", type=Path, help="start: a folder the guest reads (read-only)")
    iso.add_argument("--process", default="", help="locate: a program name or pid in the guest")
    iso.add_argument("--program", action="store_true", help="dump: the located program's files")
    iso.add_argument("--domain", default="", help="start (libvmi): the running domain to attach")
    iso.add_argument("--kvmi-socket", default="", help="start (libvmi on KVM): its KVMi socket")


def _guest(args) -> dict:
    """The guest options of a start; a T3 domain (and its KVMi socket) rides in `args`."""
    guest = {key: getattr(args, key, None) for key in GUEST}
    guest = {key: value for key, value in guest.items() if value is not None}
    if getattr(args, "domain", ""):
        guest["args"] = (args.domain, getattr(args, "kvmi_socket", ""))
    return guest


def _hold(session, workspace: Path) -> bool:
    """Keep the guest until it ends by itself (True) or Ctrl+C stops it (False)."""
    from viwo.core.isolation.session import forget

    try:
        while session.alive():
            time.sleep(1.0)
        return True
    except KeyboardInterrupt:
        session.close()
        return False
    finally:
        forget(workspace)


def _one_shot(rt, args, printer) -> dict:
    """`viwo isolate EXE ...`: start the target under a tier, patch it live, close."""
    from viwo.core.isolation import session as sessions

    exe = Path(args.action)
    if not exe.is_file():
        raise ViwoError("not_found", f"executable not found: {exe}", hint="or an action name")
    req = sessions.IsolateRequest(
        args.workspace, args.image, exe, args.tier, args.pid, args.snapshot, _guest(args)
    )
    return sessions.drive(rt, req, args.patchset, args.base, printer)


def isolate(rt, args, printer) -> Envelope:
    """`list` (or no action) names the tiers; `start` boots and holds; the rest act on the
    workspace's running session."""
    from viwo.core.isolation import session as sessions
    from viwo.core.isolation import tiers

    if args.action == "list" or args.list:
        return Envelope.success({"tiers": tiers(rt)})
    if args.workspace is None:
        raise ViwoError("invalid_request", "give --workspace <folder>")
    if args.action not in ("start", *sessions.ACTIONS):  # the one-shot form: an executable
        return Envelope.success(_one_shot(rt, args, printer))
    if args.action != "start":
        opt = {"name": args.name, "exe": args.exe, "patchset": args.patchset, "base": args.base}
        opt.update(target=args.process, program=args.program, snapshot=args.snapshot)
        opt.update(wait=args.wait, hold=args.hold)
        return Envelope.success(sessions.act(rt, args.workspace, args.action, printer, **opt))
    req = sessions.IsolateRequest(
        args.workspace, args.image, args.exe, args.tier, args.pid, args.snapshot,
        _guest(args),
    )  # fmt: skip
    info, session = sessions.start(rt, req, printer)
    return Envelope.success(
        {**info, "ended": "guest" if _hold(session, args.workspace) else "user"}
    )
