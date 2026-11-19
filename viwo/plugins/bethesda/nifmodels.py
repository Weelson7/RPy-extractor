"""decode.nif (doc 16.0c): Bethesda NIF models into glTF binaries (`.glb`), in process, on the
shared writer (viwo/contracts/gltf.py) over nif.py's reader (Skyrim, Skyrim SE, Fallout 4).
The node tree becomes glTF nodes (names, local transforms); each shape (NiTriShape with its
NiTriShapeData, BSTriShape with its own vertices or, skinned in Skyrim SE, with those of its
NiSkinPartition: partition.py) a node with a mesh of one primitive: its
positions, normals, tangents, every UV set, vertex colours as data (`_COLOR_0`), triangles as
stored, and its shader property as the material, named after the property (Fallout 4: its
`.bgsm` path) or else its colour texture; that texture is embedded as PNG when the `.dds` is in
the run (Pillow reads it), otherwise the material is untextured and counted. A skinned shape
gets its skin: its bones as joints, every weight (normalised to sum to one; from the
NiSkinPartition, each partition's bones mapped to the skin's, when NiSkinData or the shape's
own vertices do not hold them), and as inverse
bind matrices the transforms Gamebryo skins with: bone^-1 * shape * rootParentToSkin *
rootParent^-1 * bone * skinToBone, which is skinToBone when the file is consistent. NIF is
right-handed, Z up, Y forward: glTF's (x, y, z) is NIF's (-x, z, y), a rotation, so a model
faces glTF's +Z, keeps its sides and its winding. Bethesda's tangent arrays are named the other
way round (the one called tangents runs along V, as NifSkope and nifly write it): TANGENT is the
one along U, its handedness from the other. Collision, particles, controllers, animations and
Fallout 4's `.bgsm` materials are not read; a NIF without a shape is counted, not converted."""

import io
import struct
from array import array
from pathlib import Path

from viwo.contracts import gltf
from viwo.contracts import workspace as ws
from viwo.contracts.gltf import FLOAT, UINT, Glb
from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from . import nif as reader
from . import partition

SLOT = SlotDefinition("decode.nif", "decode", "bethesda", "nif-builtin", suffixes=(".nif",))
P, S = (0, 2, 1), (-1.0, 1.0, 1.0)  # glTF axis n is NIF axis P[n] times S[n]
CACHE = 64  # PNG textures kept across the models of one call


def turned(m) -> list[list[float]]:
    """A NIF 3x4 matrix in glTF's axes (conjugated by the rotation)."""
    return [[S[r] * S[c] * m[P[r]][P[c]] for c in range(3)] + [S[r] * m[P[r]][3]] for r in range(3)]


def _vectors(values: array, unit: bool = False) -> array:
    out = array("f", bytes(4 * len(values)))
    for n in range(3):
        out[n::3] = array("f", (S[n] * v for v in values[P[n] :: 3]))
    return gltf.unit(out) if unit else out


def _texture(model: Path, path: str, cache: dict) -> bytes | None:
    """The PNG of a `.dds` named by the NIF: in the workspace's `dds/` group, else under a
    folder above the model (an extracted Data tree); None when it is not in the run."""
    rel = path.replace("\\", "/").strip("/")
    name = rel.rpartition("/")[2]
    group = model.parent.parent / "dds"
    found = [group / name] if model.parent.name.lower() == "nif" else []
    found += [up / rel for up in list(model.parents)[:6]] + [model.parent / name]
    file = next((f for f in found if name and f.is_file()), None)
    if file is None:
        return None
    if file not in cache:
        if len(cache) >= CACHE:
            cache.clear()
        try:
            from PIL import Image

            with Image.open(file) as image:
                cache[file] = io.BytesIO()
                image.save(cache[file], "PNG")
                cache[file] = cache[file].getvalue()
        except Exception:  # noqa: BLE001  (Pillow missing or a format it refuses: untextured)
            cache[file] = None
    return cache[file]


def _material(glb: Glb, nif, ref: int, model: Path, cache: dict) -> tuple[int, bool]:
    name, path = reader.material(nif, ref)
    png = _texture(model, path, cache) if path else None
    stem = path.replace("\\", "/").rpartition("/")[2].rpartition(".")[0]
    entry = {"name": name or stem or f"material_{ref}"}
    entry["pbrMetallicRoughness"] = {"metallicFactor": 0.0}
    if png is not None:
        image = gltf.texture(glb, png, f"{stem}.png")
        entry["pbrMetallicRoughness"]["baseColorTexture"] = {"index": image}
    glb.doc["materials"].append(entry)
    return len(glb.doc["materials"]) - 1, png is not None


