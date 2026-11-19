"""decode.rigid_model_v2 (doc 16.0c): Total War rigid models into glTF binaries (`.glb`), in
process, on the shared writer (viwo/contracts/gltf.py) over rigid.py's reader (versions 5, 6, 7).
LOD 0 only: each mesh group a primitive with what its vertex layout holds (positions; normals,
tangents, one or two UV sets, the vertex colours as data (`_COLOR_0`) when it has them; a bow
wave's second position and float as data, as stored: `_POSITION_1`, `_VALUE_0`), its
triangles, and a material named after the group (else its colour map, its decal), holding the
shader, the material type, the layout and every texture path as extras; a decal's projection
box is drawn see-through (alpha 0.25, its decal path in the extras). The colour
map (texture type 0) is embedded as PNG when its `.dds` is in the run (Pillow reads it), else
the material is untextured and counted. A weighted or cinematic group carries its bone links
(2 or 4 a vertex, scaled to sum to one): with the skeleton the header names in the run (its
`.anim` for names and parents, its `.bone_inv_trans_mats` for the bind matrices; the reference
pose is the inverse of those), as a glTF skin; without it, as data (`_JOINTS_0`, `_WEIGHTS_0`),
counted with the reason (also when a vertex weighs on a bone past the skeleton's last); no pose
is invented. A group without bones in a skinned model follows the first bone. A group of a
layout not read (flag placements and effects hold no vertex data) is left out and counted with
why; a file holding only such groups is refused with it. Warscape is left-handed, Y up: X is
mirrored on every position, direction and matrix, each triangle is wound the other way so its front
stays its front, and a tangent's handedness is taken after the mirror. Textures are found by
name in the workspace's `dds/` group, or by their game path above the model's folder; a name
two folders share is taken as the first of that name. A skeleton is the first pair of its name
(COLLECT's `name__1` included) whose `.anim` reads and whose bind matrices match its bones."""

import glob
import io
import struct
from array import array
from pathlib import Path

from viwo.contracts import gltf
from viwo.contracts import workspace as ws
from viwo.contracts.gltf import FLOAT, UINT, Glb
from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from . import rigid

SUFFIX = ".rigid_model_v2"
SLOT = SlotDefinition("decode.rigid_model_v2", "decode", "warscape", "rmv2-builtin",
                      suffixes=(SUFFIX,))  # fmt: skip
SIDE = (-1.0, 1.0, 1.0)  # the mirror: X turns
CACHE = 64  # PNG textures and skeletons kept across the models of one call


def mirrored(m) -> list[list[float]]:
    return [[m[r][c] * SIDE[r] * (SIDE[c] if c < 3 else 1.0) for c in range(4)] for r in range(3)]


def _mirror(values: array) -> array:
    values[0::3] = array("f", (-v for v in values[0::3]))
    return values


def found(model: Path, rel: str) -> list[Path]:
    """The files a model names by its game path: in the workspace's group of its kind (with
    the others of that name COLLECT kept, `name__1`...), else under a folder above the model
    (an extracted pack)."""
    rel = rel.replace("\\", "/").strip("/")
    stem, _, kind = rel.rpartition("/")[2].rpartition(".")
    out = []
    if model.parent.name.lower() == SUFFIX[1:] and stem:
        group = model.parent.parent / kind.lower()
        out += [group / f"{stem}.{kind}"] + sorted(group.glob(f"{glob.escape(stem)}__*.{kind}"))
    out += [up / rel for up in list(model.parents)[:8]]
    return [f for f in out if stem and f.is_file()]


def find(model: Path, rel: str) -> Path | None:
    """The first of `found`: a name two folders share is taken as the first of that name."""
    return next(iter(found(model, rel)), None)


def _cached(cache: dict, key, make):
    if key not in cache:
        if len(cache) >= CACHE:
            cache.clear()
        cache[key] = make()
    return cache[key]


def _png(file: Path) -> bytes | None:
    try:
        from PIL import Image

        with Image.open(file) as image:
            out = io.BytesIO()
            image.save(out, "PNG")
        return out.getvalue()
    except Exception:  # noqa: BLE001  (Pillow missing or a format it refuses: untextured)
        return None


def _skeleton(model: Path, name: str):
    """(names, parents, inverse binds) or why there is none: the first pair of files of its
    name (COLLECT keeps others of that name as `name__1`) that reads and agrees."""
    anims, binds = (found(model, f"animations/skeletons/{name}{x}") if name else []
                    for x in (".anim", ".bone_inv_trans_mats"))  # fmt: skip
    if not (anims and binds):
        return f"its skeleton {name!r} is not in the run" if name else "it names no skeleton"
    why = ""
    for anim, inverse in ((a, b) for a in anims for b in binds):
        try:
            return rigid.skeleton(anim.read_bytes(), inverse.read_bytes())
        except (OSError, ValueError, struct.error, UnicodeDecodeError) as exc:
            why = why or str(exc)
    return f"its skeleton {name!r} does not read: {why}"


