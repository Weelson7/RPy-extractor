"""Total War rigid models (`.rigid_model_v2`), read for decode.rigid_model_v2 (models.py), as
Rome II's own files lay them out (read on its packs; AssetEditor and RPFM name the parts the
same way). Versions 5 (Rome II's older files: names in UTF-16), 6 (Rome II, Attila, Thrones of
Britannia) and 7 (Warhammer, by version 6's layout with a longer LOD header) are read; 1, 3, 8
and the rest are refused by name.

  header  "RMV2", version, LODs, skeleton name (128 bytes; 256 in UTF-16 at 5); LOD 0's header
          after it: meshes, vertex bytes, index bytes, offset of its first mesh, distance (20
          bytes; 28 from 7)
  mesh    material type u16, flags u16, mesh size, vertex offset, vertices, index offset,
          indices (offsets from the mesh), bounding box 6f, shader name and parameters; then
          the material block, which the material type decides:
  default block  vertex format u16 @80, name @82 (32), texture folder (256), filters (256),
          pivot 3f @628, matrices, attachment points and textures counted @792, their lists
          @940 (84 bytes each, then 260 a texture: type u32, path; type 0 the colour map).
          Version 5 doubles every string (UTF-16): shader @48 (64), format @112, name @114
          (64), pivot @1204, counts @1368, lists @1516, 116 bytes a point, 516 a texture
  decal (67, 87)  the decal's path @80 (@112 in UTF-16 at 5): vertices are its projection box
  banner (29, 30), bow wave (22)  name or nothing; no pivot
  vertex  (LAYOUTS: offsets in a vertex) static (format 0, 32 bytes): position 4 halves (from
          the pivot), UV, second UV, normal, U and V directions as bytes in B, G, R order,
          colour; collision (1, 24): position 3f, normal 3f; weighted (3, 28): position,
          2 bone indices, the first one's weight (the second weighs the rest), normal, UV, V and
          U directions (R, G, B); cinematic (4, 32): position, 4 bone indices, 4 weights,
          normal, UV, V and U directions; water (8, 12): position, UV; banner (28): static
          without its second UV; bow wave (24): position, a second position, UV, a float;
          decal (16): position 4f
  skeleton  the pair the header names: `<name>.anim` (version 5: version, ?, rate, name with
          a u16 length, end time, bones: name, parent) and `<name>.bone_inv_trans_mats`
          (version 1, count, per bone a 4x3 matrix for row vectors: three axes, translation)

Flag placements (26) and lights and effects (45) hold no vertex data; they, and any other
material type or vertex format, are not read and say which they are."""

import struct
from array import array
from typing import NamedTuple

HEADS = {5: (256, 20), 6: (128, 20), 7: (128, 28)}  # version -> skeleton name, LOD header


class Block(NamedTuple):
    """Where a version's default material block keeps its fields (offsets from the mesh)."""

    wide: bool  # strings in UTF-16
    shader: int  # its size @48
    format: int
    name: int
    pivot: int
    counts: int
    lists: int
    point: int  # bytes an attachment point


BLOCKS = {5: Block(True, 64, 112, 114, 1204, 1368, 1516, 116),
          6: Block(False, 12, 80, 82, 628, 792, 940, 84)}  # fmt: skip
BLOCKS[7] = BLOCKS[6]


class Layout(NamedTuple):
    """A vertex layout: offsets in a vertex (-1: none); positions are at 0."""

    name: str
    stride: int
    position: str = "3e"  # halves (from the pivot) or floats
    uvs: tuple = ()
    normal: int = -1  # bytes, or three floats when `floats`
    along: tuple = (-1, -1)  # U and V directions (bytes)
    order: tuple = (0, 1, 2)  # the order their bytes hold R, G, B
    bones: tuple = (0, 0)  # offset, how many
    colour: int = -1
    floats: bool = False
    data: tuple = ()  # (attribute, offset, struct format) kept as stored


BANNER = Layout("banner", 28, uvs=(8,), normal=12, along=(16, 20), order=(2, 1, 0), colour=24)
DECAL = Layout("decal", 16, "3f")
FORMATS = {  # vertex format of a default block -> layout
    0: Layout("static", 32, uvs=(8, 12), normal=16, along=(20, 24), order=(2, 1, 0), colour=28),
    1: Layout("collision", 24, "3f", normal=12, floats=True),
    3: Layout("weighted", 28, uvs=(16,), normal=12, along=(24, 20), bones=(8, 2)),
    4: Layout("cinematic", 32, uvs=(20,), normal=16, along=(28, 24), bones=(8, 4)),
    8: Layout("water", 12, uvs=(8,)),
}
KINDS = {  # material type of another block -> layout (None: no vertex data)
    22: Layout("bow wave", 24, uvs=(16,), data=(("_POSITION_1", 8, "3e"), ("_VALUE_0", 20, "f"))),
    26: None, 29: BANNER, 30: BANNER, 45: None, 67: DECAL, 87: DECAL,
}  # fmt: skip
UNREAD = {26: "flag placement", 45: "light or effect"}


def _text(raw, at: int, size: int, wide: bool = False) -> str:
    held = bytes(raw[at : at + size])
    return held.decode("utf-16-le", "replace").split("\0")[0] if wide else (
        held.split(b"\0")[0].decode("latin-1"))  # fmt: skip


