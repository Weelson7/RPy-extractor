"""analysis.emulate and analysis.symbolic (doc 6.2, rung A4): one isolated routine of a game
binary (a decoder, a checksum, a key schedule) run outside the game in Unicorn, or its inputs
solved in angr. Both are worker tools (core/workers.py): GPL code behind a process boundary.

Options (`viwo analyze --set key=value`, or the API's `options`):
  start      the routine: 0x<va> | rva:0x<rva> | export:<name>            (required)
  args       comma-separated: <int> | hex:<bytes> | file:<path> | zeros:<n> | sym:<n> (symbolic)
  dump       emulate: argN:<size>,... buffers written after the run (argN = the Nth pointer)
  max_insns  emulate: instruction budget (default 1,000,000)
  find       symbolic: the address to reach (required); avoid: comma-separated addresses
The worker writes result.json (status, return value, reason) and the dumped or solved buffers."""

from viwo.contracts.analysis import Analyzer
from viwo.contracts.errors import ViwoError
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from ._process import failed, run_tool

UNICORN = DependencySpec.of("unicorn")
ANGR = DependencySpec.of("angr")
ARG_KINDS = ("hex", "file", "zeros", "sym")


def parse_arg(text: str) -> dict:
    """One routine argument: an integer, or a buffer whose address is passed instead."""
    kind, _, value = text.strip().partition(":")
    if kind in ARG_KINDS and value:
        return {kind: int(value, 0) if kind in ("zeros", "sym") else value}
    try:
        return {"int": int(text.strip(), 0)}
    except ValueError:
        raise ViwoError("invalid_request", f"bad routine argument {text!r}", hint=__doc__) from None


def worker_spec(binary, options: dict, symbolic: bool) -> dict:
    """The worker's job, validated here so a bad request fails before any process starts."""
    if not options.get("start"):
        raise ViwoError("invalid_request", "give the routine's address: start=0x...", hint=__doc__)
    split = lambda key: [x for x in str(options.get(key, "")).split(",") if x.strip()]  # noqa: E731
    spec = {"binary": str(binary), "start": str(options["start"])}
    spec["args"] = [parse_arg(a) for a in split("args")]
    if symbolic:
        if not options.get("find"):
            raise ViwoError("invalid_request", "give the address to reach: find=0x...")
        return {**spec, "find": str(options["find"]), "avoid": split("avoid")}
    dumps = [d.split(":") for d in split("dump")]
    if any(len(d) != 2 or not d[0].startswith("arg") for d in dumps):
        raise ViwoError("invalid_request", "dump entries look like arg0:256", hint=__doc__)
    spec["dump"] = [{"arg": int(a[3:]), "size": int(n, 0)} for a, n in dumps]
    return {**spec, "max_insns": int(options.get("max_insns") or 1_000_000)}


class _Worker(Analyzer):
    """Shared run: locate the worker, hand it the spec, read result.json back."""

    kinds = ("native_binary",)
    dependency: DependencySpec
    symbolic = False

    def dependencies(self):
        return (self.dependency,)

    def analyze(self, target, ctx) -> Outcome:
        import json

        if (tool := ctx.os.tools.locate(self.dependency)) is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=self.dependency.hint)
        spec = worker_spec(target.paths[0], dict(ctx.options), self.symbolic)
        (ctx.scratch / "worker-spec.json").write_text(json.dumps(spec), encoding="utf-8")
        argv = [*tool.argv_prefix, str(ctx.scratch / "worker-spec.json"), str(ctx.staging)]
        ctx.log(f"{self.backend_id}: {target.paths[0].name} from {spec['start']}", stage="analyze")
        result = run_tool(ctx, argv, None, 600)
        try:
            report = json.loads((ctx.staging / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return failed(result, f"{self.backend_id} wrote no result.json")
        line = f"{report.get('status')}: {report.get('reason') or report.get('summary', '')}"
        if report.get("status") not in self.done:
            return Outcome(OutcomeKind.FAILED, error=line[:400])
        return Outcome(OutcomeKind.OK, len(report.get("files", ())) + 1, notes=(line[:300],))


class UnicornEmulate(_Worker):
    backend_id, license, isolation = "unicorn-emulate", "GPL-2.0", "subprocess"
    dependency, done = UNICORN, ("returned", "limit")


class AngrSymbolic(_Worker):
    backend_id, license, isolation = "angr-symbolic", "BSD-2-Clause", "subprocess"
    dependency, done, symbolic = ANGR, ("found",), True
