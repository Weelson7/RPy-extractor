"""UEFormat models (`.uemodel`, what UnrealAssetScout's Models mode writes through CUE4Parse) into
`.glb` beside them (doc 16.0c), on the shared writer (viwo/contracts/gltf.py). The pinned tool
has no glTF option, so ViWo reads the file itself, as CUE4Parse writes it at UEFormat version 10
(CUE4Parse-Conversion/Writers/UEFormat: FUEFormatHeader.cs, FDataAttribute*.cs, UEModel.cs, MIT):

  header   "UEFORMAT", identifier ("UEMODEL"), version (byte), object name, object path,
           compressed (bool) [+ "GZIP" or "ZSTD", inflated size, stored size], then the body
  string   int32 byte count + UTF-8          array   int32 count + items
  set      int32 count of attributes, each: name, int32 byte length, its bytes
  body     a set: LODS [name ("LOD0".. or "Nanite"), set], SKELETON set, COLLISION (not read)
  LOD      VERTICES [3f], NORMALS [binormal sign, 3f], TANGENTS [3f], TEXCOORDS [name, [2f]],
           INDICES (int32 count, int32 each, section after section), VERTEXCOLORS [name,
           [RGBA bytes]], MATERIALS [name, path, first index, triangles], WEIGHTS [bone u16,
           vertex i32, weight f], MORPHTARGETS (not read)
  SKELETON a set: BONES [name, parent i32, translation 3f, rotation xyzw 4f, scale 3f], ...

LOD 0 (the first LOD that is not the Nanite one) comes out whole: positions, normals, tangents,
every UV set, the vertex colour sets as data (`_COLOR_n`, never a tint), one primitive per
material section with its name, and for a skeletal mesh its bones in the reference pose with
every vertex's weights. Unreal is left-handed, Z up, in centimetres; glTF right-handed, Y up:
Y and Z swap, as Unreal's own glTF exporter does, the units stay. The swap is a mirror that
keeps what a viewer sees, so Unreal's front faces stay glTF's and the triangles keep their
order; a rotation (x, y, z, w) becomes (-x, -z, -y, w); the tangent's handedness turns with the
mirror. Materials are named, untextured (the Textures mode writes their PNG files). A file of
another version, or compressed with zstd on a Python without `compression.zstd`, is said."""

import gzip
import struct
import sys
import zlib
from array import array
from pathlib import Path

from viwo.contracts import gltf
from viwo.contracts.gltf import FLOAT, UINT, Glb

MAGIC, VERSION = b"UEFORMAT", 10
KINDS = {"POSITION": "VEC3", "NORMAL": "VEC3", "TANGENT": "VEC4"}


class _In:
    def __init__(self, data) -> None:
        self.data, self.at = memoryview(data), 0

    def take(self, fmt: str) -> tuple:
        values = struct.unpack_from(fmt, self.data, self.at)
        self.at += struct.calcsize(fmt)
        return values

    def int(self) -> int:
        return self.take("<i")[0]

    def size(self) -> int:
        size = self.int()
        if not 0 <= size <= len(self.data) - self.at:
            raise ValueError("the file ends inside its data")
        return size

    def text(self) -> str:
        size = self.size()
        self.at += size
        return bytes(self.data[self.at - size : self.at]).decode("utf-8", "replace")

    def numbers(self, kind: str, count: int) -> array:
        out = array(kind)
        out.frombytes(self.data[self.at : self.at + out.itemsize * count])
        self.at += out.itemsize * count
        if len(out) != count:
            raise ValueError("the file ends inside its data")
        if sys.byteorder == "big":
            out.byteswap()
        return out

    def attributes(self) -> dict:
        """An attribute set: name -> its bytes."""
        out = {}
        for _ in range(self.int()):
            name = self.text()
            size = self.size()
            out[name], self.at = self.data[self.at : self.at + size], self.at + size
        return out


