"""Media types by extension: the one table the workspace listing, the preview and the
merger agree on (an extension is image, audio, video, model, text or other)."""

from pathlib import Path

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


ONLINE = {  # glTF packings the 3D viewer (model-viewer) decodes with a script it fetches online
    b"KHR_draco_mesh_compression": "Draco",
    b"KHR_texture_basisu": "Basis (KTX2)",
    b"EXT_meshopt_compression": "meshopt",
}


def _json_blocks(fh):
    """A glTF file's JSON, 1 MB at a time: a .glb's first chunk, or a .gltf's whole text."""
    head = fh.read(20)
    left = int.from_bytes(head[12:16], "little") if head[:4] == b"glTF" else -1
    if head[:4] == b"glTF" and head[16:20] != b"JSON":
        return
    if left < 0:
        fh.seek(0)
    while left and (block := fh.read(1 << 20 if left < 0 else min(1 << 20, left))):
        left = left - len(block) if left > 0 else left
        yield block


def online_decoders(path: Path) -> list[str]:
    """The packings of a .glb/.gltf that make the viewer fetch a decoder from the internet (what
    its JSON names; base64 buffers cannot hold an `_`, so they never match). [] when the file
    names none or cannot be read."""
    found, tail = set(), b""
    try:
        with open(path, "rb") as fh:
            for block in _json_blocks(fh):
                text, tail = tail + block, (tail + block)[-32:]  # a name across two blocks
                found |= {name for key, name in ONLINE.items() if key in text}
    except OSError:
        return []
    return sorted(found)