def _block(raw, at: int, first: int, block: Block) -> dict:
    """A default material block: vertex format, name, shader, pivot, textures."""
    fmt = struct.unpack_from("<H", raw, at + block.format)[0] if first > block.format else -1
    if first < block.lists or fmt not in FORMATS:
        return {"why": f"vertex format {fmt}"}
    wide, size = block.wide, 512 if block.wide else 256
    out = {"layout": FORMATS[fmt], "name": _text(raw, at + block.name, 64 if wide else 32, wide)}
    out |= {"shader": _text(raw, at + 48, block.shader, wide), "textures": []}
    out["pivot"] = struct.unpack_from("<3f", raw, at + block.pivot)
    points, textures = struct.unpack_from("<II", raw, at + block.counts)
    start = at + block.lists + block.point * points
    if start + (size + 4) * textures <= at + first:  # else the counts are not this layout's
        for k in range(start, start + (size + 4) * textures, size + 4):
            kind = struct.unpack_from("<I", raw, k)[0]
            out["textures"].append((kind, _text(raw, k + 4, size, wide)))
    return out


def _other(raw, at: int, kind: int, version: int) -> dict:
    """A block of another layout, known by its material type."""
    layout, wide = KINDS[kind], version == 5
    if layout is None:
        return {"why": f"{UNREAD[kind]}: no vertex data"}
    out = {"layout": layout, "pivot": (0.0, 0.0, 0.0), "textures": [], "name": ""}
    out["shader"] = _text(raw, at + 48, 64 if wide else 12, wide)
    if layout is DECAL:
        out["decal"] = _text(raw, at + (112 if wide else 80), 512 if wide else 256, wide)
    elif layout is BANNER:
        out["name"] = _text(raw, at + 80, 32)
    return out


def _mesh(raw, at: int, version: int) -> dict:
    """A mesh group; one of a layout not read keeps its type and why (`layout` None)."""
    kind, _, size, first, count, index_at, indices = struct.unpack_from("<HH5I", raw, at)
    out = {"type": kind, "size": size, "count": count, "layout": None}
    out["bounds"] = struct.unpack_from("<6f", raw, at + 24)
    if kind in KINDS:
        out |= _other(raw, at, kind, version)
    else:
        out |= _block(raw, at, first, BLOCKS[version])
    layout = out["layout"]
    if layout is None:
        out["why"] = f"material type {kind}, {out['why']}"
        return out
    out["vertices"] = bytes(raw[at + first : at + first + layout.stride * count])
    out["indices"] = array("H", bytes(raw[at + index_at : at + index_at + 2 * indices]))
    fits = index_at - first == layout.stride * count == len(out["vertices"])
    if not fits and kind in KINDS:  # the type's number names another layout in this game
        why = f"material type {kind}, its vertices do not fit the {layout.name} layout"
        return out | {"layout": None, "why": why}
    if not fits:
        what = f"material type {kind}, {layout.name}"
        raise ValueError(f"a mesh's vertices do not fit its layout ({what})")
    if len(out["indices"]) != indices or indices % 3:
        raise ValueError("a mesh's triangles run past the file")
    return out


def read(raw: bytes) -> dict:
    """Skeleton name and LOD 0's meshes (the material type and format decide what is read)."""
    magic, version, lods = struct.unpack_from("<4sII", raw, 0)
    if magic != b"RMV2":
        raise ValueError("not a rigid model")
    if version not in HEADS:
        raise ValueError(f"rigid model version {version}: versions 5, 6 and 7 are read")
    name, _ = HEADS[version]
    out = {"version": version, "skeleton": _text(raw, 12, name, version == 5), "meshes": []}
    if lods < 1:
        return out
    meshes, _, _, at, _ = struct.unpack_from("<4If", raw, 12 + name)
    for _ in range(meshes):
        out["meshes"].append(_mesh(raw, at, version))
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
    weights, per vertex), data of a mesh of a known layout, in the file's axes (each only
    when the layout has it)."""
    lay, blob = mesh["layout"], mesh["vertices"]
    stride = lay.stride
    positions = array("f", column(blob, stride, 0, lay.position))
    for k in range(3):
        positions[k::3] = array("f", (p + mesh["pivot"][k] for p in positions[k::3]))
    out = {"positions": positions, "uvs": [array("f", column(blob, stride, at, "2e"))
                                           for at in lay.uvs]}  # fmt: skip
    if lay.normal >= 0:
        out["normals"] = (array("f", column(blob, stride, lay.normal, "3f")) if lay.floats
                          else _directions(blob, stride, lay.normal, lay.order))  # fmt: skip
    if lay.along[0] >= 0:
        out["along_u"] = _directions(blob, stride, lay.along[0], lay.order)
        out["along_v"] = _directions(blob, stride, lay.along[1], lay.order)
    if lay.colour >= 0:
        out["colours"] = array("f", (c / 255 for c in column(blob, stride, lay.colour, "4B")))
    out["data"] = {key: array("f", column(blob, stride, at, fmt)) for key, at, fmt in lay.data}
    bones, per = lay.bones
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
