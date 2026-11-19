"""decode.mdl (doc 16.0c): Source engine models into glTF binaries (`.glb`), in process, on the
shared writer (viwo/contracts/gltf.py) over studio.py's reader. Each `.mdl` finds its `.vvd` and
its `.vtx` (`.dx90.vtx` first, then `.dx80`, `.sw`, plain) by name in its own folder or in the
workspace's `vvd/` and `vtx/` groups; a name two models share (COLLECT's `name__1`) is told
apart by the checksum all three files carry. The `.glb` holds LOD 0 of the default model of
every body part: positions, normals, UVs, the bones in their reference pose with the engine's
own bind matrices (poseToBone), up to three weights a vertex, one primitive per mesh named after
its material, and that material's `$basetexture` embedded as PNG when its `.vmt` and `.vtf` are
in the run (decode.vtf's own conversion, the PNG it writes beside the texture; a `.vmt` shared
by name is taken from a cdmaterials folder of the model first); otherwise the material is
untextured and counted. Source is right-handed, Z up, X forward: glTF's (x, y, z) is Source's
(y, z, x), a rotation, so the model faces glTF's +Z and keeps its sides; the `.vtx` lists front
faces clockwise (Direct3D's order, as Crowbar and SourceIO read it), so each triangle is wound
the other way. The rest pose is the bind pose the file holds: a model whose data lies on its
side (TF2's characters, made Y-up) lies in the .glb too, where the game stands it up through
its animations. Flexes, animations, eyeballs, attachments, other bodygroup choices and other
LODs are not in it; a model with no mesh (an animation library) is counted, not converted."""

import re
import struct
from array import array
from itertools import count
from pathlib import Path

from viwo.contracts import gltf
from viwo.contracts import workspace as ws
from viwo.contracts.gltf import FLOAT, UINT, Glb
from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from . import studio, vtf

SLOT = SlotDefinition("decode.mdl", "decode", "source", "mdl-builtin", suffixes=(".mdl",))
VTX = (".dx90", ".dx80", ".sw", "")
AXES = (1, 2, 0)  # glTF axis n is Source axis AXES[n]
BASE = re.compile(rb'"?\$basetexture"?\s+"?([^"\s]+)', re.IGNORECASE)
CACHE = 64  # PNG textures kept across the models of one call


def _folder(model: Path, ext: str) -> Path:
    """Where the run keeps files of this kind: the workspace's group (`vvd/`), else the
    model's own folder."""
    group = model.parent.parent / ext
    return group if model.parent.name.lower() == "mdl" and group.is_dir() else model.parent


def _named(folder: Path, stem: str, suffix: str):
    """`stem.suffix`, then the names COLLECT gives others of that name (`stem__1.suffix`)."""
    for n in count():
        file = folder / (f"{stem}__{n}{suffix}" if n else f"{stem}{suffix}")
        if not file.is_file():
            if n:
                return
            continue
        yield file


def _companion(model: Path, checksum: int, ext: str, middles: tuple, at: int) -> bytes:
    """The .vvd or .vtx of this model: the first of its name carrying its checksum."""
    stem = re.sub(r"__\d+$", "", model.stem)
    for middle in middles:
        for file in _named(_folder(model, ext), stem + middle, f".{ext}"):
            with open(file, "rb") as fh:
                head = fh.read(at + 4)
            if len(head) == at + 4 and struct.unpack_from("<i", head, at)[0] == checksum:
                return file.read_bytes()
    raise ValueError(f"no .{ext} of this model (same name and checksum) in the run")


def _texture(model: Path, name: str, dirs: list, cache: dict) -> bytes | None:
    """The PNG of a material's $basetexture, None when its .vmt or .vtf is not in the run."""
    found = []
    for file in _named(_folder(model, "vmt"), Path(name.replace("\\", "/")).name, ".vmt"):
        hit = BASE.search(file.read_bytes())
        found += [hit.group(1).decode("utf-8", "replace").replace("\\", "/")] if hit else []
    folders = {d.replace("\\", "/").strip("/").lower() for d in dirs}
    mine = [t for t in found if t.rpartition("/")[0].lower() in folders]
    if not (mine or found):
        return None
    stem = re.sub(r"\.vtf$", "", (mine or found)[0].rpartition("/")[2], flags=re.IGNORECASE)
    file = _folder(model, "vtf") / f"{stem}.vtf"
    if file not in cache:
        if len(cache) >= CACHE:
            cache.clear()
        try:
            cache[file] = vtf.to_png(file.read_bytes()) if file.is_file() else None
        except Exception:  # noqa: BLE001  (Pillow missing or a texture it refuses: untextured)
            cache[file] = None
    return cache[file]


def _attributes(glb: Glb, blob: bytes) -> dict:
    """POSITION, NORMAL, TEXCOORD_0 of the 48-byte vertices, Source's axes turned to glTF's."""
    numbers = array("f", blob)
    n = len(blob) // studio.VERTEX
    out = {}
    for name, first in (("POSITION", 4), ("NORMAL", 7)):
        values = array("f", bytes(12 * n))
        for k in range(3):
            values[k::3] = numbers[first + AXES[k] :: 12]
        out[name] = glb.accessor(values, "VEC3", FLOAT)
    uv = array("f", bytes(8 * n))
    uv[0::2], uv[1::2] = numbers[10::12], numbers[11::12]
    out["TEXCOORD_0"] = glb.accessor(uv, "VEC2", FLOAT)
    return out


