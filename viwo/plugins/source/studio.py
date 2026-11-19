"""Source engine studio models, read for decode.mdl (models.py): the `.mdl` header, bones,
materials and meshes, the `.vvd` vertices and the `.vtx` triangles of LOD 0, for MDL versions 44
to 49 (Half-Life 2 to CS:GO and Portal 2), which share these parts of studiohdr_t. Read as the
Source SDK lays them out (public/studio.h, public/optimize.h; Crowbar and SourceIO read them the
same way); every offset of a part is relative to that part unless said:

  .mdl  "IDST", version, checksum (@8); bones: count, offset @156; textures @204; cdmaterials
        @212 (offsets from the file start); skin refs, families, offset @220; body parts @232.
        bone (216 bytes): name, parent, pos 3f @32, quat xyzw @44, poseToBone 3x4 @96;
        texture (64): name; body part (16): name, models, base, model offset;
        model (148): meshes, mesh offset, vertices, vertex index (bytes into the .vvd's) @72;
        mesh (116): material, model offset, vertices, vertex offset (from the model's first)
  .vvd  "IDSV", version, checksum (@8), LODs, vertices per LOD [8], fixups, fixup offset,
        vertex offset (@48); a vertex (48): weights 3f, bones 3B, bone count B, position 3f,
        normal 3f, uv 2f; fixups (lod, first, count) rebuild LOD 0's list when there are any
  .vtx  version 7, checksum (@16), body parts (@28) -> models -> LODs -> meshes (9 bytes)
        -> strip groups (25 bytes; 33 where CS:GO adds its topology fields) -> their vertices
        (9 bytes, the mesh vertex id @4), 16-bit indices and strips (27 or 35 bytes: indices,
        first index, .., flags: 1 triangle list, 2 triangle strip)"""

import struct
from array import array

BONE, TEXTURE, PART, MESH, VERTEX = 216, 64, 16, 116, 48
WIDE = (8, 8)  # what CS:GO adds to a strip group and to a strip


def _at(raw: bytes, fmt: str, offset: int) -> tuple:
    if offset < 0:
        raise ValueError("an offset points before the file")
    return struct.unpack_from(fmt, raw, offset)


def _text(raw: bytes, offset: int) -> str:
    return raw[offset : raw.index(b"\0", offset)].decode("utf-8", "replace")


def _bones(raw: bytes, count: int, start: int) -> list:
    """[(name, parent, position, rotation xyzw, poseToBone as three rows of four)]."""
    out = []
    for i in range(count):
        at = start + BONE * i
        name, parent = _text(raw, at + _at(raw, "<i", at)[0]), _at(raw, "<i", at + 4)[0]
        pose = _at(raw, "<12f", at + 96)
        rows = [list(pose[0:4]), list(pose[4:8]), list(pose[8:12])]
        move, turn = _at(raw, "<3f", at + 32), _at(raw, "<4f", at + 44)
        out.append((name, parent if 0 <= parent < i else -1, move, turn, rows))
    return out