def _attributes(glb: Glb, shape: dict) -> dict:
    out = {"POSITION": glb.accessor(_vectors(shape["positions"]), "VEC3", FLOAT)}
    if "normals" in shape:
        normals = _vectors(shape["normals"], unit=True)
        out["NORMAL"] = glb.accessor(normals, "VEC3", FLOAT)
        if "tangents" in shape:
            u, v = _vectors(shape["bitangents"], True), _vectors(shape["tangents"])
            out["TANGENT"] = glb.accessor(gltf.tangents(normals, u, v), "VEC4", FLOAT)
    for n, uv in enumerate(shape["uvs"]):
        out[f"TEXCOORD_{n}"] = glb.accessor(uv, "VEC2", FLOAT)
    if "colours" in shape:
        out["_COLOR_0"] = glb.accessor(shape["colours"], "VEC4", FLOAT)
    if any(len(v) != 3 * shape["count"] for k, v in shape.items() if k in ("positions", "normals")):
        raise ValueError("a shape's vertex arrays differ in length")
    return out


def _tree(nif) -> dict:
    """ref -> (name, local 3x4, child refs, shape or None) for every node and shape."""
    objects, unread = {}, [kind for kind in nif.kinds if kind in reader.UNREAD]
    if unread:
        raise ValueError(f"{unread[0]} blocks are not read")
    for ref, kind in enumerate(nif.kinds):
        if kind not in reader.NODES | reader.TRI | reader.BSTRI:
            continue
        raw = nif.block(ref)[1]
        name, local, at = reader.av_object(nif, raw)
        if kind in reader.NODES:
            objects[ref] = (name, local, reader.children(raw, at), None)
        else:
            read = reader.tri_shape if kind in reader.TRI else reader.bs_tri_shape
            shape = read(nif, raw, at)
            if shape.pop("partition", False):  # Skyrim SE skinned: its NiSkinPartition holds it
                shape |= partition.shape(nif, shape["skin"])
            objects[ref] = (name, local, [], shape)
    return objects