def body(data: bytes) -> memoryview:
    """The model's attribute set, inflated."""
    src = _In(data)
    if bytes(src.data[:8]) != MAGIC:
        raise ValueError("not a UEFormat file")
    src.at = 8
    kind, version = src.text(), src.take("<B")[0]
    if kind != "UEMODEL" or version != VERSION:
        raise ValueError(f"{kind} version {version}: only UEMODEL version {VERSION} is read")
    _name, _path = src.text(), src.text()
    if not src.take("<?")[0]:
        return src.data[src.at :]
    method, _, _ = src.text(), src.int(), src.int()
    stored = bytes(src.data[src.at :])
    if method == "GZIP":
        return memoryview(gzip.decompress(stored))
    if method != "ZSTD":
        raise ValueError(f"compressed with {method!r}")
    try:
        from compression import zstd  # Python 3.14 and later
    except ImportError:
        raise ValueError("zstd-compressed: this Python cannot inflate it (3.14 can)") from None
    try:
        return memoryview(zstd.decompress(stored))
    except zstd.ZstdError as exc:
        raise ValueError(f"zstd: {exc}") from None


def _swap(values: array, width: int) -> array:
    """(x, y, z[, w]) in Unreal's axes as glTF's: (x, z, y[, w])."""
    out = array("f", values)
    out[1::width], out[2::width] = values[2::width], values[1::width]
    return out


def _sets(blob, width: int, count: int, kind: str = "f") -> list[array]:
    """The named sets of one channel (UVs, colours), each `count` items of `width` numbers."""
    src, out = _In(blob), []
    for _ in range(src.int()):
        src.text()
        if src.int() != count:
            raise ValueError("a UV or colour set does not hold every vertex")
        out.append(src.numbers(kind, width * count))
    return out


def _channels(parts: dict) -> dict:
    """glTF attribute name -> its numbers."""
    src = _In(parts["VERTICES"])
    count = src.int()
    out = {"POSITION": _swap(src.numbers("f", 3 * count), 3)}
    signs = array("f")
    if "NORMALS" in parts and _In(parts["NORMALS"]).int() == count:
        packed = _In(parts["NORMALS"][4:]).numbers("f", 4 * count)
        signs = packed[0::4]
        normals = array("f", bytes(12 * count))
        normals[0::3], normals[1::3], normals[2::3] = packed[1::4], packed[3::4], packed[2::4]
        out["NORMAL"] = normals
    if signs and "TANGENTS" in parts and _In(parts["TANGENTS"]).int() == count:
        tangents = _swap(_In(parts["TANGENTS"][4:]).numbers("f", 3 * count), 3)
        out["TANGENT"] = array("f", bytes(16 * count))
        for n in range(3):
            out["TANGENT"][n::4] = tangents[n::3]
        out["TANGENT"][3::4] = array("f", (1.0 if s < 0 else -1.0 for s in signs))  # mirrored
    for n, uv in enumerate(_sets(parts.get("TEXCOORDS", b"\0" * 4), 2, count)):
        out[f"TEXCOORD_{n}"] = uv
    for n, rgba in enumerate(_sets(parts.get("VERTEXCOLORS", b"\0" * 4), 4, count, "B")):
        out[f"_COLOR_{n}"] = array("f", (v / 255.0 for v in rgba))
    return out


def _bones(skeleton) -> list:
    """[(name, parent, translation, rotation, scale)] in glTF's axes, parents before children."""
    blob = _In(skeleton).attributes().get("BONES", b"\0" * 4)
    src, out = _In(blob), []
    for i in range(src.int()):
        name, parent = src.text(), src.int()
        (x, y, z), (a, b, c, w), (u, v, s) = src.take("<3f"), src.take("<4f"), src.take("<3f")
        out.append((name, parent if 0 <= parent < i else -1, [x, z, y], [-a, -c, -b, w], [u, s, v]))
    return out


