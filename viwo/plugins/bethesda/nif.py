"""NIF (Gamebryo 20.2.0.7, user version 12) as Skyrim (Bethesda stream 83), Skyrim Special
Edition (100) and Fallout 4 (130) ship it, read for decode.nif (nifmodels.py) as nif.xml
(niftools) lays it out; every other version is refused by name. The header lists each block's
type and size, so a block is read inside its own bytes and the others are passed by:

  header  "Gamebryo File Format, Version 20.2.0.7\\n", version, endian, user version, blocks,
          stream (83/100/130), author, process and export strings (+ max filepath at 130),
          block types (sized strings), each block's type index and size, the string table
  NiAVObject  name (string index), extra data refs, controller, flags u32, translation 3f,
          rotation 9f (rows, applied to column vectors), scale, collision ref
  nodes   NiAVObject, children refs                    (NODES)
  NiTriShape, BSLODTriShape  NiAVObject, data, skin, material names, shader, alpha refs
  NiTriShapeData  vertex count, positions, flags (bit 0: a UV set, 0x1000: tangents), normals,
          tangents and bitangents, bounds, colours, the UV set, triangle count, triangles
  BSTriShape, BSMeshLODTriShape, BSSubIndexTriShape  NiAVObject, bounds, skin, shader, alpha,
          vertex descriptor u64 (size and offsets in dwords; attribute flags from bit 44),
          triangle count (u32 from 130), vertex count, data size, the vertices, triangles
  NiSkinInstance, BSDismemberSkinInstance: data, partition, root, bones; NiSkinData: root
          parent to skin, per bone skin to bone and (when it has them) its vertex weights;
          BSSkin::Instance: root, data, bones; BSSkin::BoneData: skin to bone per bone
  BSLightingShaderProperty: shader type, NiObjectNET, flags, UV offset and scale, texture set
          (BSShaderTextureSet: sized strings, the first the colour map); BSEffectShaderProperty:
          NiObjectNET, flags, UV offset and scale, its source texture (a sized string)"""

import struct
from array import array

STREAMS = {83: "Skyrim", 100: "Skyrim SE", 130: "Fallout 4"}
NODES = frozenset(
    "NiNode BSFadeNode BSLeafAnimNode BSTreeNode BSMultiBoundNode BSOrderedNode BSValueNode "
    "NiBillboardNode NiSwitchNode BSRangeNode BSDebrisNode BSBlastNode BSDamageStage "
    "NiLODNode".split()
)
TRI = frozenset(("NiTriShape", "BSLODTriShape"))
BSTRI = frozenset(("BSTriShape", "BSMeshLODTriShape", "BSSubIndexTriShape"))
UNREAD = ("NiTriStrips", "BSDynamicTriShape", "BSSegmentedTriShape", "NiTriShapeDynamic")
FULL, SKINNED = 0x400, 0x40


def _sized(raw, at: int) -> tuple[str, int]:
    (n,) = struct.unpack_from("<I", raw, at)
    if n > 4096:
        raise ValueError("a string runs past its block")
    return bytes(raw[at + 4 : at + 4 + n]).decode("cp1252", "replace"), at + 4 + n


class Nif:
    """The header read; `block(i)` gives (type, bytes) of block i."""

    def __init__(self, raw: bytes) -> None:
        end = raw.find(b"\n", 0, 80)
        line = raw[:end].decode("latin-1", "replace")
        if end < 0 or not line.startswith(("Gamebryo File Format", "NetImmerse File Format")):
            raise ValueError("not a NIF")
        version, _, user, count, self.stream = struct.unpack_from("<IBIII", raw, end + 1)
        if version != 0x14020007 or user != 12 or self.stream not in STREAMS:
            what = ".".join(str(version >> s & 0xFF) for s in (24, 16, 8, 0))
            what += f", user version {user}"
            what += f", stream {self.stream}" if version == 0x14020007 else ""
            raise ValueError(f"NIF {what}: 20.2.0.7, 12, stream 83/100/130 are read")
        at = end + 18
        for _ in range(4 if self.stream >= 103 else 3):
            at += 1 + raw[at]  # author, process script, export script (, max filepath)
        (kinds,), at = struct.unpack_from("<H", raw, at), at + 2
        names = []
        for _ in range(kinds):
            name, at = _sized(raw, at)
            names.append(name)
        index = array("H", raw[at : at + 2 * count])
        sizes = array("I", raw[at + 2 * count : at + 6 * count])
        at += 6 * count
        (strings, _), at = struct.unpack_from("<II", raw, at), at + 8
        self.strings = []
        for _ in range(strings):
            text, at = _sized(raw, at)
            self.strings.append(text)
        (groups,) = struct.unpack_from("<I", raw, at)
        at += 4 + 4 * groups
        self.kinds, self.spans, self.raw = [names[i & 0x7FFF] for i in index], [], memoryview(raw)
        for size in sizes:
            self.spans.append((at, at + size))
            at += size
        if len(index) != count or at > len(raw):
            raise ValueError("the NIF's blocks run past its end")

    def block(self, ref: int, kinds=None) -> tuple[str, memoryview]:
        if not 0 <= ref < len(self.kinds) or (kinds and self.kinds[ref] not in kinds):
            raise ValueError(f"a reference points at no block of the kind it needs ({ref})")
        start, end = self.spans[ref]
        return self.kinds[ref], self.raw[start:end]

    def text(self, raw, at: int) -> tuple[str, int]:
        (i,) = struct.unpack_from("<i", raw, at)
        return (self.strings[i] if 0 <= i < len(self.strings) else ""), at + 4


