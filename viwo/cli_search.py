"""`viwo search` (static arm, doc 6.7): a string, a number or a byte pattern in a workspace, a
game folder or one file (an exe, a dll), which are only read; the report lands in the
workspace's `.search/`, and each hit can go straight into a patch set (doc 18.8)."""

from pathlib import Path

from viwo.contracts.errors import Envelope, ViwoError

WHAT = "a workspace, a game folder or one file (an exe, a dll); only read"


def search_command(command) -> None:
    """viwo search arguments: one of --text, --number, --bytes, and the caps."""
    se = command("search", "find a string, a number or a byte pattern in files (read-only)")
    se.add_argument("target", type=Path, help=WHAT)
    what = se.add_mutually_exclusive_group(required=True)
    what.add_argument("--text", help="a string, tried as UTF-8, UTF-16LE and UTF-16BE")
    what.add_argument("--number", help="an integer (100, -5, 0x64) or a float (1.5, 1e3)")
    what.add_argument("--bytes", dest="pattern", help='bytes, ?? = any byte: "48 8B ?? 05"')
    se.add_argument("-i", "--ignore-case", action="store_true", help="text: any case")
    se.add_argument("--widths", default="2,4,8", help="integer widths in bytes (add 1: 1,2,4,8)")
    se.add_argument(
        "--workspace", type=Path, help="where .search/ lands (default: the one searched)"
    )
    se.add_argument("--max-hits", type=int, default=1000, help="hits overall (said when reached)")
    se.add_argument("--per-file", type=int, default=100, help="hits per file (said when reached)")
    se.add_argument("--context", type=int, default=16, help="bytes shown before and after a hit")
    se.add_argument("--signatures", type=int, default=8, help="unique AOB signatures per file")


def search(rt, args, printer) -> Envelope:
    from viwo.core import search as core
    from viwo.core.search_query import build

    given = {"text": args.text, "number": args.number, "bytes": args.pattern}
    kind, value = next((k, v) for k, v in given.items() if v is not None)
    query = build(kind, value, args.ignore_case, args.widths)
    limits = core.Limits(args.per_file, args.max_hits, args.context, args.signatures)
    if not args.target.exists():
        raise ViwoError("not_found", f"nothing to search at {args.target}", hint=WHAT)
    folder = core.results_folder(args.target, args.workspace)
    report = core.search(args.target, query, limits, printer, None, folder)
    unsaved = [] if folder else ["the results were not saved: give --workspace <folder>"]
    return Envelope.success(report, report["warnings"] + unsaved)


def text(d: dict) -> str:
    """The hits, one block each: where, the bytes around it, the signature; then the totals."""
    lines = []
    for hit in d["hits"]:
        where = f"{hit['file']} @ {hit['offset']:#x} [{hit['encoding']}]"
        if hit.get("section") is not None:
            where += f" {hit['section']} rva {hit['rva']:#x} va {hit['va']:#x}"
        lines += [where, f"    {hit['before']} [{hit['match']}] {hit['after']}".rstrip()]
        sig = hit.get("signature") or {}
        if "pattern" in sig:
            lines.append(f"    sig {sig['pattern']} at {sig['at']}")
        elif sig:
            lines.append(f"    no sig: {sig['error']}")
    q = d["query"]
    lines.append(
        f"{d['hitCount']:,} hit(s) in {d['filesWithHits']:,} of {d['searched']:,} file(s) "
        f"searched for {q['kind']} {q['value']!r} as {', '.join(q['tried'])}"
    )
    lines += [f"note: {n}" for n in q["notes"]]
    if d.get("saved"):
        lines.append(f"Saved: {d['saved']}")
    return "\n".join(lines)
