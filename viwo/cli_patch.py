"""The patching arm's commands (doc 16.2b T1-T2): `viwo patch` and `viwo mod`."""

from __future__ import annotations

from viwo.contracts.errors import Envelope, ViwoError


def patch(rt, args, printer) -> Envelope:
    from viwo.core import patchsets

    if not args.game.is_dir():
        raise ViwoError("not_found", f"game folder not found: {args.game}")
    if args.plan:
        return Envelope.success(patchsets.plan(args.game, patchsets.load(args.patchset), rt.os))
    if args.out is None:
        raise ViwoError("invalid_request", "give --out <folder> (or --plan)")
    return Envelope.success(patchsets.apply(rt, args.game, args.patchset, args.out, printer))


def mod(rt, args, printer) -> Envelope:
    from viwo.core import mods

    if args.action == "check":
        return Envelope.success({"mods": [mods.check(args.game, m) for m in args.mod]})
    if args.copy is None:
        raise ViwoError("invalid_request", f"mod {args.action} needs --copy <patched copy>")
    if args.action == "pack":
        split = lambda text: [s.strip() for s in text.split(",") if s.strip()]  # noqa: E731
        needs = {"requires": split(args.requires), "after": split(args.after)}
        return Envelope.success(mods.pack(args.game, args.copy, args.mod[0], args.name, needs))
    return Envelope.success(mods.apply(rt, args.game, args.mod, args.copy, printer))
