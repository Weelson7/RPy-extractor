"""NiSkinPartition (20.2.0.7, user version 12) as nif.xml (niftools) lays it out, read for
decode.nif (nifmodels.py): the vertices of a skinned Skyrim SE BSTriShape, and the bone links of
a skin whose NiSkinData holds no weights. Tests only: no real NIF has been read.

  NiSkinPartition  partitions u32; Skyrim SE (stream 100) only: data size, vertex size, vertex
          descriptor u64, then the shape's vertices (data size / vertex size of them, in
          BSTriShape's layout: nif.vertices); then each partition
  partition  vertices, triangles, bones, strips, weights per vertex (u16 each); its bones (u16
          each, into the skin instance's bone list); a flag and the vertex map (u16 per vertex:
          the shape's vertex it is); a flag and the weights (a float per vertex and slot); the
          strip lengths; a flag and the faces (strips, or triangles of partition vertices); a
          flag and the bone indices (a byte per vertex and slot, into the partition's bones);
          LOD level, global VB flag (bytes); Skyrim SE: vertex descriptor u64 and the triangles
          again, with the shape's vertex indices (what the shape draws)

Each vertex's links are the partition's: its slots' bones mapped through that partition's bone
list to the skin's; a vertex two partitions share takes the first. The links the Skyrim SE vertex
data repeats are not read."""

import struct
from array import array

from . import nif as reader

SKINS = ("NiSkinInstance", "BSDismemberSkinInstance")


def _array(raw, at: int, code: str, count: int) -> tuple[array, int]:
    out = array(code, bytes(raw[at : at + array(code).itemsize * count]))
    if len(out) != count:
        raise ValueError("a NiSkinPartition runs past its block")
    return out, at + out.itemsize * count


def _flagged(raw, at: int, code: str, count: int) -> tuple[array | None, int]:
    """A bool, then (when it is set) `count` values."""
    if at >= len(raw):
        raise ValueError("a NiSkinPartition runs past its block")
    return _array(raw, at + 1, code, count) if raw[at] else (None, at + 1)


def _partition(raw, at: int, sse: bool) -> tuple[dict, int]:
    count, tris, bones, strips, per = struct.unpack_from("<5H", raw, at)
    out = {"count": count, "per": per}
    out["bones"], at = _array(raw, at + 10, "H", bones)
    out["map"], at = _flagged(raw, at, "H", count)
    out["weights"], at = _flagged(raw, at, "f", count * per)
    lengths, at = _array(raw, at, "H", strips)
    _, at = _flagged(raw, at, "H", sum(lengths) if strips else 3 * tris)  # partition's own
    out["indices"], at = _flagged(raw, at, "B", count * per)
    at += 2  # LOD level, global VB
    if sse:
        out["triangles"], at = _array(raw, at + 8, "H", 3 * tris)
    return out, at


def read(nif, ref: int) -> dict:
    """The partitions ("parts") and, in Skyrim SE, the shape's vertices ("vertices")."""
    raw = nif.block(ref, ("NiSkinPartition",))[1]
    (count,), at, out = struct.unpack_from("<I", raw, 0), 4, {"parts": []}
    sse = nif.stream == 100
    if sse:
        size, stride, desc = struct.unpack_from("<IIQ", raw, 4)
        if not stride or size % stride or stride != (desc & 0xF) * 4:
            raise ValueError("a NiSkinPartition's vertex size does not match its layout")
        out["vertices"] = reader.vertices(raw[20 : 20 + size], size // stride, desc, True)
        at = 20 + size
    for _ in range(count):
        part, at = _partition(raw, at, sse)
        out["parts"].append(part)
    return out


def links(parts: list, count: int) -> tuple[array, array, int]:
    """(joints into the skin's bones, weights, slots per vertex) of the shape's `count`
    vertices from its partitions; each vertex must be in one."""
    per = max((p["per"] for p in parts), default=1)
    joints, weights = array("H", [0xFFFF]) * (per * count), array("f", bytes(4 * per * count))
    covered = bytearray(count)
    for p in parts:
        if p["weights"] is None or p["indices"] is None:
            raise ValueError("a skin partition without its weights or bone indices: not read")
        for i, v in enumerate(p["map"] if p["map"] is not None else range(p["count"])):
            if v >= count:
                raise ValueError("a skin partition maps a vertex the shape does not have")
            if covered[v]:
                continue
            covered[v] = 1
            for k in range(p["per"]):
                bone = p["indices"][i * p["per"] + k]
                if bone >= len(p["bones"]):
                    raise ValueError("a skin partition's vertex points past its bones")
                joints[v * per + k] = p["bones"][bone]
                weights[v * per + k] = p["weights"][i * p["per"] + k]
    if not all(covered):
        raise ValueError(f"{count - sum(covered)} vertices are in no skin partition")
    return joints, weights, per


def shape(nif, skin: int) -> dict:
    """A skinned Skyrim SE BSTriShape's vertices, triangles (each partition's, with the shape's
    indices) and links from the NiSkinPartition its skin instance names."""
    ref = struct.unpack_from("<i", nif.block(skin, SKINS)[1], 4)[0]
    held = read(nif, ref)
    out = held["vertices"]
    out["triangles"] = array("H", (i for p in held["parts"] for i in p["triangles"]))
    out["links"] = links(held["parts"], out["count"])
    return out
