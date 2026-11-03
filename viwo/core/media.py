"""Media types by extension: the one table the workspace listing, the preview and the
merger agree on (an extension is image, audio, video, text or other)."""

from __future__ import annotations

IMAGE = frozenset(".png .jpg .jpeg .webp .bmp .gif .svg .ico .tif .tiff .heic .avif".split())
VIDEO = frozenset(".mp4 .webm .mov .m4v .mpeg .mpg .avi .mkv .flv .3gp .ts .m2ts".split())
AUDIO = frozenset(".mp3 .ogg .wav .m4a .aac .opus .flac .wma .aiff .aif .mid .midi".split())
TEXT = frozenset(
    ".txt .json .xml .csv .md .rpy .rpym .ini .log .py .js .css .html .yaml .yml .cfg".split()
)
KINDS = (("image", IMAGE), ("audio", AUDIO), ("video", VIDEO), ("text", TEXT))


def media_type(ext: str) -> str:
    """image | audio | video | text | other, from a lowercased or raw extension with its dot."""
    ext = ext.lower()
    return next((kind for kind, exts in KINDS if ext in exts), "other")
