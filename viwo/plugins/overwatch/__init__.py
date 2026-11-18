"""Overwatch (D16): static extraction of the local install through DataTool (overtools).

Marked terms-of-service sensitive: every run, capture and repack carries a reminder (nothing is
refused; the user is responsible), and real-game testing is done by the independent operator
(doc 17.4b).
"""

import re

from viwo.contracts.plugin import (
    EnginePlugin,
    GameProbe,
    PluginManifest,
    PluginOption,
    VerifyReport,
)
from viwo.contracts.slots import Exporter, SlotDefinition
from viwo.contracts.types import DependencySpec, DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files

from . import owmdl

DATATOOL = DependencySpec.of("datatool")
MODES = "extract-unlocks,extract-general,extract-maps"
KNOWN_MODES = frozenset(
    MODES.split(",")
    + ["extract-hero-unlocks", "extract-npcs", "extract-lootbox", "extract-debug-vox"]
    + ["list-heroes", "list-maps", "list-general-unlocks", "list-unlocks"]
)
MODE_NAME = re.compile(r"^[a-z][a-z0-9-]*$")


def parse_modes(raw) -> tuple[list[str], str]:
    """(modes, problem): every mode must be a known DataTool mode name."""
    modes = [m.strip() for m in str(raw or MODES).split(",") if m.strip()]
    bad = [m for m in modes if not MODE_NAME.match(m) or m not in KNOWN_MODES]
    if bad or not modes:
        return [], f"invalid_request: unknown DataTool mode(s): {', '.join(bad) or '(none)'}"
    return modes, ""


def queries(raw, modes: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """The `query` option per extract mode, each `;` entry one DataTool argument as given:
    `extract-maps: Rialto` goes to that mode, a `--flag` to every extract mode, anything else
    to extract-unlocks. Returns ({mode: its arguments}, the entries no running mode takes)."""
    out: dict[str, list[str]] = {m: [] for m in modes if m.startswith("extract-")}
    unused = []
    for entry in filter(None, (e.strip() for e in str(raw or "").split(";"))):
        head, colon, rest = entry.partition(":")
        if entry.startswith("--"):
            targets, words = list(out), entry
        elif colon and head.strip() in KNOWN_MODES:
            targets, words = [head.strip()], rest.strip()
        else:
            targets, words = ["extract-unlocks"], entry
        targets = [m for m in targets if m in out] if words else []
        for mode in targets:
            out[mode].append(words)
        if not targets:
            unused.append(entry)
    return out, unused


MANIFEST = PluginManifest(
    "overwatch",
    "Overwatch (DataTool)",
    "0.1.0",
    engine_type="overwatch",
    priority=5,
    tos_sensitive=True,
    options=(
        PluginOption("modes", "DataTool modes to run, comma separated", "string", MODES),
        PluginOption(
            "query",
            "what to extract, in DataTool's own words, `;` between several: an entry goes to "
            "extract-unlocks (`Tracer|skin=Classic;Mercy|skin=Classic`), `mode: words` to that "
            "mode (`extract-maps: Rialto`), a `--flag` to every extract mode; empty: everything",
            "string",
            "",
        ),
        PluginOption(
            "models",
            "glb: every model also as a self-contained .glb (rig, weights, colour and normal "
            "textures); owmdl: DataTool's own files only",
            "string",
            "glb",
        ),
    ),
)
REMINDER = "Overwatch: personal, offline use of your own install; respect Blizzard's terms"


class DataToolExporter(Exporter):
    """DataTool reads the local CASC install; it may fetch missing keys itself, so it declares
    `download` (doc 11.6). ViWo passes no online switch; the user goes offline (REMINDER)."""

    backend_id, owner, license, isolation = "datatool", "overwatch", "MIT", "subprocess"
    network = "download"

    requires = (DATATOOL,)

    def export(self, ctx) -> Outcome:
        if (tool := ctx.os.tools.locate(DATATOOL)) is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=DATATOOL.hint)
        modes, problem = parse_modes(ctx.options.get("modes"))
        if problem:
            return Outcome(OutcomeKind.FAILED, error=problem)
        asked, unused = queries(ctx.options.get("query"), modes)
        failed, notes = [], (REMINDER,)
        if unused:  # never silent: a query entry no running mode takes
            notes += (f"query entries no running mode takes (not used): {'; '.join(unused)}",)
            ctx.log(notes[-1], "warn", stage="export")
        for mode in modes:
            out = ctx.staging / mode
            query = asked.get(mode, [])  # each one argument, as given
            ctx.log(f"DataTool {mode} {' '.join(query)}".rstrip(), stage="export")
            argv = [*tool.argv_prefix, str(ctx.game_root), mode, str(out), *query]
            relay = ctx.tool_output("export", every=5.0)  # DataTool's own lines, live
            done = ctx.os.process.run(argv, timeout=12 * 3600, cancel=ctx.cancel, on_line=relay)
            if not done.ok:
                failed.append(mode)
        notes += (f"failed modes: {', '.join(failed)}",) if failed else ()
        if str(ctx.options.get("models") or "glb").lower() != "owmdl":
            ctx.log("Models to glTF (.glb beside each .owmdl)", stage="export")
            made, lost = owmdl.convert_all(ctx.staging, getattr(ctx, "each", map))
            notes += (f"{made} model(s) also written as .glb",) if made else ()
            notes += (f"{len(lost)} model(s) not converted, e.g. {lost[0]}",) if lost else ()
        files = count_files(ctx.staging)
        if failed and not files:
            return Outcome(OutcomeKind.FAILED, error=f"DataTool failed: {', '.join(failed)}")
        return Outcome(OutcomeKind.OK, files, notes=notes)


class OverwatchPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = ()
        if probe.has_name("overwatch.exe", "overwatch launcher.exe"):
            evidence += ("Overwatch executable",)
        battle_net = probe.has_name(".build.info") and probe.find("casc", limit=1)
        steam = probe.has_name(".build.config") and probe.find("data/data.[0-9]*", limit=1)
        if battle_net or steam:
            evidence += ("Blizzard CASC storage",)
        score = 0.95 if len(evidence) == 2 else (0.6 if evidence else 0.0)
        return DetectionResult("overwatch", score, evidence, "overwatch")

    def slot_definitions(self):
        return (SlotDefinition("export.overwatch", "export", "overwatch", "datatool"),)

    def backends(self):
        return (DataToolExporter(),)

    def export_slot(self) -> str:
        return "export.overwatch"

    def skip_dirs(self):
        return ("data",)  # CASC storage: DataTool reads it; never copied raw

    def verify_report(self, ctx, inventory, export, collected: int) -> VerifyReport:
        return VerifyReport(True, (REMINDER,))
