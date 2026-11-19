"""DataTool's models into files anything opens (doc 16.0c): an `.owmdl` with the materials of
its model look (`.owmat`) and their PNG textures becomes one self-contained `.glb` (glTF 2.0):
every submesh with its normals, tangents, UV sets and vertex colours, the skeleton in its
reference pose and every vertex's bone weights, the colour and normal textures embedded as
they were extracted (nothing re-encoded). The formats are read as DataTool writes them
(TankLib/ExportFormats/OverwatchModel.cs and DataTool/SaveLogic/Model.cs, MIT): positions come
Z-up with V flipped for Blender and go back to glTF's Y-up here; bones are already Y-up. The
glTF writer is shared (viwo/contracts/gltf.py)."""

import struct
import sys
from array import array
from pathlib import Path

from viwo.contracts import gltf
from viwo.contracts.gltf import FLOAT, UINT, Glb
from viwo.contracts.gltf import matrix as _matrix
from viwo.contracts.gltf import quaternion as _quaternion
from viwo.contracts.gltf import times as _times

ALBEDO, NORMAL = 2903569922, 378934698  # the texture slots glTF has a place for


class _In:
    def __init__(self, data: bytes) -> None:
        self.data, self.at = data, 0

    def take(self, fmt: str) -> tuple:
        values = struct.unpack_from(fmt, self.data, self.at)
        self.at += struct.calcsize(fmt)
        return values

    def text(self) -> str:  # .NET BinaryWriter string: a 7-bit length, then UTF-8
        size = self.take("<B")[0]
        if size > 127:
            size = size % 128 + self.take("<B")[0] * 128
        self.at += size
        return self.data[self.at - size : self.at].decode("utf-8", "replace")

    def numbers(self, kind: str, count: int) -> array:
        out = array(kind)
        out.frombytes(self.data[self.at : self.at + out.itemsize * count])
        self.at += out.itemsize * count
        if len(out) != count:
            raise ValueError("the file ends inside its data")
        if sys.byteorder == "big":
            out.byteswap()
        return out


def _y_up(values: array, width: int) -> array:
    """(x, y, z[, w]) as written for Blender into glTF's axes: (x, z, -y[, w])."""
    out = array("f", values)
    out[1::width], out[2::width] = values[2::width], array("f", (-v for v in values[1::width]))
    return out


def _mesh(src: _In) -> dict:
    name = src.text()
    material, sets, count, triangles, links = src.take("<QBIIb")
    mesh = {"name": name, "material": material, "count": count}
    mesh["POSITION"] = _y_up(src.numbers("f", 3 * count), 3)
    mesh["NORMAL"] = _y_up(src.numbers("f", 3 * count), 3)
    mesh["TANGENT"] = _y_up(src.numbers("f", 4 * count), 4)
    for n in range(sets):
        uv = src.numbers("f", 2 * count)
        uv[1::2] = array("f", (1.0 - v for v in uv[1::2]))
        mesh[f"TEXCOORD_{n}"] = uv
    mesh["links"] = max(links, 0)
    mesh["joints"] = src.numbers("H", mesh["links"] * count)
    mesh["weights"] = src.numbers("f", mesh["links"] * count)
    # glTF multiplies the colour by COLOR_0, and these are the engine's masks, not a tint:
    # both sets are kept under names a viewer leaves alone
    mesh["_COLOR_A"], mesh["_COLOR_B"] = (src.numbers("f", 4 * count) for _ in range(2))
    mesh["indices"] = src.numbers("I", 3 * triangles)
    return mesh


def read(data: bytes) -> tuple[str, list, list]:
    """(model look path, bones [(name, parent, translation, scale, euler)], meshes)."""
    src = _In(data)
    major, minor = src.take("<HH")
    if major != 2:
        raise ValueError(f"owmdl {major}.{minor}: only version 2 is read")
    look, _name = src.text(), src.text()
    _guid, bones, meshes, _hardpoints = src.take("<IHII")
    skeleton = [
        (src.text(), src.take("<h")[0], src.take("<3f"), src.take("<3f"), src.take("<3f"))
        for _ in range(bones)
    ]
    return look, skeleton, [_mesh(src) for _ in range(meshes)]


def textures(model: Path, look: str) -> dict[int, dict[int, Path]]:
    """material id -> {texture slot: file}, through the model look and its materials; what is
    not on disk is simply absent (the model then comes out untextured there)."""
    out: dict[int, dict[int, Path]] = {}
    file = model.parent / look.replace("\\", "/") if look else None
    if file is None or not file.is_file():
        return out
    src = _In(file.read_bytes())
    if src.take("<HHI")[2] != 1:
        return out
    for _ in range(src.take("<Q")[0]):
        key, material = src.take("<Q")[0], model.parent / "Materials" / Path(src.text()).name
        if not material.is_file():
            continue
        inner = _In(material.read_bytes())
        inner.take("<HHI")
        count = inner.take("<QQI")[0]
        named = [
            (material.parent / inner.text().replace("\\", "/"), inner.take("<I")[0])
            for _ in range(count)
        ]
        out[key] = {slot: path.resolve() for path, slot in named if path.is_file()}
    return out


