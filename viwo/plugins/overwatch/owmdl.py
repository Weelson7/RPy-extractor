"""DataTool's models into files anything opens (doc 16.0c): an `.owmdl` with the materials of
its model look (`.owmat`) and their PNG textures becomes one self-contained `.glb` (glTF 2.0):
every submesh with its normals, tangents, UV sets and vertex colours, the skeleton in its
reference pose and every vertex's bone weights, the colour and normal textures embedded as
they were extracted (nothing re-encoded). The formats are read as DataTool writes them
(TankLib/ExportFormats/OverwatchModel.cs and DataTool/SaveLogic/Model.cs, MIT): positions come
Z-up with V flipped for Blender and go back to glTF's Y-up here; bones are already Y-up."""

import json
import math
import struct
import sys
from array import array
from pathlib import Path

ALBEDO, NORMAL = 2903569922, 378934698  # the texture slots glTF has a place for
FLOAT, USHORT, UINT = 5126, 5123, 5125


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


def _quaternion(euler: tuple) -> list[float]:
    """An XYZ Euler rotation (x applied first) as glTF's [x, y, z, w]."""
    (sx, cx), (sy, cy), (sz, cz) = ((math.sin(a / 2), math.cos(a / 2)) for a in euler)
    return [
        sx * cy * cz - cx * sy * sz,
        cx * sy * cz + sx * cy * sz,
        cx * cy * sz - sx * sy * cz,
        cx * cy * cz + sx * sy * sz,
    ]


def _matrix(translation, rotation, scale) -> list[list[float]]:
    x, y, z, w = rotation
    rows = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    return [[rows[r][c] * scale[c] for c in range(3)] + [translation[r]] for r in range(3)]


def _times(a, b) -> list[list[float]]:
    """Two 3x4 affine matrices multiplied (a then applied after b)."""
    return [
        [sum(a[r][k] * b[k][c] for k in range(3)) + (a[r][3] if c == 3 else 0) for c in range(4)]
        for r in range(3)
    ]


