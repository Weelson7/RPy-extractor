"""runtime.unreal (D2): UE4SS (MIT) in a patched copy writes the `.usmap` mappings that UE5 assets
with unversioned properties need, and a dump of every UObject, then tells ViWo it is done.
Its GUI console and its bundled mods stay off (owner's rule: nothing on screen but the game)."""

from __future__ import annotations

import shutil
from pathlib import Path

from viwo.contracts.runtime import RuntimeAgent
from viwo.contracts.types import DependencySpec

UE4SS = DependencySpec(
    "ue4ss",
    "UE4SS (Unreal runtime agent)",
    env_var="VIWO_UE4SS",
    executables=("UE4SS.dll",),
    hint="install UE4SS (MIT): `viwo install ue4ss`",
)
MOD = "ViwoDump"
DONE = "viwo-done.txt"
LUA = """-- Written by ViWo: once the game has loaded, write the mappings and the object dump.
ExecuteWithDelay({delay}, function()
  pcall(DumpUSMAP)
  pcall(DumpAllObjects)
  local f = io.open("{done}", "w")
  if f then f:write("done") f:close() end
end)
"""
QUIET = {"GuiConsoleEnabled": "0", "GuiConsoleVisible": "0", "ConsoleEnabled": "0"}


def shipping(copy: Path, exe: Path) -> Path | None:
    """The `<Project>-Win64-Shipping.exe` the launcher starts (UE4SS goes next to it)."""
    if exe.stem.lower().endswith("-shipping"):
        return exe
    found = sorted(copy.glob("*/Binaries/Win64/*-Shipping.exe"))
    return found[0] if found else None


def _settings(path: Path) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        out.append(f"{key} = {QUIET[key]}" if key in QUIET else line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


class Ue4ssAgent(RuntimeAgent):
    backend_id, owner, license, isolation = "ue4ss-agent", "unreal", "MIT", "subprocess"
    delay_ms = 20000  # the game's own startup first

    def dependencies(self):
        return (UE4SS,)

    def accepts(self, copy: Path, exe: Path) -> str:
        return "" if shipping(copy, exe) else "no <Project>/Binaries/Win64/*-Shipping.exe"

    def install(self, copy: Path, exe: Path, ctx) -> list[str]:
        win64 = shipping(copy, exe).parent
        source = Path(ctx.os.tools.locate(UE4SS).path).parent
        shutil.copytree(source, win64, dirs_exist_ok=True)
        _settings(win64 / "UE4SS-settings.ini")
        mods = win64 / "Mods"
        listed = (mods / "mods.txt").read_text(encoding="utf-8-sig").splitlines()
        off = [line.replace(": 1", ": 0") for line in listed if ":" in line]
        (mods / "mods.txt").write_text("\n".join([*off, f"{MOD} : 1"]) + "\n", encoding="utf-8")
        script = mods / MOD / "Scripts" / "main.lua"
        script.parent.mkdir(parents=True, exist_ok=True)
        done = (win64 / DONE).as_posix()
        script.write_text(LUA.format(delay=self.delay_ms, done=done), encoding="utf-8")
        return ["-windowed", "-ResX=640", "-ResY=360"]

    def finished(self, copy: Path, exe: Path) -> bool:
        return (shipping(copy, exe).parent / DONE).is_file()

    def outputs(self, copy: Path, exe: Path) -> list[Path]:
        win64 = shipping(copy, exe).parent
        names = ("Mappings.usmap", "UE4SS_ObjectDump.txt", "UE4SS.log")
        return [win64 / n for n in names if (win64 / n).is_file()]
