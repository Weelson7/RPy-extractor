"""D3 attach tools (doc 11.2, 8.3a, 16.2b), the dynamic arm's `attach.*` slots: "Continue in
x64dbg" attaches the debugger to the game's running process (`-p PID`), or starts the game's own
executable under it, so a live patch lands in the real process (x64dbg is GPL-3: a separate
process, pinned); "Continue in Cheat Engine" opens a starter table that attaches to the game as
soon as it runs (Cheat Engine unpacked by the startup check). Both run as tracked children of
ViWo, like the Ghidra GUI."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from viwo.contracts.analysis import AnalysisTarget, Handoff, LaunchSpec
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from ..patch_tools import pe

ATTACH = frozenset({"attach"})  # the slot family: Handoff's interface, run on the live game

X64DBG = DependencySpec(
    "x64dbg",
    "x64dbg (debugger)",
    env_var="VIWO_X64DBG",
    executables=("x64dbg",),
    hint="install x64dbg (GPL-3, run as a separate process): `viwo install x64dbg`",
)
CHEATENGINE = DependencySpec(
    "cheatengine",
    "Cheat Engine",
    env_var="VIWO_CHEATENGINE",
    executables=("cheatengine-x86_64",),
    install_dirs=("Cheat Engine 7.7", "Cheat Engine 7.6", "Cheat Engine 7.5", "Cheat Engine"),
    hint="install Cheat Engine: `viwo install cheatengine`",
)
TABLE = """<?xml version="1.0" encoding="utf-8"?>
<CheatTable CheatEngineTableVersion="45">
  <CheatEntries/>
  <LuaScript>-- Written by ViWo: attach to {name} as soon as it runs.
local name = "{name}"
local timer = createTimer(nil)
timer.Interval = 1000
timer.OnTimer = function(t)
  if getProcessIDFromProcessName(name) ~= nil then
    openProcess(name)
    t.destroy()
  end
end
</LuaScript>
</CheatTable>
"""


def table_name(name: str) -> str:
    """An executable name inside the table's Lua string, inside its XML: "&", "<", quotes and
    backslashes in names ("Command & Conquer.exe") would otherwise break the table."""
    lua = name.replace("\\", "\\\\").replace('"', '\\"')
    return escape(lua)


def _bits(exe: Path) -> int:
    with open(exe, "rb") as fh:
        info = pe(fh.read(4096))
    return 32 if info and info["machine"] == 0x14C else 64


def quiet_x64dbg(debugger: Path) -> None:
    """Pre-answer x64dbg's release-notes window off screen (owner's rule): it opens while the
    stored [Gui] ReleaseNotesEpoch is older than the build, in the ini next to the debugger."""
    ini = debugger.with_suffix(".ini")
    text = ini.read_text(encoding="utf-8", errors="replace") if ini.is_file() else ""
    if "ReleaseNotesEpoch=" in text:
        return  # already answered (by x64dbg or by the user)
    line = "ReleaseNotesEpoch=9999999999"  # later than any build, read as decimal or hex
    if "[Gui]" in text:
        text = text.replace("[Gui]", f"[Gui]\n{line}", 1)
    else:
        text = text.rstrip("\n") + ("\n" if text else "") + f"[Gui]\n{line}\n"
    ini.write_text(text, encoding="utf-8")


class X64dbgGui(Handoff):
    backend_id, license, isolation = "x64dbg-gui", "GPL-3.0", "subprocess"
    label, accepts, families = "Continue in x64dbg", ("native_binary",), ATTACH
    self_check_args = ()  # a GUI: never started just to answer

    requires = (X64DBG,)

    def prepare(self, target: AnalysisTarget, ctx) -> LaunchSpec | Outcome:
        """`ctx.options["pid"]`: the running game to attach to; none starts the executable."""
        tool = ctx.os.tools.locate(X64DBG)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=X64DBG.hint)
        exe = target.paths[0].resolve()
        debugger = Path(tool.path).resolve()
        if _bits(exe) == 32:  # the pinned snapshot ships both: release/x32/x32dbg.exe
            debugger = debugger.parent.parent / "x32" / debugger.name.replace("x64", "x32")
            if not debugger.is_file():  # an x64dbg of the user's own may come without it
                why = f"{exe.name} is a 32-bit program and this x64dbg has no {debugger}"
                return Outcome(OutcomeKind.UNAVAILABLE, error=why)
        if "third_party" in debugger.parts:  # ViWo's own copy, never the user's install
            quiet_x64dbg(debugger)
        else:
            ctx.log("x64dbg is your own install: its first-run windows are left to you", "info")
        pid = int(ctx.options.get("pid") or 0)
        what = ("-p", str(pid)) if pid else (str(exe),)
        return LaunchSpec((str(debugger), *what), exe.parent)


def quiet_cheatengine(host, home: Path) -> None:
    """Pre-answer Cheat Engine's first-run questions off screen (owner's rule): CEShare's server
    setup (it asks while autorun/ceshare/server.txt is missing), the table Lua question
    (LuaScriptAction 0 = run the table's script: the ViWo table needs it) and the first-time tips.
    A value the user already set is kept."""
    server = home / "autorun" / "ceshare" / "server.txt"
    if server.parent.is_dir() and not server.exists():
        server.write_text("", encoding="utf-8")
    key = r"HKCU\Software\Cheat Engine"
    for name, value in (("LuaScriptAction", "0"), ("First Time User", "0")):
        if host.process.run(["reg", "query", key, "/v", name], timeout=10).returncode:
            host.process.run(
                ["reg", "add", key, "/v", name, "/t", "REG_DWORD", "/d", value, "/f"], timeout=10
            )


class CheatEngineGui(Handoff):
    backend_id, license, isolation = "cheatengine-gui", "Cheat Engine license", "subprocess"
    label, accepts, families = "Continue in Cheat Engine", ("native_binary",), ATTACH
    self_check_args = ()

    requires = (CHEATENGINE,)

    def prepare(self, target: AnalysisTarget, ctx) -> LaunchSpec | Outcome:
        tool = ctx.os.tools.locate(CHEATENGINE)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=CHEATENGINE.hint)
        exe = target.paths[0]
        ctx.staging.mkdir(parents=True, exist_ok=True)
        table = (ctx.staging / f"{exe.stem}.CT").resolve()
        table.write_text(TABLE.format(name=table_name(exe.name)), encoding="utf-8")
        owned = "third_party" in Path(tool.path).resolve().parts  # never the user's own install
        if ctx.os.os_id == "windows" and owned:
            quiet_cheatengine(ctx.os, Path(tool.path).resolve().parent)
        elif not owned:
            ctx.log("Cheat Engine is your own install: its first-run questions are left to you")
        return LaunchSpec((*tool.argv_prefix, str(table)), table.parent)