def _skeleton(glb: Glb, bones: list) -> None:
    """One node per bone in its reference pose, and the skin that binds the meshes to them."""
    local = [_matrix(t, _quaternion(r), s) for _, _, t, s, r in bones]
    world: dict[int, list] = {}

    def placed(i: int, seen: tuple = ()) -> list:
        parent = bones[i][1]
        if i not in world:
            rooted = parent < 0 or parent == i or parent >= len(bones) or parent in seen
            world[i] = local[i] if rooted else _times(placed(parent, (*seen, i)), local[i])
        return world[i]

    nodes = [
        {"name": name, "translation": list(move), "scale": list(scale)}
        | {"rotation": _quaternion(euler)}
        for name, _, move, scale, euler in bones
    ]
    inverse = (v for i in range(len(bones)) for v in gltf.columns(gltf.inverse(placed(i))))
    gltf.skin(glb, nodes, [bone[1] for bone in bones], array("f", inverse))


def _material(glb: Glb, key: int, slots: dict[int, Path], images: dict[Path, int]) -> int:
    """A glTF material with the colour and normal textures the look gives, PNG bytes as they
    are; every other slot stays a file beside the model."""
    material = {"name": f"{key:016X}", "doubleSided": True}
    material["pbrMetallicRoughness"] = {"metallicFactor": 0.0, "roughnessFactor": 0.8}
    for slot, place in ((ALBEDO, "baseColorTexture"), (NORMAL, "normalTexture")):
        file = slots.get(slot)
        if file is None or file.suffix.lower() != ".png":
            continue
        if file not in images:
            images[file] = gltf.texture(glb, file.read_bytes(), file.name)
        holder = material if slot == NORMAL else material["pbrMetallicRoughness"]
        holder[place] = {"index": images[file]}
    glb.doc["materials"].append(material)
    return len(glb.doc["materials"]) - 1


def convert(model: Path, out: Path) -> tuple[str, ...]:
    """model (.owmdl) -> out (.glb); the notes say what the result lacks."""
    look, bones, meshes = read(model.read_bytes())
    slots, glb, images, materials, primitives = textures(model, look), Glb(), {}, {}, []
    if bones:
        _skeleton(glb, bones)
    for mesh in (m for m in meshes if m["count"] and m["indices"]):
        names = ("POSITION", "NORMAL", "TANGENT", "_COLOR_A", "_COLOR_B")
        names += tuple(k for k in mesh if k[:3] == "TEX")
        kinds = {"POSITION": "VEC3", "NORMAL": "VEC3", "TEXCOORD_0": "VEC2", "TEXCOORD_1": "VEC2"}
        attributes = {
            n: glb.accessor(mesh[n], kinds.get(n, "VEC2" if n[:3] == "TEX" else "VEC4"), FLOAT)
            for n in names
        }
        if bones and mesh["links"]:
            gltf.links(glb, attributes, mesh["joints"], mesh["weights"], mesh["links"])
        key = mesh["material"]
        if key not in materials:
            materials[key] = _material(glb, key, slots.get(key, {}), images)
        indices = glb.accessor(mesh["indices"], "SCALAR", UINT, gltf.INDICES)
        primitives.append(
            {"attributes": attributes, "indices": indices, "material": materials[key]}
        )
    if not primitives:
        raise ValueError("no mesh in it")
    roots = [i for i, bone in enumerate(bones) if not 0 <= bone[1] < len(bones) or bone[1] == i]
    gltf.finish(glb, model.stem, primitives, roots, out)
    bare = sum(1 for key in materials if ALBEDO not in slots.get(key, {}))
    return (f"{bare} of {len(materials)} material(s) without a colour texture",) if bare else ()


MAIN = 100  # bones from which the biggest skeleton of a skin is its character


def label(model: Path, root: Path, main: bool = False) -> str:
    """A name that says where the model sits (hero, event, skin), since every skin reuses the
    same model ids: `<root>/<mode>/Heroes/Tracer/Skin/Overwatch/Posh/Models/..` gives
    "Tracer - Overwatch - Posh - <id>". A skin comes with dozens of props and effect shapes:
    its character is marked "(main)", which also lists it first."""
    parts = model.relative_to(root).parts
    above = parts[1 : parts.index("Models")] if "Models" in parts else parts[1:-2]
    stem = f"(main) {model.stem}" if main else model.stem
    return " - ".join([*(p for p in above if p not in ("Heroes", "Skin")), stem])


def _bones(model: Path) -> tuple[int, int]:
    """(bones, meshes) from the model's header; (0, 0) when it cannot be read."""
    try:
        with model.open("rb") as handle:
            src = _In(handle.read(4096))
        src.take("<HH"), src.text(), src.text()
        return src.take("<IHII")[1:3]
    except (OSError, struct.error, IndexError):
        return 0, 0


def mains(models: list[Path]) -> set[Path]:
    """Per skin (the folder holding `Models`), the model with the largest skeleton, when it is
    a character's (MAIN bones or more)."""
    skins: dict[Path, list[Path]] = {}
    for model in models:
        skins.setdefault(model.parent.parent, []).append(model)
    best = (max(group, key=_bones) for group in skins.values())
    return {model for model in best if _bones(model)[0] >= MAIN}


def convert_all(root: Path, each=map) -> tuple[int, list[str]]:
    """A .glb beside every .owmdl under root: (how many, what failed and why)."""

    models = sorted(root.rglob("*.owmdl"))
    main = mains(models)

    def one(model: Path) -> str:
        try:
            convert(model, model.with_name(label(model, root, model in main) + ".glb"))
        except (OSError, ValueError, struct.error, IndexError) as exc:
            return f"{model.name}: {exc}"
        return ""

    said = list(each(one, models))
    return said.count(""), [s for s in said if s]
