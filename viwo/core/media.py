"""Media types by extension: the one table the workspace listing, the preview and the
merger agree on (an extension is image, audio, video, model, text or other)."""

IMAGE = frozenset(".png .jpg .jpeg .webp .bmp .gif .svg .ico .tif .tiff .heic .avif".split())
VIDEO = frozenset(".mp4 .webm .mov .m4v .mpeg .mpg .avi .mkv .flv .3gp .ts .m2ts".split())
AUDIO = frozenset(".mp3 .ogg .wav .m4a .aac .opus .flac .wma .aiff .aif .mid .midi".split())
TEXT = frozenset(
    ".txt .json .xml .csv .md .rpy .rpym .ini .log .py .js .css .html .yaml .yml .cfg".split()
)
MODEL = frozenset(".glb .gltf".split())  # what the 3D preview opens
KINDS = (("image", IMAGE), ("audio", AUDIO), ("video", VIDEO), ("model", MODEL))
KINDS += (("text", TEXT),)


def media_type(ext: str) -> str:
    """image | audio | video | model | text | other, from an extension with its dot (any case)."""
    ext = ext.lower()
    return next((kind for kind, exts in KINDS if ext in exts), "other")
