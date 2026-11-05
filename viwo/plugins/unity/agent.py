"""runtime.unity (D2): BepInEx 6 for IL2CPP (LGPL-2.1, loaded by the game, never by ViWo) in a
patched copy. On its first start it generates the interop assemblies, real .NET assemblies of
the IL2CPP code with every type and signature, then its chainloader reports startup complete.
Its console window stays off (owner's rule). Mono games need no agent: their assemblies are in
the files already (analysis.dotnet)."""

import shutil
from pathlib import Path

from viwo.contracts.runtime import RuntimeAgent
from viwo.contracts.types import DependencySpec

BEPINEX = DependencySpec.of("bepinex")
CONFIG = "[Logging.Console]\nEnabled = false\n"
READY = "Chainloader startup complete"


class BepInExAgent(RuntimeAgent):
    backend_id, owner, license, isolation = "bepinex-agent", "unity", "LGPL-2.1", "subprocess"
    network = "download"  # its first start fetches the Unity base libraries for the game

    requires = (BEPINEX,)

    def accepts(self, copy: Path, exe: Path) -> str:
        if (exe.parent / "GameAssembly.dll").is_file():
            return ""
        return "a Mono build: its assemblies are in the files already (analysis.dotnet)"

    def install(self, copy: Path, exe: Path, ctx) -> list[str]:
        source = Path(ctx.os.tools.locate(BEPINEX).path).parent
        shutil.copytree(source, exe.parent, dirs_exist_ok=True)
        self._log(exe).unlink(missing_ok=True)  # a reused copy: the last run's log is not done
        config = exe.parent / "BepInEx" / "config" / "BepInEx.cfg"
        config.parent.mkdir(parents=True, exist_ok=True)
        if not config.is_file():
            config.write_text(CONFIG, encoding="utf-8")
        return ["-screen-fullscreen", "0", "-screen-width", "640", "-screen-height", "360"]

    def _log(self, exe: Path) -> Path:
        return exe.parent / "BepInEx" / "LogOutput.log"

    def finished(self, copy: Path, exe: Path) -> bool:
        log = self._log(exe)
        return log.is_file() and READY in log.read_text(encoding="utf-8", errors="replace")

    def outputs(self, copy: Path, exe: Path) -> list[Path]:
        interop = exe.parent / "BepInEx" / "interop"
        found = sorted(interop.glob("*.dll")) if interop.is_dir() else []
        return [*found, *([self._log(exe)] if self._log(exe).is_file() else [])]
