"""Total War rigid models (`.rigid_model_v2`), read for decode.rigid_model_v2 (models.py), as
Rome II's own files lay them out (read on its packs; AssetEditor and RPFM name the parts the
same way). Versions 6 (Rome II, Attila, Thrones of Britannia) and 7 (Warhammer, by the same
layout with a longer LOD header) are read; 5 (UTF-16 names), 8 and the rest are refused by name.

  header  "RMV2", version, LODs, skeleton name (128 bytes); LOD 0's header @140: meshes,
          vertex bytes, index bytes, offset of its first mesh, distance (20 bytes; 28 from 7)
  mesh    material type u16, flags u16, mesh size, vertex offset, vertices, index offset,
          indices (offsets from the mesh), bounding box, shader name and parameters (to @80);
          vertex format u16 @80, name @82 (32), texture folder (256), filters (256), pivot 3f
          @628, matrices, attachment points and textures counted @792, their lists @940
          (84 bytes each, then 260 a texture: type u32, path; type 0 is the colour map)
  vertex  static (format 0, 32 bytes): position 4 halves (from the pivot), UV, second UV,
          normal, U and V directions as bytes in B, G, R order, colour;
          weighted (3, 28): position, 2 bone indices, the first one's weight (the second
          weighs the rest), normal, UV, V and U directions (R, G, B);
          cinematic (4, 32): position, 4 bone indices, 4 weights, normal, UV, V and U directions
  skeleton  the pair the header names: `<name>.anim` (version 5: version, ?, rate, name with
          a u16 length, end time, bones: name, parent) and `<name>.bone_inv_trans_mats`
          (version 1, count, per bone a 4x3 matrix for row vectors: three axes, translation)"""

import struct
from array import array

LOD_HEADER = {6: 20, 7: 28}
FORMATS = {  # format -> name, size, UVs, normal, U direction, V direction, order, bones, colour
    0: ("static", 32, (8, 12), 16, 20, 24, (2, 1, 0), (0, 0), 28),
    3: ("weighted", 28, (16,), 12, 24, 20, (0, 1, 2), (8, 2), -1),
    4: ("cinematic", 32, (20,), 16, 28, 24, (0, 1, 2), (8, 4), -1),
}


def _text(raw, at: int, size: int) -> str:
    return bytes(raw[at : at + size]).split(b"\0")[0].decode("latin-1")


def _mesh(raw, at: int) -> dict:
    """A mesh group; one whose material block is not the layout read (texture combos, decals,
    water: shorter blocks or other vertex formats) keeps only its type and format."""
    kind, _, size, first, count, index_at, indices = struct.unpack_from("<HH5I", raw, at)
    fmt = struct.unpack_from("<H", raw, at + 80)[0] if first >= 82 else -1
    out = {"type": kind, "format": fmt if first >= 940 else -1, "size": size, "count": count}
    if out["format"] not in FORMATS:
        return out | {"format": fmt if fmt not in FORMATS else -1}
    out |= {"pivot": struct.unpack_from("<3f", raw, at + 628), "textures": []}
    out |= {"name": _text(raw, at + 82, 32), "shader": _text(raw, at + 48, 12)}
    points, textures = struct.unpack_from("<II", raw, at + 792)
    start = at + 940 + 84 * points
    if start + 260 * textures <= at + first:  # else the counts are not this layout's
        for k in range(start, start + 260 * textures, 260):
            out["textures"].append((struct.unpack_from("<I", raw, k)[0], _text(raw, k + 4, 256)))
    stride = FORMATS[fmt][1]
    out["vertices"] = bytes(raw[at + first : at + first + stride * count])
    out["indices"] = array("H", bytes(raw[at + index_at : at + index_at + 2 * indices]))
    if index_at - first != stride * count or len(out["vertices"]) != stride * count:
        raise ValueError(f"a mesh's vertices do not fit its format {fmt}")
    if len(out["indices"]) != indices or indices % 3:
        raise ValueError("a mesh's triangles run past the file")
    return out


