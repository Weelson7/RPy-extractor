"""Scylla dump-to-patch (doc 11.8): "Continue in Scylla" attaches to the running game and dumps
its in-memory image to a reconstructed PE (IAT rebuilt) in the workspace, which then feeds the
cold-patch flow (patch sets, doc 18.8). Scylla (NtQuery/Scylla, GPL-3.0) is GUI-only with no
reliable CLI, so ViWo wires it as a launch-and-guide handoff like the debugger, never a faked
automation: it opens Scylla as a tracked child and the console says the steps. It is an
attach-family tool, so it rides the dynamic arm's `viwo attach` / RUNTIME surface behind the
`capture` switch (doc 11.1); its slot is `attach.dump`."""

from viwo.contracts.analysis import AnalysisTarget, Handoff, LaunchSpec
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

SCYLLA = DependencySpec.of("scylla")
STEPS = (
    "In Scylla: pick the game in the process list, then Dump, then Fix Dump (or IAT Autosearch "
    "-> Get Imports -> Fix Dump); save the rebuilt PE into {folder}",
    "The rebuilt PE feeds the cold-patch flow: point a patch set at it (doc 18.8)",
)


class ScyllaDump(Handoff):
    backend_id, license, isolation = "scylla-gui", "GPL-3.0", "subprocess"
    label, accepts, families = "Continue in Scylla", ("native_binary",), frozenset({"attach"})
    self_check_args = ()  # a GUI: never started just to answer
    requires = (SCYLLA,)

    def prepare(self, target: AnalysisTarget, ctx) -> LaunchSpec | Outcome:
        tool = ctx.os.tools.locate(SCYLLA)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=SCYLLA.hint)
        ctx.staging.mkdir(parents=True, exist_ok=True)
        for line in STEPS:
            ctx.log(line.format(folder=ctx.staging), "info")
        return LaunchSpec(tuple(str(a) for a in tool.argv_prefix), ctx.staging)
