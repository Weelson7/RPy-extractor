"""Bink 2 video to MP4 through the game's own Bink DLL (ViWo authors no Bink decoder): run as
its own process, so the game's code never runs inside ViWo. Every frame is decoded by the DLL
and piped as 32-bit pixels into the pinned ffmpeg.

Usage: python -I decode_bink.py <bink2w64.dll> <in.bk2> <out.mp4> <ffmpeg argv...>
Prints one JSON line: {"width", "height", "frames", "fps"} or {"error"}. Exit 0 when the MP4
was written, 2 when the DLL refused the file, 3 when ffmpeg failed.
"""

import ctypes
import json
import os
import struct
import subprocess
import sys

SURFACE32 = 3  # BINKSURFACE32: B, G, R, A bytes per pixel


def bind(path: str):
    dll = ctypes.CDLL(path)
    handle = ctypes.c_void_p
    dll.BinkOpen.restype = handle
    dll.BinkOpen.argtypes = [ctypes.c_char_p, ctypes.c_uint32]
    for name in ("BinkDoFrame", "BinkNextFrame", "BinkClose"):
        getattr(dll, name).argtypes = [handle]
    dll.BinkCopyToBuffer.argtypes = [handle, handle] + [ctypes.c_uint32] * 5
    return dll


def encoder(ffmpeg: list, width: int, height: int, rate: str, out: str):
    argv = [*ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra"]
    argv += ["-s", f"{width}x{height}", "-r", rate, "-i", "-"]
    argv += ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", out]
    return subprocess.Popen(argv, stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def main(dll_path: str, src: str, out: str, ffmpeg: list) -> int:
    dll = bind(dll_path)
    name = src.encode("mbcs") if os.name == "nt" else os.fsencode(src)  # the DLL takes ANSI
    bink = dll.BinkOpen(name, 0)
    if not bink:
        print(json.dumps({"error": "the game's Bink DLL could not open the file"}))
        return 2
    width, height, frames, _num, _last, rate, div = struct.unpack("<7I", ctypes.string_at(bink, 28))
    try:
        enc = encoder(ffmpeg, width, height, f"{rate}/{div or 1}", out)
    except OSError as exc:  # no ffmpeg where it was said to be
        dll.BinkClose(bink)
        print(json.dumps({"error": f"ffmpeg did not start: {exc}"}))
        return 3
    frame = ctypes.create_string_buffer(width * height * 4)
    try:
        for _ in range(frames):
            dll.BinkDoFrame(bink)
            dll.BinkCopyToBuffer(bink, frame, width * 4, height, 0, 0, SURFACE32)
            enc.stdin.write(frame.raw)
            dll.BinkNextFrame(bink)
    except BrokenPipeError:
        pass  # ffmpeg stopped: its exit code and message say why
    finally:
        dll.BinkClose(bink)
        enc.stdin.close()
    said = enc.stderr.read().decode("utf-8", "replace")
    if enc.wait():
        print(json.dumps({"error": f"ffmpeg failed: {said[-300:]}"}))
        return 3
    fps = rate / (div or 1)
    print(json.dumps({"width": width, "height": height, "frames": frames, "fps": round(fps, 3)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]))
