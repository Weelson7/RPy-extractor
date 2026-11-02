"""Harvest helper, run by the Python that ships RenderDoc's `renderdoc` module (it is built
for one exact Python version, so it runs as a separate process). Not imported by ViWo.

Usage: python rd_harvest.py <capture.rdc> <output folder>
Writes every texture of the capture as tex_<resource id>.png.
"""

import os
import sys

import renderdoc as rd  # type: ignore  # provided by the RenderDoc install


def main(capture: str, out: str) -> int:
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    cap = rd.OpenCaptureFile()
    ok = getattr(rd, "ResultCode", getattr(rd, "ReplayStatus", None)).Succeeded
    if cap.OpenFile(capture, "", None) != ok:
        return 2
    status, controller = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != ok:
        return 3
    os.makedirs(out, exist_ok=True)
    for tex in controller.GetTextures():
        save = rd.TextureSave()
        save.resourceId = tex.resourceId
        save.destType = rd.FileType.PNG
        save.mip = 0
        save.alpha = rd.AlphaMapping.Preserve
        controller.SaveTexture(save, os.path.join(out, f"tex_{int(tex.resourceId)}.png"))
    controller.Shutdown()
    cap.Shutdown()
    rd.ShutdownReplay()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