def _skin(glb: Glb, bones: list, blob: bytes, attributes: dict) -> list[int]:
    """The joints in the reference pose with poseToBone as their inverse bind matrices, every
    vertex's (up to) three weights; the root joints."""
    nodes, binds = [], array("f")
    for name, _, (x, y, z), (a, b, c, w), pose in bones:
        nodes.append({"name": name, "translation": [y, z, x], "rotation": [b, c, a, w]})
        turned = [[pose[r][c] for c in AXES] + [pose[r][3]] for r in AXES]
        binds.extend(gltf.columns(turned))
    gltf.skin(glb, nodes, [bone[1] for bone in bones], binds)
    numbers, n = array("f", blob), len(blob) // studio.VERTEX
    joints, weights, used = array("H", bytes(6 * n)), array("f", bytes(12 * n)), blob[15::48]
    for k in range(3):
        column = [j if k < u else 0xFFFF for j, u in zip(blob[12 + k :: 48], used)]
        if max((j for j in column if j != 0xFFFF), default=0) >= len(bones):
            raise ValueError("a vertex is weighted to a bone the model does not have")
        joints[k::3], weights[k::3] = array("H", column), numbers[k::12]
    gltf.links(glb, attributes, joints, weights, 3)
    return [i for i, bone in enumerate(bones) if bone[1] < 0]


def _material(glb: Glb, model: Path, mdl: dict, slot: int, cache: dict) -> tuple[int, bool]:
    """(glTF material of a mesh's material slot, textured)."""
    skins, names = mdl["skins"], mdl["textures"]
    index = skins[slot] if 0 <= slot < len(skins) else slot
    name = names[index] if 0 <= index < len(names) else f"material_{index}"
    png = _texture(model, name, mdl["dirs"], cache)
    material = {"name": name, "pbrMetallicRoughness": {"metallicFactor": 0.0}}
    if png is not None:
        image = gltf.texture(glb, png, f"{Path(name).name}.png")
        material["pbrMetallicRoughness"]["baseColorTexture"] = {"index": image}
    glb.doc["materials"].append(material)
    return len(glb.doc["materials"]) - 1, png is not None


def _parts(glb: Glb, model: Path, mdl: dict, vertices: bytes, meshes: list, cache: dict):
    """The default models' vertices one after another, a primitive per mesh with triangles
    (each wound the other way), the materials made: (vertices, primitives, materials)."""
    blob, made, primitives, size = bytearray(), {}, [], studio.VERTEX
    for part, tris in zip(mdl["parts"], meshes):
        if not part:
            continue
        base, end = len(blob) // size, len(blob) // size + part[1]
        blob += vertices[part[0] * size : (part[0] + part[1]) * size]
        if len(blob) != end * size:
            raise ValueError("a model's vertices run past the .vvd")
        for (slot, _, offset), mesh in zip(part[2], tris):
            flat = array("I", (base + offset + i for t in range(0, len(mesh), 3)
                               for i in (mesh[t], mesh[t + 2], mesh[t + 1])))  # fmt: skip
            if flat and max(flat) >= end:
                raise ValueError("a mesh points past its model's vertices")
            if not flat:
                continue
            if slot not in made:
                made[slot] = _material(glb, model, mdl, slot, cache)
            primitives.append({"indices": glb.accessor(flat, "SCALAR", UINT, gltf.INDICES)})
            primitives[-1]["material"] = made[slot][0]
    return bytes(blob), primitives, made


def convert(model: Path, out: Path, cache: dict) -> tuple[int, int] | None:
    """model (.mdl) -> out (.glb): (materials, untextured ones); None: it holds no mesh."""
    mdl = studio.read_mdl(model.read_bytes())
    if not any(part and part[1] > 0 for part in mdl["parts"]):
        return None
    sum_ = mdl["checksum"]
    vertices = studio.read_vvd(_companion(model, sum_, "vvd", ("",), 8), sum_)
    meshes = studio.read_vtx(_companion(model, sum_, "vtx", VTX, 16), sum_, mdl["parts"])
    glb, roots = Glb(), []
    blob, primitives, made = _parts(glb, model, mdl, vertices, meshes, cache)
    if not primitives:
        raise ValueError("no triangles at LOD 0")
    attributes = _attributes(glb, blob)
    if mdl["bones"]:
        roots = _skin(glb, mdl["bones"], blob, attributes)
    for primitive in primitives:
        primitive["attributes"] = attributes
    gltf.finish(glb, model.stem, primitives, roots, out)
    return len(made), sum(1 for _, textured in made.values() if not textured)


class MdlDecoder(Decoder):
    backend_id, owner, license = "mdl-builtin", "source", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        return self.decode_many([path], dest, ctx)

    def decode_many(self, paths: list[Path], dest: Path, ctx) -> Outcome:
        """Every model of the batch into dest; what failed is counted with the first reason,
        models without a mesh and untextured materials are counted (never silent)."""
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
        note = f"{len(paths)} model(s): {said['made']} written as .glb, {said['plain']} without a "
        note += f"mesh (animations); {said['bare']} of {said['materials']} material(s) untextured"
        note += " (no .vmt with a $basetexture whose .vtf is in the run)" if said["bare"] else ""
        partial = f"{len(lost)} model(s) not converted, e.g. {lost[0]}" if lost else ""
        kind = OutcomeKind.FAILED if lost and not said["made"] else OutcomeKind.OK
        return Outcome(kind, said["made"], error=partial, notes=(note,))
