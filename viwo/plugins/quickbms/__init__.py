"""QuickBMS bridge (D21, rung 6): any custom archive format with a community .bms script.

Point [options.quickbms] scripts = <folder> at your scripts. A script named "<ext>.bms" or
"<ext>.<anything>.bms" handles files ending in .<ext> that nothing else recognizes, in
every game. QuickBMS (GPL-2.0) runs as a separate process.
Flags (-o overwrite, -Y yes to prompts) follow the QuickBMS documentation.
"""

from __future__ import annotations

from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Match, SlotDefinition, Unarchiver
from viwo.contracts.types import DependencySpec, DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files

QUICKBMS = DependencySpec(
    "quickbms",
    "QuickBMS",
    env_var="VIWO_QUICKBMS",
    executables=("quickbms", "quickbms_4gb_files"),
    install_dirs=("quickbms",),
    hint="install QuickBMS (GPL-2.0) and set [options.quickbms] scripts = <folder of .bms>",
)
MANIFEST = PluginManifest("quickbms", "QuickBMS scripts", "0.1.0", engine_type="any", priority=-50)


class ScriptTable:
    """Suffix -> script, filled from the configured folder."""

    def __init__(self) -> None:
        self.scripts: dict[str, Path] = {}

    def load(self, folder: str) -> None:
        root = Path(folder).expanduser()
        if not root.is_dir():
            raise ValueError(f"scripts folder not found: {root}")
        for script in sorted(root.glob("*.bms")):
            self.scripts.setdefault("." + script.name.split(".", 1)[0].lower(), script)

    def identify(self, path: Path, head: bytes, tail: bytes) -> Match | None:
        return Match("unarchive.bms", path) if path.suffix.lower() in self.scripts else None


class QuickBmsCli(Unarchiver):
    backend_id, owner, license, isolation = "quickbms-cli", "quickbms", "GPL-2.0", "subprocess"

    def __init__(self, table: ScriptTable) -> None:
        self.table = table

    def dependencies(self):
        return (QUICKBMS,)

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        tool, script = ctx.os.tools.locate(QUICKBMS), self.table.scripts.get(archive.suffix.lower())
        if tool is None or script is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=QUICKBMS.hint)
        argv = [*tool.argv_prefix, "-o", "-Y", str(script), str(archive), str(dest)]
        result = ctx.os.process.run(argv, timeout=3600, cancel=ctx.cancel)
        files = count_files(dest)
        if not result.ok or not files:
            return Outcome(OutcomeKind.FAILED, error=(result.stderr or result.stdout)[-300:])
        return Outcome(OutcomeKind.OK, files, notes=(f"script {script.name}",))


PLUGIN = "QuickBmsPlugin"  # discovered by viwo.core.wiring.registry


class QuickBmsPlugin(EnginePlugin):
    def __init__(self) -> None:
        self.table = ScriptTable()

    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def configure(self, options) -> None:
        """`[options.quickbms] scripts`, else the pinned scripts folder under third_party/."""
        folder = options.get("scripts") or (
            self.home / "third_party" / "quickbms" / "scripts" if self.home else ""
        )
        if folder and Path(folder).is_dir():
            self.table.load(str(folder))

    def detect(self, probe: GameProbe) -> DetectionResult:
        return DetectionResult("any", 0.0, (), "quickbms")  # never picks a game: it serves all

    def slot_definitions(self):
        return (
            SlotDefinition(
                "unarchive.bms",
                "unarchive",
                "quickbms",
                "quickbms-cli",
                identify=self.table.identify,
            ),
        )

    def backends(self):
        return (QuickBmsCli(self.table),)
