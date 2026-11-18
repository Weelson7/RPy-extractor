"""Unity meshes as glTF binaries (doc 16.0c): every Mesh also comes out as `<name>.glb` beside
UnityPy's `.obj`, through the shared writer (viwo/contracts/gltf.py). UnityPy decodes the vertex
data (its MeshHandler: vertex streams, compressed meshes, `.resS` streams); everything it gives
is kept: positions, normals, tangents, every UV set, the vertex colours as data (`_COLOR_0`, so
no viewer takes them for a tint), each sub-mesh as a primitive with 16- or 32-bit indices, and
for a skinned mesh its bind poses and bone weights, with the bone names and hierarchy of the
SkinnedMeshRenderer that draws it (else the bones are named by their hash). Unity is
left-handed, glTF right-handed: X is mirrored on every position, normal, tangent and matrix,
each triangle is wound the other way so its front stays its front, a tangent's handedness turns
with the mirror, and V turns (glTF's images start at the top). The main texture (`_MainTex`) of
the renderer's material is embedded as PNG when it resolves; no shader is translated."""

import io
from array import array

from viwo.contracts import gltf
from viwo.contracts import workspace as ws
from viwo.contracts.gltf import FLOAT, UINT, USHORT

DRAWERS = ("SkinnedMeshRenderer", "MeshFilter", "MeshRenderer")
KINDS = {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4"}
CACHE = 64  # main textures kept as PNG across the meshes of one export


def _key(reader) -> tuple:
    return str(getattr(reader.assets_file, "name", "")), reader.path_id


def renderers(env) -> dict:
    """mesh -> (its bone transforms, its materials), from the renderers of a loaded group."""
    found, drawn = {}, {}
    for obj in getattr(env, "objects", ()):
        if obj.type.name not in DRAWERS:
            continue
        try:  # one that does not resolve leaves its mesh plainer: counted in `summary`
            data = obj.parse_as_object()
            owner = _key(data.m_GameObject.deref())
            if obj.type.name == "MeshRenderer":
                drawn[owner] = list(data.m_Materials or [])
            elif data.m_Mesh:
                bones = list(getattr(data, "m_Bones", None) or [])
                mats = list(getattr(data, "m_Materials", None) or [])
                found[_key(data.m_Mesh.deref())] = (owner, bones, mats)
        except Exception:  # noqa: BLE001
            continue
    return {mesh: (b, m or drawn.get(o, [])) for mesh, (o, b, m) in found.items()}


def flat(rows, width: int, count: int) -> array:
    """The first `width` numbers of each row, NaN as 0 (a viewer refuses NaN bounds)."""
    out = array("f", (v if v == v else 0.0 for row in rows for v in row[:width]))
    if len(out) != width * count:
        raise ValueError(f"a vertex channel holds {len(out) // width} of {count} vertices")
    return out


def _turn(values: array, width: int, start: int = 0) -> array:
    values[start::width] = array("f", (-v for v in values[start::width]))
    return values


def _attributes(glb, h, count: int) -> dict:
    out = {"POSITION": glb.accessor(_turn(flat(h.m_Vertices, 3, count), 3), "VEC3", FLOAT)}
    if h.m_Normals:
        out["NORMAL"] = glb.accessor(_turn(flat(h.m_Normals, 3, count), 3), "VEC3", FLOAT)
    if h.m_Tangents:
        tangents = _turn(_turn(flat(h.m_Tangents, 4, count), 4), 4, 3)  # x and handedness
        out["TANGENT"] = glb.accessor(tangents, "VEC4", FLOAT)
    if h.m_Colors:
        scale = 255.0 if isinstance(h.m_Colors[0][0], int) else 1.0  # UNorm8 comes as bytes
        colours = array("f", (v / scale for v in flat(h.m_Colors, 4, count)))
        out["_COLOR_0"] = glb.accessor(colours, "VEC4", FLOAT)
    for n in range(8):
        rows = getattr(h, f"m_UV{n}", None)
        if not rows:
            continue
        width = len(rows[0])
        if width >= 2:
            uv = flat(rows, 2, count)
            uv[1::2] = array("f", (1.0 - v for v in uv[1::2]))
            out[f"TEXCOORD_{n}"] = glb.accessor(uv, "VEC2", FLOAT)
        if width != 2:  # a set of 1, 3 or 4 numbers is also kept whole, as Unity holds it
            out[f"_UV{n}"] = glb.accessor(flat(rows, width, count), KINDS[width], FLOAT)
    return out


def mirrored(m) -> list[list[float]]:
    """A Unity Matrix4x4f (`eRC` is row R, column C: the translation is e03, e13, e23, as
    read on real bind poses) as a right-handed 3x4: X mirrored on both sides."""
    sign = (-1.0, 1.0, 1.0, 1.0)
    return [[float(getattr(m, f"e{r}{c}")) * sign[r] * sign[c] for c in range(4)] for r in range(3)]


def _bones(bones: list, hashes: list) -> tuple[list[str], list[int]]:
    """Bone names and parents from the renderer's transforms, else names by hash, no parents."""
    keys, names, fathers = [], [], []
    for i, ptr in enumerate(bones):
        try:
            reader = ptr.deref()
            bone = reader.parse_as_object()
            father = _key(bone.m_Father.deref()) if bone.m_Father else None
            keys.append(_key(reader))
            names.append(str(bone.m_GameObject.deref_parse_as_object().m_Name))
        except Exception:  # noqa: BLE001  (a bone in a file not loaded: named by its place)
            keys.append(None)
            father = None
            names.append(f"bone_{i}")
        fathers.append(father)
    if not bones:
        return [f"bone_{h & 0xFFFFFFFF:08X}" for h in hashes], [-1] * len(hashes)
    at = {k: i for i, k in enumerate(keys) if k is not None}
    return names, [at.get(f, -1) if f else -1 for f in fathers]


def skeleton(glb, binds: list[list[float]], bones: list, hashes: list) -> list[int]:
    """One joint node per bind pose, placed where it was bound (the mesh shows its rest pose),
    under its parent bone; the skin; the root joints."""
    named = len(bones) == len(binds)
    names, parents = _bones(bones if named else [], hashes if len(hashes) == len(binds) else [])
    names = names or [f"bone_{i}" for i in range(len(binds))]
    parents = parents or [-1] * len(binds)
    nodes = []
    for i, bind in enumerate(binds):
        place = gltf.inverse(bind)
        local = gltf.times(binds[parents[i]], place) if parents[i] >= 0 else place
        nodes.append({"name": names[i], "matrix": gltf.columns(local)})
    gltf.skin(glb, nodes, parents, array("f", (v for b in binds for v in gltf.columns(b))))
    return [i for i, parent in enumerate(parents) if parent < 0]


def _png(reader, cache: dict) -> tuple[str, bytes]:
    key = _key(reader)
    if key not in cache:
        texture, png = reader.parse_as_object(), io.BytesIO()
        texture.image.save(png, format="PNG")
        if len(cache) >= CACHE:
            cache.clear()
        cache[key] = (f"{texture.m_Name or key[1]}.png", png.getvalue())
    return cache[key]


def _texture(glb, ptr, made: dict, cache: dict) -> int | None:
    """The glTF texture of a material's `_MainTex` (PNG), None when it does not resolve: no
    main texture, one in a file not loaded, or one PIL cannot write (the mesh stays plain)."""
    try:
        sheet = ptr.deref_parse_as_object().m_SavedProperties.m_TexEnvs
        tex = next(e.m_Texture for k, e in sheet if getattr(k, "name", k) == "_MainTex")
        reader = tex.deref()
        if _key(reader) not in made:
            name, png = _png(reader, cache)
            made[_key(reader)] = gltf.texture(glb, png, name)
    except Exception:  # noqa: BLE001  (counted by the caller as untextured)
        return None
    return made[_key(reader)]


def _primitive(glb, triangles, base: int, count: int) -> dict | None:
    """One sub-mesh's triangles, each wound the other way (the mirror would turn its front)."""
    flat_ = array("I", (base + i for a, b, c in triangles for i in (a, c, b)))
    if not flat_:
        return None
    if max(flat_) >= count:
        raise ValueError(f"a sub-mesh points at vertex {max(flat_)} of {count}")
    small = max(flat_) < 0xFFFF  # 0xFFFF is a restart value glTF forbids in 16-bit indices
    values, kind = (array("H", flat_), USHORT) if small else (flat_, UINT)
    return {"indices": glb.accessor(values, "SCALAR", kind, gltf.INDICES)}


def _weights(glb, h, attributes: dict, count: int, bones: int) -> None:
    """Every vertex's bone indices and weights (a mesh with one bone a vertex has no weights:
    the one bone weighs 1)."""
    per = len(h.m_BoneIndices[0])
    joints = array("H", (int(j) for row in h.m_BoneIndices for j in row[:per]))
    ones = array("f", ([1.0] + [0.0] * (per - 1)) * count)
    weights = flat(h.m_BoneWeights, per, count) if h.m_BoneWeights else ones
    if len(joints) != per * count or max(joints) >= bones:
        raise ValueError(f"the bone indices do not fit {count} vertices and {bones} bones")
    gltf.links(glb, attributes, joints, weights, per)


def convert(h, data, drawn: tuple | None, out, cache: dict) -> tuple[bool, bool]:
    """A processed MeshHandler `h` of Mesh `data` into `out` (.glb); `drawn` is what
    `renderers` found for it. (It has a colour texture, its bones are named by hash.) A skin
    needs bind poses and bone weights both: a mesh with one and not the other is written
    unskinned, as glTF wants."""
    count = h.m_VertexCount or len(h.m_Vertices or ())
    if not count or not h.m_Vertices:
        raise ValueError("no vertices")
    glb, (bones, materials) = gltf.Glb(), drawn or ([], [])
    poses = (getattr(data, "m_BindPose", None) or ()) if h.m_BoneIndices else ()
    binds = [mirrored(m) for m in poses]
    hashes = getattr(data, "m_BoneNameHashes", None) or []
    roots = skeleton(glb, binds, bones, hashes) if binds else []
    attributes = _attributes(glb, h, count)
    if binds:
        _weights(glb, h, attributes, count, len(binds))
    primitives, made = [], {}
    for n, (triangles, sub) in enumerate(zip(h.get_triangles(), data.m_SubMeshes)):
        part = _primitive(glb, triangles, getattr(sub, "baseVertex", 0) or 0, count)
        if part is None:
            continue
        found = _texture(glb, materials[n], made, cache) if n < len(materials) else None
        if found is not None:
            colour = {"baseColorTexture": {"index": found}, "metallicFactor": 0.0}
            glb.doc["materials"].append({"pbrMetallicRoughness": colour})
            part["material"] = len(glb.doc["materials"]) - 1
        primitives.append({"attributes": attributes} | part)
    if not primitives:
        raise ValueError("no triangles")
    gltf.finish(glb, str(data.m_Name or "mesh"), primitives, roots, out)
    return bool(made), bool(binds) and len(bones) != len(binds)


def write(ctx, obj, data, name: str, record: dict) -> int:
    """`mesh/<name>.glb` for one Mesh: 1 when written; one that cannot be is counted with the
    first reason (`summary`), its `.obj` kept."""
    if ctx.selected_exts is not None and ".glb" not in ctx.selected_exts:
        return 0
    said = record["shared"].setdefault("glb", dict.fromkeys(("made", "lost", "bare", "hash"), 0))
    if record.get("drawn") is None:  # once per loaded group (`_export_env` resets it)
        record["drawn"] = renderers(record.get("env"))
    try:
        from UnityPy.helpers.MeshHelper import MeshHandler

        handler = MeshHandler(data)
        handler.process()
        folder = ctx.staging / "mesh"
        folder.mkdir(parents=True, exist_ok=True)
        target, drawn = ws.next_free(folder / f"{name}.glb"), record["drawn"].get(_key(obj))
        textured, hashed = convert(handler, data, drawn, target, said.setdefault("png", {}))
    except Exception as exc:  # noqa: BLE001  (counted and said; the .obj stands)
        said["lost"] += 1
        said.setdefault("why", f"{name}: {exc}"[:160])
        return 0
    said["made"] += 1
    said["bare"] += not textured
    said["hash"] += hashed
    return 1


def summary(ctx, shared: dict) -> list[str]:
    """What the .glb pass made, and what it could not (never silent)."""
    said = shared.get("glb")
    if not said:
        return []
    ctx.log(f"glTF: {said['made']} mesh(es) also as .glb (mesh/)", stage="export")
    notes = []
    if said["lost"]:
        why = said.get("why", "")
        notes.append(f"{said['lost']} mesh(es) not written as .glb (the .obj stands): {why}")
    if said["bare"]:
        notes.append(
            f"{said['bare']} .glb mesh(es) untextured: no main texture (_MainTex) resolved "
            "through a renderer loaded with them"
        )
    if said["hash"]:
        notes.append(
            f"{said['hash']} skinned .glb mesh(es) with bones named by hash, unparented: no "
            "SkinnedMeshRenderer loaded with them"
        )
    return notes