def read(raw: bytes) -> dict:
    """Skeleton name and LOD 0's meshes (the material type and format decide what is read)."""
    magic, version, lods = struct.unpack_from("<4sII", raw, 0)
    if magic != b"RMV2":
        raise ValueError("not a rigid model")
    if version not in LOD_HEADER:
        raise ValueError(f"rigid model version {version}: versions 6 and 7 are read")
    out = {"version": version, "skeleton": _text(raw, 12, 128), "meshes": []}
    if lods < 1:
        return out
    meshes, _, _, at, _ = struct.unpack_from("<4If", raw, 140)
    for _ in range(meshes):
        out["meshes"].append(_mesh(raw, at))
        at += out["meshes"][-1]["size"]
    return out


def column(blob: bytes, stride: int, offset: int, fmt: str) -> list:
    """One attribute of interleaved vertices: its numbers, vertex after vertex."""
    size = struct.calcsize(f"<{fmt}")
    return [v for row in struct.iter_unpack(f"<{offset}x{fmt}{stride - offset - size}x", blob)
            for v in row]  # fmt: skip


def _directions(blob: bytes, stride: int, offset: int, order) -> array:
    raw = column(blob, stride, offset, "3B")
    return array("f", (raw[i + o] / 127.5 - 1.0 for i in range(0, len(raw), 3) for o in order))


def vertices(mesh: dict) -> dict:
    """positions (pivot added), normals, along_u, along_v, uvs, colours, links (joints,
    weights, per vertex) of a mesh of a known format, in the file's axes."""
    _, stride, uvs, normal, u, v, order, (bones, per), colour = FORMATS[mesh["format"]]
    blob = mesh["vertices"]
    positions = array("f", column(blob, stride, 0, "3e"))
    for k in range(3):
        positions[k::3] = array("f", (p + mesh["pivot"][k] for p in positions[k::3]))
    out = {"positions": positions, "normals": _directions(blob, stride, normal, order)}
    out |= {"along_u": _directions(blob, stride, u, order)}
    out |= {"along_v": _directions(blob, stride, v, order)}
    out["uvs"] = [array("f", column(blob, stride, at, "2e")) for at in uvs]
    if colour >= 0:
        out["colours"] = array("f", (c / 255 for c in column(blob, stride, colour, "4B")))
    if per:
        joints = array("H", column(blob, stride, bones, f"{per}B"))
        weights = column(blob, stride, bones + per, f"{per}B")
        if per == 2:  # one weight stored: the second bone weighs the rest
            weights = [w for first in weights[0::2] for w in (first, 255 - first)]
        out["links"] = (joints, array("f", (w / 255 for w in weights)), per)
    return out


def skeleton(anim: bytes, inverse: bytes) -> tuple[list, list, list]:
    """(bone names, parents, inverse bind matrices as 3x4 for column vectors)."""
    version, _, _, size = struct.unpack_from("<IIfH", anim, 0)
    if version != 5:
        raise ValueError(f"skeleton .anim version {version}: version 5 is read")
    at = 14 + size + 4
    (count,), at = struct.unpack_from("<I", anim, at), at + 4
    names, parents = [], []
    for _ in range(count):
        (size,) = struct.unpack_from("<H", anim, at)
        names.append(anim[at + 2 : at + 2 + size].decode("latin-1"))
        parents.append(struct.unpack_from("<i", anim, at + 2 + size)[0])
        at += 6 + size
    held, matrices = struct.unpack_from("<II", inverse, 0)
    if held != 1 or matrices != count or len(inverse) < 8 + 48 * count:
        raise ValueError("the skeleton's .bone_inv_trans_mats does not match its .anim")
    binds = []
    for b in range(count):
        f = struct.unpack_from("<12f", inverse, 8 + 48 * b)
        binds.append([[f[3 * c + r] for c in range(3)] + [f[9 + r]] for r in range(3)])
    return names, [p if 0 <= p < count and p != i else -1 for i, p in enumerate(parents)], binds