def _skeleton(glb: Glb, bones: list) -> list[int]:
    """One node per bone in the reference pose, the skin, the root joints."""
    world = []
    for _, parent, move, turn, scale in bones:
        local = gltf.matrix(move, turn, scale)
        world.append(gltf.times(world[parent], local) if parent >= 0 else local)
    nodes = [{"name": n, "translation": t, "rotation": r, "scale": s} for n, _, t, r, s in bones]
    binds = array("f", (v for m in world for v in gltf.columns(gltf.inverse(m))))
    gltf.skin(glb, nodes, [bone[1] for bone in bones], binds)
    return [i for i, bone in enumerate(bones) if bone[1] < 0]


def _weights(blob, count: int, bones: int) -> tuple[array, array, int]:
    """Every vertex's (bone, weight) pairs, as many slots a vertex as the most any has."""
    src, links = _In(blob), {}
    for _ in range(src.int()):
        bone, vertex, weight = src.take("<Hif")
        if not (0 <= vertex < count and bone < bones):
            raise ValueError(f"a weight points at vertex {vertex} or bone {bone}")
        links.setdefault(vertex, []).append((bone, weight))
    width = max(map(len, links.values()), default=1)
    joints, weights = array("H", [0xFFFF]) * (width * count), array("f", bytes(4 * width * count))
    for vertex, pairs in links.items():
        for k, (bone, weight) in enumerate(pairs):
            joints[vertex * width + k], weights[vertex * width + k] = bone, weight
    return joints, weights, width


def _primitives(glb: Glb, parts: dict, attributes: dict, count: int) -> list[dict]:
    """One primitive per material section, its triangles as Unreal winds them."""
    src = _In(parts["INDICES"])
    indices = src.numbers("I", src.int())
    if indices and max(indices) >= count:
        raise ValueError(f"an index points at vertex {max(indices)} of {count}")
    src, out = _In(parts.get("MATERIALS", b"\0" * 4)), []
    sections = [(src.text(), src.text(), *src.take("<ii")) for _ in range(src.int())]
    for name, path, first, faces in sections or [("", "", 0, len(indices) // 3)]:
        chosen = indices[first : first + 3 * faces]
        if not chosen:
            continue
        glb.doc["materials"].append({"name": name or Path(path).name or "material"})
        at = glb.accessor(chosen, "SCALAR", UINT, gltf.INDICES)
        part = {"indices": at, "material": len(glb.doc["materials"]) - 1}
        out.append({"attributes": attributes} | part)
    return out


def convert(model: Path, out: Path) -> bool:
    """model (.uemodel) -> out (.glb); False when it holds no mesh (a skeleton alone)."""
    root = _In(body(model.read_bytes())).attributes()
    if "LODS" not in root:
        return False
    src = _In(root["LODS"])
    lods = [(src.text(), src.attributes()) for _ in range(src.int())]
    parts = next((p for n, p in lods if n != "Nanite"), lods[0][1] if lods else None)
    if parts is None or "VERTICES" not in parts or "INDICES" not in parts:
        return False
    glb, channels = Glb(), _channels(parts)
    count = len(channels["POSITION"]) // 3
    attributes = {
        k: glb.accessor(v, KINDS.get(k, "VEC2" if k[:3] == "TEX" else "VEC4"), FLOAT)
        for k, v in channels.items()
    }
    bones = _bones(root["SKELETON"]) if "SKELETON" in root and "WEIGHTS" in parts else []
    roots = _skeleton(glb, bones) if bones else []
    if bones:
        gltf.links(glb, attributes, *_weights(parts["WEIGHTS"], count, len(bones)))
    primitives = _primitives(glb, parts, attributes, count)
    if not primitives:
        raise ValueError("no triangles")
    gltf.finish(glb, model.stem, primitives, roots, out)
    return True


def convert_all(root: Path, each=map) -> tuple[int, list[str], int]:
    """A .glb beside every .uemodel under root: (written, what failed and why, without mesh)."""

    def one(model: Path) -> str:
        try:
            return "" if convert(model, model.with_suffix(".glb")) else "-"
        except (OSError, ValueError, struct.error, IndexError, EOFError, zlib.error) as exc:
            return f"{model.name}: {exc}"

    said = list(each(one, sorted(root.rglob("*.uemodel"))))
    return said.count(""), [s for s in said if s not in ("", "-")], said.count("-")
