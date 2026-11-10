"""The flags that choose the configuration of one run (doc 9.1, value source 4): `--ini`, `--os`,
`--profile`, `--features`, `--plugin <id>=on|off`, `--slot <slot>=<main>[,<spare>]`. They come
before the command; after it `--slot` and `--plugin` are the command's own."""

import argparse
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.core.wiring.boot import boot

from .cli_arms import first_word


def split_features(args) -> tuple[str, ...] | None:
    """`--features a,b` as a tuple (None when the flag is absent: the ini decides)."""
    text = getattr(args, "features", None)
    return tuple(f.strip() for f in text.split(",") if f.strip()) if text else None


def run_overrides(args) -> tuple[dict, dict] | None:
    """`--plugin <id>=on|off` and `--slot <slot>=<main>[,<spare>]` given before the command
    (doc 9.1), as ({plugin: on}, {slot: (main, spare)}); `none` empties a place."""
    plugins, slots = {}, {}
    for text in getattr(args, "plugin_overrides", None) or ():
        name, _, value = (part.strip().lower() for part in text.partition("="))
        if not name or value not in ("on", "off"):
            raise ViwoError("invalid_request", f"--plugin {text}: expected <id>=on|off")
        plugins[name] = value == "on"
    for text in getattr(args, "slot_overrides", None) or ():
        name, _, value = (part.strip() for part in text.partition("="))
        parts = ["" if p.strip() == "none" else p.strip() for p in value.split(",")]
        if not name or not value or len(parts) > 2:
            raise ViwoError("invalid_request", f"--slot {text}: expected <slot>=<main>[,<spare>]")
        slots[name.lower()] = (parts[0], (parts + [""])[1])
    return (plugins, slots) if plugins or slots else None


def boot_from(args):
    """The runtime the global flags ask for (doc 9.1, value source 4)."""
    return boot(
        args.ini,
        args.os_id,
        profile=args.profile,
        features=split_features(args),
        overrides=run_overrides(args),
    )


def global_flags(ap) -> None:
    """The flags that choose the configuration of this run; they come before the command."""
    ap.add_argument("--ini", type=Path, help="startup ini (default: startup.ini)")
    ap.add_argument("--os", dest="os_id", help="auto | linux | windows")
    ap.add_argument("--profile", help="a distro's plugin set (renpy, unity, ..., custom, mixed)")
    ap.add_argument("--features", help="comma-separated [startup] features for this run")
    ap.add_argument(
        "--plugin",
        dest="plugin_overrides",
        action="append",
        metavar="ID=on|off",
        help="a plugin on or off for this run (repeatable; before the command)",
    )
    ap.add_argument(
        "--slot",
        dest="slot_overrides",
        action="append",
        metavar="SLOT=MAIN[,SPARE]",
        help="a slot's backends for this run (repeatable; before the command)",
    )


def boot_for_cli(argv: list[str]):
    """Boot early so plugin add-on commands can join the parser (the global flags are read
    first, up to the command word: after it `--slot` and `--plugin` are the command's own).
    A bad configuration returns None here; the command itself reports it."""
    pre = argparse.ArgumentParser(add_help=False)
    global_flags(pre)
    word = first_word(argv)
    known, _ = pre.parse_known_args(argv[:word] if word >= 0 else argv)
    try:
        return boot_from(known)
    except Exception:  # noqa: BLE001 (reported by the real boot in _run)
        return None
