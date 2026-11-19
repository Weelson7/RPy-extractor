"""The isolation arm's command (doc 11.8, 12): `viwo isolate` drives a patcher session — list the
tiers and their readiness, or start a target under a tier (VirtualBox, QEMU, DRAKVUF/LibVMI),
apply a patch set live, and close. The same patch set the cold `viwo patch` writes into a copy is
written here into the running/guest target (core.isolation.live, the cold+live bridge)."""

from pathlib import Path

from viwo.contracts.errors import Envelope, ViwoError


def isolate_command(command) -> None:
    """viwo isolate (T4) arguments: list the tiers, or start a target under one and patch live."""
    iso = command("isolate", "run a target behind an isolation boundary and patch it live (T4)")
    iso.add_argument("exe", type=Path, nargs="?", help="the target executable (none: list tiers)")
    iso.add_argument("--list", action="store_true", help="only list the tiers and their readiness")
    iso.add_argument("--tier", default="", help="vbox | qemu | libvmi (default: the first ready)")
    iso.add_argument("--image", type=Path, help="guest disk image to boot (QEMU)")
    iso.add_argument("--pid", type=int, default=0, help="an already-running process to attach")
    iso.add_argument("--patchset", type=Path, help="a patch set to apply live (*.patch.json)")
    iso.add_argument("--base", type=lambda s: int(s, 0), default=0, help="live module base (ASLR)")
    iso.add_argument("--snapshot", action="store_true", help="take a base snapshot before patching")
    iso.add_argument("--workspace", type=Path, help="where .runtime/ lands (required to start)")


def isolate(rt, args, printer) -> Envelope:
    """No executable lists the tiers; with one, a session starts under a tier and patches live."""
    from viwo.core.isolation import tiers
    from viwo.core.isolation.live import IsolateRequest, drive

    if args.list or args.exe is None:
        return Envelope.success({"tiers": tiers(rt)})
    if args.workspace is None:
        raise ViwoError("invalid_request", "give --workspace <folder>")
    if not args.exe.is_file():
        raise ViwoError("not_found", f"executable not found: {args.exe}")
    req = IsolateRequest(
        args.exe, args.workspace, args.tier, args.image, args.pid,
        args.patchset, args.base, args.snapshot,
    )  # fmt: skip
    return Envelope.success(drive(rt, req, printer))