def _inverse(m) -> list[float]:
    """The inverse of a 3x4 affine matrix, as glTF's 16 column-major numbers."""
    (a, b, c), (d, e, f), (g, h, i) = (row[:3] for row in m)
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g) or 1.0
    inv = [
        [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
        [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
        [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
    ]
    move = [-sum(inv[r][k] * m[k][3] for k in range(3)) for r in range(3)]
    return [v for c in range(3) for v in (*(inv[r][c] for r in range(3)), 0.0)] + [*move, 1.0]


class Glb:
    """A glTF 2.0 binary being filled: one buffer, its views and accessors, the JSON beside."""

    def __init__(self) -> None:
        self.blob, self.doc = bytearray(), {"asset": {"version": "2.0", "generator": "ViWo"}}
        for key in ("bufferViews", "accessors", "images", "textures", "materials", "nodes"):
            self.doc[key] = []

    def view(self, data: bytes, target: int = 0) -> int:
        self.blob += b"\0" * (-len(self.blob) % 4)
        view = {"buffer": 0, "byteOffset": len(self.blob), "byteLength": len(data)}
        self.doc["bufferViews"].append(view | ({"target": target} if target else {}))
        self.blob += data
        return len(self.doc["bufferViews"]) - 1

    def accessor(self, values: array, kind: str, component: int, target: int = 34962) -> int:
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[kind]
        entry = {"bufferView": self.view(values.tobytes(), target), "componentType": component}
        entry |= {"count": len(values) // width, "type": kind}
        if kind == "VEC3" and target == 34962 and values:  # POSITION must say its bounds
            entry["min"] = [min(values[n::3]) for n in range(3)]
            entry["max"] = [max(values[n::3]) for n in range(3)]
        self.doc["accessors"].append(entry)
        return len(self.doc["accessors"]) - 1

    def save(self, path: Path) -> None:
        self.doc["buffers"] = [{"byteLength": len(self.blob)}]
        doc = {k: v for k, v in self.doc.items() if v or k == "asset"}
        text = json.dumps(doc, separators=(",", ":")).encode("utf-8")
        text += b" " * (-len(text) % 4)
        self.blob += b"\0" * (-len(self.blob) % 4)
        size = 12 + 8 + len(text) + 8 + len(self.blob)
        head = struct.pack("<4sII", b"glTF", 2, size) + struct.pack("<I4s", len(text), b"JSON")
        path.write_bytes(head + text + struct.pack("<I4s", len(self.blob), b"BIN\0") + self.blob)


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

    for i, (name, parent, move, scale, euler) in enumerate(bones):
        kids = [k for k, bone in enumerate(bones) if bone[1] == i and k != i]
        node = {"name": name, "translation": list(move), "scale": list(scale)}
        node |= {"rotation": _quaternion(euler)} | ({"children": kids} if kids else {})
        glb.doc["nodes"].append(node)
    inverse = array("f", (v for i in range(len(bones)) for v in _inverse(placed(i))))
    binds = glb.accessor(inverse, "MAT4", FLOAT, 0)
    glb.doc["skins"] = [{"joints": list(range(len(bones))), "inverseBindMatrices": binds}]


def _links(glb: Glb, mesh: dict, attributes: dict) -> None:
    """Bone indices and weights four at a time (JOINTS_0, JOINTS_1...): none is dropped. A
    slot DataTool left empty (0xFFFF) points at bone 0 with no weight."""
    links, count = mesh["links"], mesh["count"]
    for group in range(0, links, 4):
        joints, weights = array("H", bytes(8 * count)), array("f", bytes(16 * count))
        for k in range(group, min(group + 4, links)):
            column = mesh["joints"][k::links]
            used = array("B", (j != 0xFFFF for j in column))
            joints[k - group :: 4] = array("H", (j if u else 0 for j, u in zip(column, used)))
            kept = (w if u else 0.0 for w, u in zip(mesh["weights"][k::links], used))
            weights[k - group :: 4] = array("f", kept)
        attributes[f"JOINTS_{group // 4}"] = glb.accessor(joints, "VEC4", USHORT)
        attributes[f"WEIGHTS_{group // 4}"] = glb.accessor(weights, "VEC4", FLOAT)


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
            view = glb.view(file.read_bytes())
            glb.doc["images"].append(
                {"bufferView": view, "mimeType": "image/png", "name": file.name}
            )
            glb.doc["textures"].append({"source": len(glb.doc["images"]) - 1})
            images[file] = len(glb.doc["textures"]) - 1
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
            _links(glb, mesh, attributes)
        key = mesh["material"]
        if key not in materials:
            materials[key] = _material(glb, key, slots.get(key, {}), images)
        indices = glb.accessor(mesh["indices"], "SCALAR", UINT, 34963)
        primitives.append(
            {"attributes": attributes, "indices": indices, "material": materials[key]}
        )
    if not primitives:
        raise ValueError("no mesh in it")
    roots = [i for i, bone in enumerate(bones) if not 0 <= bone[1] < len(bones) or bone[1] == i]
    glb.doc["meshes"] = [{"name": model.stem, "primitives": primitives}]
    glb.doc["nodes"].append({"name": model.stem, "mesh": 0} | ({"skin": 0} if bones else {}))
    glb.doc |= {"scenes": [{"nodes": [*roots, len(glb.doc["nodes"]) - 1]}], "scene": 0}
    glb.save(out)
    bare = sum(1 for key in materials if ALBEDO not in slots.get(key, {}))
    return (f"{bare} of {len(materials)} material(s) without a colour texture",) if bare else ()


def label(model: Path, root: Path) -> str:
    """A name that says where the model sits (hero, event, skin), since every skin reuses the
    same model ids: `<root>/<mode>/Heroes/Tracer/Skin/Overwatch/Posh/Models/..` gives
    "Tracer - Overwatch - Posh - <id>"."""
    parts = model.relative_to(root).parts
    above = parts[1 : parts.index("Models")] if "Models" in parts else parts[1:-2]
    return " - ".join([*(p for p in above if p not in ("Heroes", "Skin")), model.stem])


def convert_all(root: Path, each=map) -> tuple[int, list[str]]:
    """A .glb beside every .owmdl under root: (how many, what failed and why)."""

    def one(model: Path) -> str:
        try:
            convert(model, model.with_name(label(model, root) + ".glb"))
        except (OSError, ValueError, struct.error, IndexError) as exc:
            return f"{model.name}: {exc}"
        return ""

    said = list(each(one, sorted(root.rglob("*.owmdl"))))
    return said.count(""), [s for s in said if s]