def _rig(glb: Glb, held) -> list[int]:
    """The joints in the bind pose (each world matrix the inverse of its bind matrix) and the
    skin: the root joints."""
    names, parents, binds = held
    worlds, nodes, inverse = [gltf.inverse(b) for b in binds], [], array("f")
    for i, (bone, parent) in enumerate(zip(names, parents)):
        local = gltf.times(binds[parent], worlds[i]) if parent >= 0 else worlds[i]
        nodes.append({"name": bone, "matrix": gltf.columns(mirrored(local))})
        inverse.extend(gltf.columns(mirrored(binds[i])))
    gltf.skin(glb, nodes, parents, inverse)
    return [i for i, parent in enumerate(parents) if parent < 0]


def _attributes(glb: Glb, data: dict) -> dict:
    """POSITION, and NORMAL, TANGENT, TEXCOORD_n, _COLOR_0 and the layout's data (as stored)
    when the layout has them."""
    out = {"POSITION": glb.accessor(_mirror(data["positions"]), "VEC3", FLOAT)}
    if "normals" in data:
        normals = gltf.unit(_mirror(data["normals"]))
        out["NORMAL"] = glb.accessor(normals, "VEC3", FLOAT)
    if "normals" in data and "along_u" in data:
        u, v = gltf.unit(_mirror(data["along_u"])), _mirror(data["along_v"])
        out["TANGENT"] = glb.accessor(gltf.tangents(normals, u, v), "VEC4", FLOAT)
    for n, uv in enumerate(data["uvs"]):
        out[f"TEXCOORD_{n}"] = glb.accessor(uv, "VEC2", FLOAT)
    if "colours" in data:
        out["_COLOR_0"] = glb.accessor(data["colours"], "VEC4", FLOAT)
    for key, values in data["data"].items():
        width = len(values) // (len(data["positions"]) // 3)
        out[key] = glb.accessor(values, ("SCALAR", "VEC2", "VEC3", "VEC4")[width - 1], FLOAT)
    return out


def _links(glb: Glb, attributes: dict, data: dict, bones: int) -> None:
    """The bone links: JOINTS_n/WEIGHTS_n of a skin of `bones` joints, else (bones 0) as data;
    a static group in a skinned model weighs fully on the first bone."""
    count = len(data["positions"]) // 3
    joints, weights, per = data.get("links") or ([0] * count, [1.0] * count, 1)
    joints, weights = gltf.weighed(joints, weights, per)
    if bones and max((j for j in joints if j != 0xFFFF), default=0) >= bones:
        raise ValueError("a vertex is weighted to a bone its skeleton does not have")
    if bones:
        gltf.links(glb, attributes, joints, weights, per)
        return
    found: dict = {}
    gltf.links(glb, found, joints, weights, per)
    attributes |= {f"_{key}": index for key, index in found.items()}


def _material(glb: Glb, model: Path, mesh: dict, cache: dict) -> tuple[int, bool]:
    """Named after the group (else its colour map, its decal, its type); a decal's projection
    box is drawn see-through."""
    colour = next((path for kind, path in mesh["textures"] if kind == 0 and path), "")
    file = find(model, colour) if colour else None
    png = _cached(cache, ("png", file), lambda: _png(file)) if file else None
    decal = mesh.get("decal", "")
    named = colour or decal
    entry = {"name": mesh["name"] or named.rpartition("/")[2] or f"group_{mesh['type']}"}
    entry["pbrMetallicRoughness"] = {"metallicFactor": 0.0}
    entry["extras"] = {"shader": mesh["shader"], "material_type": mesh["type"],
                       "layout": mesh["layout"].name,
                       "textures": [path for _, path in mesh["textures"] if path]}  # fmt: skip
    if decal:
        entry["extras"]["decal"] = decal
        entry["pbrMetallicRoughness"]["baseColorFactor"] = [1.0, 1.0, 1.0, 0.25]
        entry["alphaMode"] = "BLEND"
    if png is not None:
        image = gltf.texture(glb, png, f"{Path(colour).stem}.png")
        entry["pbrMetallicRoughness"]["baseColorTexture"] = {"index": image}
    glb.doc["materials"].append(entry)
    return len(glb.doc["materials"]) - 1, png is not None


