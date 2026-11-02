"""Harvest helper, run by a Python that has RenderDoc's `renderdoc` module: the installed
`qrenderdoc --py rd_harvest.py` (RenderDoc's embedded interpreter, headless) or any Python with
the module. Runs as a separate process; not imported by ViWo.

Usage: python rd_harvest.py <capture.rdc> <output folder>
       (or VIWO_RD_CAPTURE / VIWO_RD_OUT in the environment, since qrenderdoc passes no argv)
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
    args = sys.argv[1:3] if len(sys.argv) >= 3 else []
    capture_file = os.environ.get("VIWO_RD_CAPTURE") or args[0]
    out_dir = os.environ.get("VIWO_RD_OUT") or args[1]
    sys.exit(main(capture_file, out_dir))