def floats(raw, at: int, count: int) -> array:
    out = array("f", bytes(raw[at : at + 4 * count]))
    if len(out) != count:
        raise ValueError("a block's data runs past its end")
    return out


def transform(raw, at: int) -> list[list[float]]:
    """Rotation 9f, translation 3f, scale f (NiTransform) as a 3x4 matrix."""
    r, t, s = floats(raw, at, 9), floats(raw, at + 36, 3), floats(raw, at + 48, 1)[0]
    return [[r[3 * row + c] * s for c in range(3)] + [t[row]] for row in range(3)]


def av_object(nif: Nif, raw) -> tuple[str, list, int]:
    """(name, local 3x4 matrix, offset past NiAVObject)."""
    name, at = nif.text(raw, 0)
    (extra,) = struct.unpack_from("<I", raw, at)
    at += 4 + 4 * extra + 8  # extra data refs, controller, flags
    r, t, s = floats(raw, at + 12, 9), floats(raw, at, 3), floats(raw, at + 48, 1)[0]
    return name, [[r[3 * i + c] * s for c in range(3)] + [t[i]] for i in range(3)], at + 56


def children(raw, at: int) -> list[int]:
    (n,) = struct.unpack_from("<I", raw, at)
    return list(struct.unpack_from(f"<{n}i", raw, at + 4))


def tri_shape(nif: Nif, raw, at: int) -> dict:
    """An NiTriShape: its NiTriShapeData read, its skin and shader refs."""
    data, skin, materials = struct.unpack_from("<iiI", raw, at)
    at += 12 + 8 * materials + 5  # material names and extra data, active one, needs update
    (shader,) = struct.unpack_from("<i", raw, at)
    out = tri_data(nif.block(data, ("NiTriShapeData",))[1])
    return out | {"skin": skin, "shader": shader}


def tri_data(raw) -> dict:
    n, has = struct.unpack_from("<H2xB", raw, 4)
    out, at = {"positions": floats(raw, 9, 3 * n) if has else None}, 9 + 12 * n * bool(has)
    flags, has = struct.unpack_from("<H4xB", raw, at)
    at += 7
    if has:
        out["normals"], at = floats(raw, at, 3 * n), at + 12 * n
        if flags & 0x1000:
            out["tangents"], out["bitangents"] = (
                floats(raw, at, 3 * n),
                floats(raw, at + 12 * n, 3 * n),
            )
            at += 24 * n
    at += 16  # bounding sphere
    if raw[at]:
        out["colours"], at = floats(raw, at + 1, 4 * n), at + 16 * n
    at += 1
    out["uvs"] = [floats(raw, at, 2 * n)] if flags & 1 else []
    at += 8 * n * (flags & 1) + 6  # consistency flags, additional data
    tris, has = struct.unpack_from("<H4xB", raw, at)
    out["triangles"] = array("H", bytes(raw[at + 7 : at + 7 + 6 * tris])) if has else array("H")
    if len(out["triangles"]) != 3 * tris * bool(has) or out["positions"] is None:
        raise ValueError("an NiTriShapeData is cut short or holds no vertices")
    return out | {"count": n}


def column(blob, stride: int, offset: int, fmt: str) -> list:
    """One attribute of interleaved vertices: its numbers, vertex after vertex."""
    size = struct.calcsize(f"<{fmt}")
    if offset + size > stride:
        raise ValueError("a vertex attribute lies past its vertex")
    return [v for row in struct.iter_unpack(f"<{offset}x{fmt}{stride - offset - size}x", blob)
            for v in row]  # fmt: skip


def _unit(values) -> array:
    return array("f", (v / 127.5 - 1.0 for v in values))


