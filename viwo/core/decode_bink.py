"""decode.bink2: Bink 2 video to MP4 through the game's own Bink DLL (ffmpeg has no Bink 2
decoder). A helper process decodes every frame and pipes it into ffmpeg; ViWo authors no
decoder and the game's code never runs inside ViWo."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from viwo.contracts.slots import Decoder
from viwo.contracts.types import Outcome, OutcomeKind

from .merger.ffmpeg import FFMPEG

BINK_HELPER = Path(__file__).resolve().parents[1] / "data" / "bink" / "decode_bink.py"


@lru_cache(maxsize=16)
def bink_dll(game_root: Path) -> Path | None:
    """The game's own Bink 2 DLL (Cyberpunk 2077 and many others ship one), found once."""
    for name in ("bink2w64.dll", "bink2w32.dll"):
        hit = next(iter(sorted(game_root.rglob(name))), None)
        if hit is not None:
            return hit
    return None


class BinkGame(Decoder):
    """decode.bink2: ffmpeg has no Bink 2 decoder, the game has one. A helper process decodes
    every frame with the game's DLL and pipes it into ffmpeg (MP4); ViWo authors no decoder."""

    backend_id, license, isolation = "bink-game", "the game's own Bink DLL", "subprocess"
    requires = (FFMPEG,)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        tool, dll = ctx.os.tools.locate(FFMPEG), bink_dll(ctx.game_root)
        if tool is None or dll is None:
            why = FFMPEG.hint if tool is None else "no Bink 2 DLL (bink2w64.dll) in the game"
            return Outcome(OutcomeKind.UNAVAILABLE, error=why)
        out = dest / f"{path.name}.mp4"
        argv = [sys.executable, "-I", str(BINK_HELPER), str(dll), str(path), str(out)]
        result = ctx.os.process.run([*argv, *tool.argv_prefix], timeout=3600, cancel=ctx.cancel)
        said = (result.stdout or "").strip().splitlines()[-1:] or [result.stderr[-300:]]
        if not result.ok or not out.is_file():
            return Outcome(OutcomeKind.FAILED, error=said[0])
        return Outcome(OutcomeKind.OK, 1, notes=(f"{path.name}: {said[0]}; video only",))
