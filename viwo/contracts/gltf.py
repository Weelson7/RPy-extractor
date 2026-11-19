"""glTF 2.0 binaries (`.glb`) for the plugins that turn a game's models into an open format
(doc 16.0c): one buffer with its views and accessors and the JSON beside it; affine matrices
as three rows of four (glTF wants columns: `columns`); a skin's joint nodes and inverse bind
matrices; bone links four to a set (JOINTS_n, WEIGHTS_n), made to sum to one when asked
(`weighed`); unit normals and tangents with their handedness from a stored V direction; PNG
images embedded as they are. The plugin reads its engine's format and converts its axes; this
module only writes."""

import json
import math
import struct
from array import array
from pathlib import Path

FLOAT, USHORT, UINT = 5126, 5123, 5125
VERTICES, INDICES = 34962, 34963  # buffer view targets


def quaternion(euler) -> list[float]:
    """An XYZ Euler rotation (x applied first) as glTF's [x, y, z, w]."""
    (sx, cx), (sy, cy), (sz, cz) = ((math.sin(a / 2), math.cos(a / 2)) for a in euler)
    return [
        sx * cy * cz - cx * sy * sz,
        cx * sy * cz + sx * cy * sz,
        cx * cy * sz - sx * sy * cz,
        cx * cy * cz + sx * sy * sz,
    ]


def matrix(translation, rotation, scale) -> list[list[float]]:
    """Translation, rotation [x, y, z, w] and scale as a 3x4 affine matrix."""
    x, y, z, w = rotation
    rows = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    return [[rows[r][c] * scale[c] for c in range(3)] + [translation[r]] for r in range(3)]


def times(a, b) -> list[list[float]]:
    """Two 3x4 affine matrices multiplied (a then applied after b)."""
    return [
        [sum(a[r][k] * b[k][c] for k in range(3)) + (a[r][3] if c == 3 else 0) for c in range(4)]
        for r in range(3)
    ]


def inverse(m) -> list[list[float]]:
    """The inverse of a 3x4 affine matrix (a singular one is divided by 1, not refused)."""
    (a, b, c), (d, e, f), (g, h, i) = (row[:3] for row in m)
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g) or 1.0
    inv = [
        [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
        [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
        [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
    ]
    move = [-sum(inv[r][k] * m[k][3] for k in range(3)) for r in range(3)]
    return [[*inv[r], move[r]] for r in range(3)]


def columns(m) -> list[float]:
    """A 3x4 affine matrix as glTF's 16 column-major numbers."""
    head = [v for c in range(3) for v in (*(m[r][c] for r in range(3)), 0.0)]
    return head + [m[0][3], m[1][3], m[2][3], 1.0]


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

    def accessor(self, values: array, kind: str, component: int, target: int = VERTICES) -> int:
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[kind]
        entry = {"bufferView": self.view(values.tobytes(), target), "componentType": component}
        entry |= {"count": len(values) // width, "type": kind}
        if kind == "VEC3" and target == VERTICES and values:  # POSITION must say its bounds
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


def texture(glb: Glb, png: bytes, name: str) -> int:
    """A PNG image embedded with its own bytes; the index of the texture that shows it."""
    view = glb.view(png)
    glb.doc["images"].append({"bufferView": view, "mimeType": "image/png", "name": name})
    glb.doc["textures"].append({"source": len(glb.doc["images"]) - 1})
    return len(glb.doc["textures"]) - 1


def skin(glb: Glb, nodes: list[dict], parents: list[int], binds: array) -> None:
    """One node per joint (their children from `parents`, -1 for a root) and the skin with
    their inverse bind matrices (16 column-major numbers each). The joints come first."""
    for i, node in enumerate(nodes):
        kids = [k for k, parent in enumerate(parents) if parent == i and k != i]
        glb.doc["nodes"].append(node | ({"children": kids} if kids else {}))
    matrices = glb.accessor(binds, "MAT4", FLOAT, 0)
    glb.doc["skins"] = [{"joints": list(range(len(nodes))), "inverseBindMatrices": matrices}]


def links(glb: Glb, attributes: dict, joints: array, weights: array, per_vertex: int) -> None:
    """Bone indices and weights (`per_vertex` of each per vertex) four at a time: JOINTS_0,
    WEIGHTS_0, JOINTS_1... none is dropped. A slot marked empty (0xFFFF) points at joint 0
    and weighs nothing."""
    count = len(joints) // per_vertex
    for group in range(0, per_vertex, 4):
        bones, weight = array("H", bytes(8 * count)), array("f", bytes(16 * count))
        for k in range(group, min(group + 4, per_vertex)):
            column = joints[k::per_vertex]
            used = array("B", (j != 0xFFFF for j in column))
            bones[k - group :: 4] = array("H", (j if u else 0 for j, u in zip(column, used)))
            kept = (w if u else 0.0 for w, u in zip(weights[k::per_vertex], used))
            weight[k - group :: 4] = array("f", kept)
        attributes[f"JOINTS_{group // 4}"] = glb.accessor(bones, "VEC4", USHORT)
        attributes[f"WEIGHTS_{group // 4}"] = glb.accessor(weight, "VEC4", FLOAT)


def unit(values: array) -> array:
    """Three-number vectors scaled to length one (a zero one stays as it is)."""
    for i in range(0, len(values), 3):
        size = math.sqrt(values[i] ** 2 + values[i + 1] ** 2 + values[i + 2] ** 2) or 1.0
        values[i], values[i + 1], values[i + 2] = (v / size for v in values[i : i + 3])
    return values


def tangents(normals: array, along_u: array, along_v: array) -> array:
    """TANGENT from a stored U direction (already in glTF's axes), w the side the stored V
    direction lies on (cross(N, T) . V), so a mirror or a swap upstream keeps its sign."""
    out = array("f", bytes(16 * (len(normals) // 3)))
    for k, i in enumerate(range(0, len(normals), 3)):
        (nx, ny, nz), (tx, ty, tz), v = normals[i : i + 3], along_u[i : i + 3], along_v[i : i + 3]
        side = (ny * tz - nz * ty) * v[0] + (nz * tx - nx * tz) * v[1] + (nx * ty - ny * tx) * v[2]
        out[4 * k : 4 * k + 4] = array("f", (tx, ty, tz, -1.0 if side < 0 else 1.0))
    return out


def weighed(joints, weights, per: int) -> tuple[array, array]:
    """Each vertex's links for `links`: a slot that weighs nothing is marked empty (0xFFFF),
    the others scaled to sum to one (the stored ones round: bytes, half floats)."""
    joints, weights = array("H", joints), array("f", weights)
    for i in range(0, len(joints), per):
        total = sum(w for w in weights[i : i + per] if w > 0) or 1.0
        for k in range(i, i + per):
            if weights[k] > 0:
                weights[k] /= total
            else:
                joints[k], weights[k] = 0xFFFF, 0.0
    return joints, weights


def finish(glb: Glb, name: str, primitives: list[dict], roots: list[int], out: Path) -> None:
    """One mesh of these primitives on one node (bound to the skin when there is one), the
    scene of the root joints and that node, written to `out`."""
    glb.doc["meshes"] = [{"name": name, "primitives": primitives}]
    skinned = {"skin": 0} if glb.doc.get("skins") else {}
    glb.doc["nodes"].append({"name": name, "mesh": 0} | skinned)
    glb.doc |= {"scenes": [{"nodes": [*roots, len(glb.doc["nodes"]) - 1]}], "scene": 0}
    glb.save(out)