def _primitive(glb: Glb, model: Path, mesh: tuple, bones: int, cache: dict) -> dict:
    """A mesh group (and its vertices) as a primitive: attributes, links, triangles wound the
    other way."""
    mesh, data = mesh
    count = len(data["positions"]) // 3
    tri = mesh["indices"]
    if max(tri) >= count:
        raise ValueError("a triangle points past its mesh group's vertices")
    attributes = _attributes(glb, data)
    if "links" in data or bones:
        _links(glb, attributes, data, bones)
    flat = array("I", (tri[t + d] for t in range(0, len(tri), 3) for d in (0, 2, 1)))
    material, textured = _material(glb, model, mesh, cache)
    indices = glb.accessor(flat, "SCALAR", UINT, gltf.INDICES)
    return {"attributes": attributes, "indices": indices, "material": material, "_": textured}


def _needed(shown: list) -> int:
    """The highest bone any vertex weighs on (-1: none)."""
    links = [data["links"] for _, data in shown if "links" in data]
    return max((j for joints, weights, _ in links for j, w in zip(joints, weights) if w > 0),
               default=-1)  # fmt: skip


def convert(model: Path, out: Path, cache: dict) -> dict | None:
    """model (.rigid_model_v2) -> out (.glb): what it held (materials, untextured ones,
    groups left out, how its bones went); None: it holds no mesh."""
    held = rigid.read(model.read_bytes())
    shown = [m for m in held["meshes"] if m["layout"] and m["count"] and len(m["indices"])]
    left = [m for m in held["meshes"] if not m["layout"]]
    if not shown:
        if left:
            raise ValueError(f"no mesh group of a layout read ({left[0]['why']})")
        return None
    glb, roots, rig, bones = Glb(), [], "", 0
    shown = [(mesh, rigid.vertices(mesh)) for mesh in shown]
    if any(mesh["layout"].bones[1] for mesh, _ in shown):
        name, need = held["skeleton"], _needed(shown)
        skeleton = _cached(cache, ("skeleton", name), lambda: _skeleton(model, name))
        rig = skeleton if isinstance(skeleton, str) else "skinned"
        if rig == "skinned" and need >= len(skeleton[0]):
            rig = f"its skeleton {name!r} has {len(skeleton[0])} bones, a vertex weighs on "
            rig += f"bone {need}"
        if rig == "skinned":
            roots, bones = _rig(glb, skeleton), len(skeleton[0])
    primitives = [_primitive(glb, model, mesh, bones, cache) for mesh in shown]
    bare = sum(1 for p in primitives if not p.pop("_"))
    gltf.finish(glb, model.stem, primitives, roots, out)
    return {"materials": len(primitives), "bare": bare, "left": left, "rig": rig}


class RigidModelDecoder(Decoder):
    backend_id, owner, license = "rmv2-builtin", "warscape", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        return self.decode_many([path], dest, ctx)

    def decode_many(self, paths: list[Path], dest: Path, ctx) -> Outcome:
        """Every model of the batch into dest; what failed is counted with the first reason,
        and so are models without a mesh, groups left out, bone links kept as data and
        untextured materials (never silent)."""
        dest.mkdir(parents=True, exist_ok=True)
        cache, lost, said = {}, [], {"made": 0, "plain": 0, "materials": 0, "bare": 0}
        left, data = [], []
        for path in paths:
            if ctx.cancel.cancelled:
                break
            try:
                result = convert(path, ws.next_free(dest / f"{path.stem}.glb"), cache)
            except (OSError, ValueError, struct.error, IndexError, UnicodeDecodeError) as exc:
                lost.append(f"{path.name}: {exc}")
                continue
            said["plain" if result is None else "made"] += 1
            if result:
                said["materials"] += result["materials"]
                said["bare"] += result["bare"]
                left += [m["why"] for m in result["left"]]
                data += [result["rig"]] if result["rig"] not in ("", "skinned") else []
        return _outcome(len(paths), said, lost, left, data)


def _outcome(total: int, said: dict, lost: list, left: list, data: list) -> Outcome:
    note = f"{total} model(s): {said['made']} written as .glb, {said['plain']} without a mesh; "
    note += f"{said['bare']} of {said['materials']} material(s) untextured"
    note += " (no colour map, or its .dds not in the run)" if said["bare"] else ""
    notes = (note,)
    if data:
        notes += (f"{len(data)} model(s) keep their bone links as data (_JOINTS_0, _WEIGHTS_0),"
                  f" e.g. {data[0]}",)  # fmt: skip
    if left:
        notes += (f"{len(left)} mesh group(s) of layouts not read left out, e.g. {left[0]}",)
    partial = f"{len(lost)} model(s) not converted, e.g. {lost[0]}" if lost else ""
    kind = OutcomeKind.FAILED if lost and not said["made"] else OutcomeKind.OK
    return Outcome(kind, said["made"], error=partial, notes=notes)
