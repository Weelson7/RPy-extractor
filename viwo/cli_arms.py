"""The CLI grouped by ViWo's three arms (plus system): `viwo --help` lists the commands per arm,
`viwo <arm>` lists one arm, `viwo <arm> <command> ...` runs the command; flat verbs still work."""

from __future__ import annotations

STATIC = ("survey", "detect", "extract", "replay", "unpack", "sanitize", "analyze", "diff")
SYSTEM = ("serve", "info", "slots", "install", "config", "indexes", "diag", "workbook")
ARMS = {
    "static": ("the game is not running", STATIC),
    "dynamic": (
        "the game is running",
        ("capture", "dump", "trace", "profile", "agent", "record", "attach"),
    ),
    "patching": ("you change its content", ("repack", "patch", "mod")),
    "system": ("tools, config, the web UI", SYSTEM),
}
VALUED = {"--ini", "--os", "--profile", "--features"}


def first_word(argv: list[str]) -> int:
    """Index of the first command word (global flags and their values skipped), or -1."""
    skip = False
    for i, token in enumerate(argv):
        if skip:
            skip = False
        elif token in VALUED:
            skip = True
        elif not token.startswith("-"):
            return i
    return -1


def split_arm(argv: list[str]) -> tuple[str, list[str]]:
    """(arm, argv without the arm word) when the first command word is an arm, else ("", argv)."""
    i = first_word(argv)
    if i < 0 or argv[i] not in ARMS:
        return "", argv
    return argv[i], argv[:i] + argv[i + 1 :]


def listing(helps: dict[str, str], arms: tuple[str, ...] = tuple(ARMS)) -> str:
    """Command lines grouped by arm; commands of no arm (add-ons) come last."""
    lines, placed = [], set()
    for arm in arms:
        what, names = ARMS[arm]
        lines.append(f"{arm} ({what}):")
        for name in (n for n in names if n in helps):
            lines.append(f"  {name:<10} {helps[name]}")
            placed.add(name)
    extra = [n for n in helps if n not in placed] if len(arms) == len(ARMS) else []
    if extra:
        lines += ["add-ons:", *(f"  {name:<10} {helps[name]}" for name in extra)]
    return "\n".join(lines)


def group_commands(parser, sub) -> None:
    """Replace argparse's flat command list by the grouped one, in the parser's description."""
    parser.viwo_helps = {a.dest: a.help or "" for a in sub._choices_actions}
    sub._choices_actions = []
    parser.description += "\n\ncommands, by arm (`viwo <arm>` lists one):\n"
    parser.description += listing(parser.viwo_helps)