def bs_tri_shape(nif: Nif, raw, at: int) -> dict:
    """A BSTriShape (and its kinds that add their fields after it): its own vertex data."""
    skin, shader, _, desc = struct.unpack_from("<3iQ", raw, at + 16)
    wide = nif.stream >= 130
    tris, n, size = struct.unpack_from("<IHI" if wide else "<HHI", raw, at + 36)
    at += 46 if wide else 44
    flags, stride = desc >> 44 & 0xFFF, (desc & 0xF) * 4
    if not size:
        why = "keeps its vertices in its NiSkinPartition" if skin >= 0 else "holds no vertices"
        raise ValueError(f"a BSTriShape {why}: not read")
    blob = raw[at : at + stride * n]
    out = {"count": n, "skin": skin, "shader": shader, "uvs": []}
    out["triangles"] = array("H", bytes(raw[at + stride * n : at + size]))
    if size != stride * n + 6 * tris or len(out["triangles"]) != 3 * tris or not flags & 1:
        raise ValueError("a BSTriShape's data does not match its vertex layout")
    full = bool(flags & FULL) or nif.stream == 100  # Skyrim SE stores full floats
    out["positions"] = array("f", column(blob, stride, 0, "3f" if full else "3e"))
    uv, uv2, normal, tangent, colour, weight = (
        (desc >> 4 * (b + 1) & 0xF) * 4 if flags >> b & 1 else -1 for b in range(1, 7)
    )  # attribute bit b has its offset in the descriptor's nibble b + 1
    out["uvs"] = [array("f", column(blob, stride, u, "2e")) for u in (uv, uv2) if u >= 0]
    if normal >= 0:
        out["normals"] = _unit(column(blob, stride, normal, "3B"))
    if normal >= 0 and tangent >= 0:
        out["tangents"] = _unit(column(blob, stride, tangent, "3B"))
        x = column(blob, stride, 12 if full else 6, "f" if full else "e")
        y, z = (_unit(column(blob, stride, o + 3, "B")) for o in (normal, tangent))
        out["bitangents"] = array("f", (v for row in zip(x, y, z) for v in row))
    if colour >= 0:
        out["colours"] = array("f", (v / 255 for v in column(blob, stride, colour, "4B")))
    if weight >= 0:
        joints = array("H", column(blob, stride, weight + 8, "4B"))
        out["links"] = (joints, array("f", column(blob, stride, weight, "4e")), 4)
    return out


def _weights(raw, at: int, bones: int, count: int) -> tuple:
    """NiSkinData's per-bone skin-to-bone transforms and its vertex weights, as links."""
    binds, slots = [], [[] for _ in range(count)]
    for bone in range(bones):
        binds.append(transform(raw, at))
        (n,) = struct.unpack_from("<H", raw, at + 68)
        for vertex, weight in struct.iter_unpack("<Hf", bytes(raw[at + 70 : at + 70 + 6 * n])):
            if vertex >= count:
                raise ValueError("a bone weighs a vertex the shape does not have")
            slots[vertex].append((bone, weight))
        at += 70 + 6 * n
    per = max(1, max(map(len, slots), default=1))
    joints = array("H", (j for s in slots for j, _ in s + [(0xFFFF, 0.0)] * (per - len(s))))
    weights = array("f", (w for s in slots for _, w in s + [(0xFFFF, 0.0)] * (per - len(s))))
    return binds, (joints, weights, per)


def skin(nif: Nif, ref: int, count: int) -> dict | None:
    """bones (node refs), binds (skin to bone), root, to_skin (root parent to skin, or None),
    links (joints, weights, per vertex) when the skin data holds them."""
    if ref < 0:
        return None
    kinds = ("NiSkinInstance", "BSDismemberSkinInstance", "BSSkin::Instance")
    kind, raw = nif.block(ref, kinds)
    if kind == "BSSkin::Instance":  # Fallout 4: the weights are in the vertices
        root, data, n = struct.unpack_from("<iiI", raw, 0)
        bones = list(struct.unpack_from(f"<{n}i", raw, 12))
        held = nif.block(data, ("BSSkin::BoneData",))[1]
        (m,) = struct.unpack_from("<I", held, 0)
        binds = [transform(held, 20 + 68 * k) for k in range(m)]
        return {"bones": bones, "binds": binds, "root": root, "to_skin": None, "links": None}
    data, _, root, n = struct.unpack_from("<iiiI", raw, 0)
    bones = list(struct.unpack_from(f"<{n}i", raw, 16))
    held = nif.block(data, ("NiSkinData",))[1]
    m, has = struct.unpack_from("<IB", held, 52)
    binds, links = _weights(held, 57, m, count) if has else (None, None)
    if not has:  # skin to bone without weights: the transforms alone
        binds, at = [], 57
        for _ in range(m):
            binds.append(transform(held, at))
            at += 70
    return {"bones": bones, "binds": binds, "root": root, "to_skin": transform(held, 0),
            "links": links}  # fmt: skip


def material(nif: Nif, ref: int) -> tuple[str, str]:
    """(name, colour texture path) of a shape's shader property; ("", "") without one."""
    kind, raw = nif.block(ref) if ref >= 0 else ("", b"")
    if kind not in ("BSLightingShaderProperty", "BSEffectShaderProperty"):
        return "", ""
    lighting = kind == "BSLightingShaderProperty"  # its shader type comes before the name
    name, at = nif.text(raw, 4 if lighting else 0)
    (extra,) = struct.unpack_from("<I", raw, at)
    at += 4 + 4 * extra + 4 + 8 + 16  # extra data, controller, flags, UV offset and scale
    if not lighting:
        return name, _sized(raw, at)[0]
    (textures,) = struct.unpack_from("<i", raw, at)
    if textures < 0:
        return name, ""
    held = nif.block(textures, ("BSShaderTextureSet",))[1]
    return name, (_sized(held, 4)[0] if struct.unpack_from("<I", held, 0)[0] else "")