class _Scene:
    """One NIF being written: its objects, their parents, glTF node of each, the materials."""

    def __init__(self, nif, model: Path, cache: dict) -> None:
        self.nif, self.model, self.cache, self.glb = nif, model, cache, Glb()
        self.objects, self.parent, self.made, self.meshes = _tree(nif), {}, {}, []
        for ref, (_, _, kids, _) in self.objects.items():
            for kid in kids:
                if kid in self.objects and kid != ref:
                    self.parent.setdefault(kid, ref)  # a child two nodes claim: the first
        self.index = {ref: n for n, ref in enumerate(self.objects)}

    def world(self, ref: int) -> list:
        chain = []
        while ref is not None:
            if ref in chain:
                raise ValueError("the node tree has a cycle")
            chain.append(ref)
            ref = self.parent.get(ref)
        out = [[float(r == c) for c in range(4)] for r in range(3)]
        for ref in reversed(chain):
            out = gltf.times(out, self.objects[ref][1])
        return out

    def skin(self, ref: int, shape: dict, attributes: dict) -> int:
        """The shape's skin: joints, inverse bind matrices, the links in `attributes`."""
        held = reader.skin(self.nif, shape["skin"], shape["count"])
        links, bones = shape.get("links") or held["links"], held["bones"]
        if links is None and held["partition"] < 0:
            raise ValueError("a skin without weights and without a NiSkinPartition: not read")
        if links is None:  # NiSkinData without weights: the partitions hold them
            links = partition.links(partition.read(self.nif, held["partition"])["parts"],
                                    shape["count"])  # fmt: skip
        if any(b not in self.objects for b in bones) or len(held["binds"]) != len(bones):
            raise ValueError("a skin's bones are not nodes of the file")
        binds, root = array("f"), held["root"]
        for bone, to_bone in zip(bones, held["binds"]):
            if held["to_skin"] is not None and root in self.objects:
                at = self.world(bone)
                lead = gltf.times(gltf.inverse(at), self.world(ref))
                lead = gltf.times(lead, gltf.times(held["to_skin"], gltf.inverse(self.world(root))))
                to_bone = gltf.times(gltf.times(lead, at), to_bone)
            binds.extend(gltf.columns(turned(to_bone)))
        joints, weights, per = links
        if len(joints) != per * shape["count"]:
            raise ValueError("a skin's links do not cover its shape's vertices")
        joints, weights = gltf.weighed(joints, weights, per)
        if max((j for j in joints if j != 0xFFFF), default=0) >= len(bones):
            raise ValueError("a vertex is weighted to a bone its skin does not have")
        glb = self.glb
        gltf.links(glb, attributes, joints, weights, per)
        matrices = glb.accessor(binds, "MAT4", FLOAT, 0)
        skin = {"joints": [self.index[b] for b in bones], "inverseBindMatrices": matrices}
        glb.doc.setdefault("skins", []).append(skin)
        return len(glb.doc["skins"]) - 1

    def mesh(self, ref: int, name: str, shape: dict) -> dict:
        """The shape's mesh (one primitive) and skin, as fields of its node; {} without
        triangles."""
        flat = array("I", shape["triangles"])
        if not flat:
            return {}
        if max(flat) >= shape["count"]:
            raise ValueError("a triangle points past its shape's vertices")
        attributes = _attributes(self.glb, shape)
        if shape["shader"] not in self.made:
            self.made[shape["shader"]] = _material(
                self.glb, self.nif, shape["shader"], self.model, self.cache
            )
        indices = self.glb.accessor(flat, "SCALAR", UINT, gltf.INDICES)
        primitive = {"attributes": attributes, "indices": indices}
        self.meshes.append({"name": name, "primitives": [primitive]})
        primitive["material"] = self.made[shape["shader"]][0]
        out = {"mesh": len(self.meshes) - 1}
        return out | ({"skin": self.skin(ref, shape, attributes)} if shape["skin"] >= 0 else {})

    def write(self, out: Path) -> None:
        for ref, (name, local, kids, shape) in self.objects.items():
            node = {"name": name, "matrix": gltf.columns(turned(local))}
            kids = [self.index[k] for k in kids if self.parent.get(k) == ref]
            node |= {"children": kids} if kids else {}
            self.glb.doc["nodes"].append(node | (self.mesh(ref, name, shape) if shape else {}))
        if not self.meshes:
            raise ValueError("its shapes hold no triangles")
        roots = [self.index[r] for r in self.objects if r not in self.parent]
        self.glb.doc |= {"meshes": self.meshes, "scenes": [{"nodes": roots}], "scene": 0}
        self.glb.save(out)


def convert(model: Path, out: Path, cache: dict) -> tuple[int, int] | None:
    """model (.nif) -> out (.glb): (materials, untextured ones); None: it holds no shape."""
    scene = _Scene(reader.Nif(model.read_bytes()), model, cache)
    if not any(shape for *_, shape in scene.objects.values()):
        return None
    scene.write(out)
    return len(scene.made), sum(1 for _, textured in scene.made.values() if not textured)


class NifDecoder(Decoder):
    backend_id, owner, license = "nif-builtin", "bethesda", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        return self.decode_many([path], dest, ctx)

    def decode_many(self, paths: list[Path], dest: Path, ctx) -> Outcome:
        """Every model of the batch into dest; what failed is counted with the first reason,
        models without a shape and untextured materials are counted (never silent)."""
        dest.mkdir(parents=True, exist_ok=True)
        cache, lost, said = {}, [], {"made": 0, "plain": 0, "materials": 0, "bare": 0}
        for path in paths:
            if ctx.cancel.cancelled:
                break
            try:
                result = convert(path, ws.next_free(dest / f"{path.stem}.glb"), cache)
            except (OSError, ValueError, struct.error, IndexError) as exc:
                lost.append(f"{path.name}: {exc}")
                continue
            said["plain" if result is None else "made"] += 1
            said["materials"] += result[0] if result else 0
            said["bare"] += result[1] if result else 0
        note = f"{len(paths)} NIF(s): {said['made']} written as .glb, {said['plain']} without a "
        note += f"shape; {said['bare']} of {said['materials']} material(s) untextured"
        note += " (no colour map, or its .dds not in the run)" if said["bare"] else ""
        partial = f"{len(lost)} NIF(s) refused, e.g. {lost[0]}" if lost else ""
        kind = OutcomeKind.FAILED if lost and not said["made"] else OutcomeKind.OK
        return Outcome(kind, said["made"], error=partial, notes=(note,))