def read_mdl(raw: bytes) -> dict:
    """Checksum, bones, texture names, cdmaterials folders, skin family 0, and per body part its
    default model: (first vertex, vertices, [(material, vertices, vertex offset)]) or None."""
    ident, version, checksum = _at(raw, "<4sii", 0)
    if ident != b"IDST":
        raise ValueError("not a Source studio model")
    if not 44 <= version <= 49:
        raise ValueError(f"studio model version {version}: versions 44 to 49 are read")
    textures, tex_at, dirs, dir_at = _at(raw, "<4i", 204)
    refs, families, skin_at, parts, part_at = _at(raw, "<5i", 220)
    out = {"checksum": checksum, "bones": _bones(raw, *_at(raw, "<ii", 156)), "parts": []}
    out["textures"] = [_text(raw, tex_at + TEXTURE * i + _at(raw, "<i", tex_at + TEXTURE * i)[0])
                       for i in range(textures)]  # fmt: skip
    out["dirs"] = [_text(raw, _at(raw, "<i", dir_at + 4 * i)[0]) for i in range(dirs)]
    out["skins"] = list(_at(raw, f"<{refs}h", skin_at)) if families > 0 and refs > 0 else []
    for p in range(parts):
        models, _, model_at = _at(raw, "<iii", part_at + PART * p + 4)
        if models < 1:
            out["parts"].append(None)
            continue
        at = part_at + PART * p + model_at
        meshes, mesh_at, vertices, first = _at(raw, "<4i", at + 72)
        rows = [_at(raw, "<i4xii", at + mesh_at + MESH * k) for k in range(meshes)]
        out["parts"].append((first // VERTEX, vertices, rows, models))
    return out


def read_vvd(raw: bytes, checksum: int) -> bytes:
    """LOD 0's vertices, 48 bytes each, fixups applied."""
    ident, _, check, _ = _at(raw, "<4siii", 0)
    if ident != b"IDSV" or check != checksum:
        raise ValueError("its .vvd is not this model's (another checksum)")
    count, (fixups, fixup_at, data) = _at(raw, "<i", 16)[0], _at(raw, "<3i", 48)
    if fixups:
        rows = [_at(raw, "<3i", fixup_at + 12 * f) for f in range(fixups)]
        out = b"".join(raw[data + VERTEX * a : data + VERTEX * (a + n)] for lod, a, n in rows)
    else:
        out = raw[data : data + VERTEX * count]
    if len(out) != VERTEX * count:
        raise ValueError(f"the .vvd holds {len(out) // VERTEX} of {count} vertices")
    return out


def _strip(indices, flags: int) -> list[int]:
    """A strip's indices as a triangle list in the file's winding (a strip alternates)."""
    if not flags & 2:
        return list(indices)
    out = []
    for k in range(len(indices) - 2):
        a, b, c = indices[k : k + 3]
        if a != b and b != c and a != c:
            out += (a, b, c) if k % 2 == 0 else (b, a, c)
    return out


def _groups(raw: bytes, start: int, count: int, wide: bool) -> list[int]:
    """The triangles of one mesh's strip groups, as mesh vertex ids in the file's order."""
    out, group = [], 25 + WIDE[0] * wide
    for g in range(count):
        at = start + group * g
        verts, vert_at, total, index_at, strips, strip_at = _at(raw, "<6i", at)
        span = raw[at + vert_at : at + vert_at + 9 * verts]
        ids = [v[0] for v in struct.iter_unpack("<4xH3x", span)] if len(span) == 9 * verts else []
        indices = array("H", raw[at + index_at : at + index_at + 2 * total])
        if not verts or not total or len(ids) != verts or len(indices) != total:
            raise ValueError("a strip group is empty or runs past the .vtx")  # or misread
        step = 27 + WIDE[1] * wide
        rows = [_at(raw, "<2i10xB", at + strip_at + step * s) for s in range(strips)]
        for n, first, flags in rows or [(total, 0, 1)]:
            if not (0 < n and 0 <= first and first + n <= total):
                raise ValueError("a strip is empty or runs past its group")
            out += [ids[i] for i in _strip(indices[first : first + n], flags)]
    return out


def read_vtx(raw: bytes, checksum: int, parts: list) -> list:
    """Per body part, LOD 0 of its default model: per mesh, its triangles (mesh vertex ids).
    The strip group size is the one under which every mesh reads whole."""
    (version,), (check,) = _at(raw, "<i", 0), _at(raw, "<i", 16)
    count, part_at = _at(raw, "<ii", 28)
    if version != 7 or check != checksum:
        raise ValueError("its .vtx is not this model's (another checksum or version)")
    for wide in (False, True):
        try:
            return [_part(raw, part_at + 8 * p, part, wide) for p, part in enumerate(parts[:count])]
        except (ValueError, IndexError, struct.error) as exc:
            if wide:
                raise ValueError(f"the .vtx does not read: {exc}") from None
    return []


def _part(raw: bytes, at: int, part, wide: bool) -> list:
    if part is None:
        return []
    models, model_at = _at(raw, "<ii", at)
    lods, lod_at = _at(raw, "<ii", at + model_at) if models > 0 else (0, 0)
    if lods < 1:
        return []
    lod = at + model_at + lod_at
    meshes, mesh_at = _at(raw, "<ii", lod)
    out = []
    for k, (_, vertices, _) in enumerate(part[2][:meshes]):
        mesh = lod + mesh_at + 9 * k
        tris = _groups(raw, mesh + _at(raw, "<i", mesh + 4)[0], _at(raw, "<i", mesh)[0], wide)
        if tris and max(tris) >= vertices:
            raise ValueError(f"a triangle points at vertex {max(tris)} of a mesh of {vertices}")
        out.append(tris)
    return out
