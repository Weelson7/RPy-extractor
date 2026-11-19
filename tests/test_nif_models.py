"""L1: Bethesda NIF models into .glb (decode.nif: viwo/plugins/bethesda/nifmodels.py over nif.py).
Properties over random NIFs the test lays out byte by byte, for each stream ViWo reads (Skyrim
83: NiTriShape with NiTriShapeData, NiSkinInstance and NiSkinData weights; Skyrim SE 100:
BSTriShape with full floats, NiSkinData transforms and weights in the vertices; Fallout 4 130:
BSTriShape with half floats, BSSkin::Instance and BSSkin::BoneData): every node is a glTF node
whose world transform is the NIF's turned from Z-up to Y-up; every vertex is there turned, with
its normal, UVs, colours, tangent along U; every triangle as stored; each shape's material is
named after its shader (else its colour map) and embeds that map as PNG when its .dds is in the
run; a skinned vertex lands where Gamebryo's skinning puts it in the file's pose; a lopsided
shape keeps its sides and its front faces; other versions and unread blocks are refused by
name, a NIF without a shape is counted, and nothing is half-written."""

import io
import math
import random
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.test_owmdl import open_glb
from viwo.contracts import gltf
from viwo.contracts.types import OutcomeKind
from viwo.plugins.bethesda import nifmodels

P, S = (0, 2, 1), (-1.0, 1.0, 1.0)  # glTF axis n is NIF axis P[n] times S[n]
DXT1 = struct.pack("<4sIIIIIII44x", b"DDS ", 124, 0x81007, 4, 4, 8, 0, 1)
DXT1 += struct.pack("<II4s20x", 32, 0x4, b"DXT1") + struct.pack("<I16x", 0x1000)


def sized(text: str) -> bytes:
    return struct.pack("<I", len(text)) + text.encode()


def nif_file(stream: int, blocks: list, strings: list, head=(0x14020007, 12)) -> bytes:
    kinds = list(dict.fromkeys(kind for kind, _ in blocks))
    out = b"Gamebryo File Format, Version 20.2.0.7\n"
    out += struct.pack("<IBIII", head[0], 1, head[1], len(blocks), stream)
    for text in [b"viwo", b"", b""] + [b""] * (stream >= 103):
        out += bytes([len(text) + 1]) + text + b"\0"
    out += struct.pack("<H", len(kinds)) + b"".join(sized(k) for k in kinds)
    out += b"".join(struct.pack("<H", kinds.index(k)) for k, _ in blocks)
    out += b"".join(struct.pack("<I", len(data)) for _, data in blocks)
    out += struct.pack("<II", len(strings), max(map(len, strings), default=0))
    return (
        out + b"".join(map(sized, strings)) + struct.pack("<I", 0) + b"".join(d for _, d in blocks)
    )


def unit(rng, n: int = 3) -> list[float]:
    v = [rng.gauss(0, 1) for _ in range(n)]
    return [x / math.sqrt(sum(y * y for y in v)) for x in v]


def place(rng, scale: float = 1.0) -> list[list[float]]:
    """A random rotation and translation (and scale) as a 3x4 matrix."""
    return gltf.matrix([rng.uniform(-5, 5) for _ in "xyz"], unit(rng, 4), [scale] * 3)


def pack_transform(m) -> bytes:
    """A 3x4 matrix of a rotation times a uniform scale as NiTransform: rotation, t, scale."""
    s = math.sqrt(sum(m[r][0] ** 2 for r in range(3)))
    rows = [m[r][c] / s for r in range(3) for c in range(3)]
    return struct.pack("<9f3ff", *rows, *(m[r][3] for r in range(3)), s)


def turned(v) -> list[float]:
    return [S[n] * v[P[n]] for n in range(3)]


def apply(m, v) -> list[float]:
    return [sum(m[r][c] * v[c] for c in range(3)) + m[r][3] for r in range(3)]


class Scene:
    """Blocks with their refs known before their bytes, and the string table."""

    def __init__(self, rng, stream: int) -> None:
        self.rng, self.stream, self.blocks, self.strings = rng, stream, [], []

    def ref(self, kind: str) -> int:
        self.blocks.append([kind, b""])
        return len(self.blocks) - 1

    def text(self, name: str) -> int:
        self.strings.append(name)
        return len(self.strings) - 1

    def av(self, name: str, local) -> bytes:
        s = pack_transform(local)
        return (
            struct.pack("<iIiI", self.text(name), 0, -1, 14)
            + s[36:48]
            + s[:36]
            + s[48:]
            + (struct.pack("<i", -1))
        )

    def bytes(self) -> bytes:
        return nif_file(self.stream, [tuple(b) for b in self.blocks], self.strings)


def vertices(rng, n: int, bones: int) -> list[dict]:
    out = []
    for _ in range(n):
        v = {"p": [rng.uniform(-30, 30) for _ in range(3)], "uv": [rng.random(), rng.random()]}
        v |= {
            "nb": [rng.randrange(256) for _ in range(9)],
            "c": [rng.randrange(256) for _ in range(4)],
        }
        used = rng.randint(1, 4)
        raw = [rng.random() + 0.05 for _ in range(used)] + [0.0] * (4 - used)
        v["w"] = [w / sum(raw) for w in raw]
        v["j"] = [rng.randrange(bones) if bones else 0 for _ in range(4)]
        out.append(v)
    return out


def half(values) -> list[float]:
    return list(struct.unpack(f"<{len(values)}e", struct.pack(f"<{len(values)}e", *values)))


def norm(values) -> list[float]:
    return [v / 127.5 - 1.0 for v in values]


def tri_data(sc: Scene, verts: list, tris: list, flags: int) -> bytes:
    """NiTriShapeData with normals, tangents (flags 0x1000), colours, one UV set."""
    n = len(verts)
    out = struct.pack("<iHBBB", 0, n, 0, 0, 1) + b"".join(
        struct.pack("<3f", *v["p"]) for v in verts
    )
    out += struct.pack("<HIB", flags, 0, 1)
    for k in (0, 3, 6) if flags & 0x1000 else (0,):  # normals, tangents (V), bitangents (U)
        out += b"".join(struct.pack("<3f", *norm(v["nb"][k : k + 3])) for v in verts)
    out += (
        bytes(16) + b"\1" + b"".join(struct.pack("<4f", *(c / 255 for c in v["c"])) for v in verts)
    )
    out += b"".join(struct.pack("<2f", *v["uv"]) for v in verts) + struct.pack("<Hi", 0, -1)
    flat = [i for t in tris for i in t]
    return (
        out
        + struct.pack("<HIB", len(tris), len(flat), 1)
        + struct.pack(f"<{len(flat)}H", *flat)
        + bytes(2)
    )


def bs_vertex(v: dict, full: bool) -> bytes:
    b = norm(v["nb"][6:9])  # the U direction: x after the position, y and z after the bytes
    out = struct.pack("<3ff", *v["p"], b[0]) if full else struct.pack("<3ee", *v["p"], b[0])
    out += struct.pack("<2e", *v["uv"]) + bytes(v["nb"][0:3] + v["nb"][7:8])
    out += bytes(v["nb"][3:6] + v["nb"][8:9]) + bytes(v["c"])
    return out + struct.pack("<4e4B", *v["w"], *v["j"])


def bs_shape(sc: Scene, av: bytes, verts: list, tris: list, refs: tuple) -> bytes:
    full = sc.stream == 100
    base = 16 if full else 8  # position (and the U direction's x); then 28 bytes
    stride = base + 28
    offsets = (base // 4) << 8 | (base + 4) // 4 << 16 | (base + 8) // 4 << 20
    offsets |= (base + 12) // 4 << 24 | (base + 16) // 4 << 28
    desc = stride // 4 | offsets | (0x1 | 0x2 | 0x8 | 0x10 | 0x20 | 0x40 | (0x400 * full)) << 44
    data = b"".join(bs_vertex(v, full) for v in verts)
    data += b"".join(struct.pack("<3H", *t) for t in tris)
    sizes = (struct.pack("<IHI", len(tris), len(verts), len(data)) if sc.stream >= 130
             else struct.pack("<HHI", len(tris), len(verts), len(data)))  # fmt: skip
    tail = struct.pack("<I", 0) if sc.stream == 100 else b""
    return av + bytes(16) + struct.pack("<3iQ", refs[0], refs[1], -1, desc) + sizes + data + tail


def shader(sc: Scene, kind: str) -> int:
    """A lighting shader whose texture set names tex0 (in the run; Fallout 4 names its .bgsm),
    or an effect shader whose source texture is tex1 (not in the run)."""
    ref, uv = sc.ref(kind), struct.pack("<4f", 0, 0, 1, 1)
    if kind == "BSEffectShaderProperty":
        sc.blocks[ref][1] = struct.pack("<iIi", -1, 0, -1) + bytes(8) + uv + sized("fx\\tex1.dds")
        return ref
    tset = sc.ref("BSShaderTextureSet")
    sc.blocks[tset][1] = struct.pack("<I", 9) + sized("textures\\armor\\tex0.dds") + sized("") * 8
    name = sc.text("materials\\armor\\iron.bgsm") if sc.stream == 130 else -1
    sc.blocks[ref][1] = struct.pack("<IiIi", 1, name, 0, -1) + bytes(8) + uv
    sc.blocks[ref][1] += struct.pack("<i", tset) + bytes(24)
    return ref


def skin_blocks(sc: Scene, root: int, bones: list, verts: list) -> tuple[int, dict]:
    """The skin of a shape: Fallout 4's BSSkin pair, else NiSkinInstance (or its dismember
    kind) with NiSkinData, which holds the weights only for Skyrim's NiTriShape."""
    rng, n = sc.rng, len(bones)
    s2b = [place(rng, rng.uniform(0.5, 2)) for _ in bones]
    if sc.stream == 130:
        inst, data = sc.ref("BSSkin::Instance"), sc.ref("BSSkin::BoneData")
        sc.blocks[inst][1] = struct.pack(f"<iiI{n}iI", root, data, n, *bones, 0)
        sc.blocks[data][1] = struct.pack("<I", n)
        sc.blocks[data][1] += b"".join(bytes(16) + pack_transform(m) for m in s2b)
        return inst, {"s2b": s2b, "to_skin": None}
    to_skin, has = place(rng, rng.uniform(0.5, 2)), sc.stream == 83
    inst = sc.ref(rng.choice(("NiSkinInstance", "BSDismemberSkinInstance")))
    data = sc.ref("NiSkinData")
    sc.blocks[inst][1] = struct.pack(f"<iiiI{n}i", data, -1, root, n, *bones) + bytes(4)
    body = pack_transform(to_skin) + struct.pack("<IB", n, has)
    for k, m in enumerate(s2b):
        pairs = [(i, sum(w for w, j in zip(v["w"], v["j"]) if j == k)) for i, v in enumerate(verts)]
        pairs = [(i, w) for i, w in pairs if w > 0 and has]
        body += pack_transform(m) + bytes(16) + struct.pack("<H", len(pairs))
        body += b"".join(struct.pack("<Hf", i, w) for i, w in pairs)
    sc.blocks[data][1] = body
    return inst, {"s2b": s2b, "to_skin": to_skin}


def add_shape(sc: Scene, model: dict, ref: int, s: int) -> None:
    rng, bones = sc.rng, model["bones"]
    verts = vertices(rng, rng.randint(3, 9), len(bones) if s == 0 else 0)
    tris = [tuple(rng.randrange(len(verts)) for _ in range(3)) for _ in range(rng.randint(1, 6))]
    shade = shader(sc, ("BSLightingShaderProperty", "BSEffectShaderProperty")[s])
    skin, rig = skin_blocks(sc, model["root"], bones, verts) if s == 0 else (-1, None)
    av = sc.av(f"shape{s}", model["local"][ref])
    if sc.stream == 83:
        data = sc.ref("NiTriShapeData")
        sc.blocks[data][1] = tri_data(sc, verts, tris, 0x1001)
        sc.blocks[ref][1] = av + struct.pack("<iiIiBii", data, skin, 0, -1, 0, shade, -1)
    else:
        sc.blocks[ref][1] = bs_shape(sc, av, verts, tris, (skin, shade))
    model["shapes"].append({"ref": ref, "verts": verts, "tris": tris, "rig": rig})


def make(rng, stream: int) -> tuple[Scene, dict]:
    """A root, a few bones under it, two shapes (the first skinned to the bones)."""
    sc = Scene(rng, stream)
    root = sc.ref("BSFadeNode")
    bones = [sc.ref("NiNode") for _ in range(rng.randint(1, 4))]
    parent = {b: rng.choice([root, *bones[:i]]) for i, b in enumerate(bones)}
    shapes = [sc.ref("NiTriShape" if stream == 83 else "BSTriShape") for _ in range(2)]
    parent |= {s: rng.choice([root, *bones]) for s in shapes}
    local = {r: place(rng, rng.uniform(0.5, 2)) for r in [root, *bones, *shapes]}
    model = {"parent": parent, "local": local, "root": root, "bones": bones, "shapes": []}
    for s, ref in enumerate(shapes):
        add_shape(sc, model, ref, s)
    for node in [root, *bones]:
        kids = [r for r, p in parent.items() if p == node]
        sc.blocks[node][1] = sc.av(f"node{node}", local[node])
        sc.blocks[node][1] += struct.pack(f"<I{len(kids)}iI", len(kids), *kids, 0)
    return sc, model


def nif_world(model: dict, ref: int) -> list:
    local = model["local"][ref]
    up = model["parent"].get(ref)
    return gltf.times(nif_world(model, up), local) if up is not None else local


def conj(m) -> list:
    return [[S[r] * S[c] * m[P[r]][P[c]] for c in range(3)] + [S[r] * m[P[r]][3]] for r in range(3)]


def stored(v: dict, stream: int) -> dict:
    """What the file holds of a vertex, as the reader must see it."""
    u = norm(v["nb"][6:9])
    u[0] = half(u[:1])[0] if stream == 130 else u[0]
    out = {"p": half(v["p"]) if stream == 130 else v["p"], "u": u, "v": norm(v["nb"][3:6])}
    out |= {"n": norm(v["nb"][0:3]), "uv": v["uv"] if stream == 83 else half(v["uv"])}
    weights = v["w"] if stream == 83 else half(v["w"])
    links = {}
    for w, j in zip(weights, v["j"]):
        links[j] = links.get(j, 0.0) + w
    total = sum(links.values())
    return out | {"links": {j: w / total for j, w in links.items() if w > 0}}


def glb_world(doc):
    nodes = doc["nodes"]
    parent = {k: i for i, node in enumerate(nodes) for k in node.get("children", ())}

    def world(i):
        m = nodes[i]["matrix"]
        local = [[m[4 * c + r] for c in range(4)] for r in range(3)]
        return gltf.times(world(parent[i]), local) if i in parent else local

    return world


def unit3(v) -> list[float]:
    size = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / size for x in v]


def cross(a, b) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def ctx():
    return SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


def png_of(dds: bytes) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    with Image.open(io.BytesIO(dds)) as image:
        image.save(out, "PNG")
    return out.getvalue()


def lay_out(root: Path, sc: Scene, dds: bytes) -> Path:
    for folder in ("nif", "dds"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "nif" / "armor.nif").write_bytes(sc.bytes())
    (root / "dds" / "tex0.dds").write_bytes(dds)
    return root / "nif" / "armor.nif"


class NifModelTests(unittest.TestCase):
    def close(self, got, want, tol: float = 1e-3) -> None:
        self.assertEqual(len(got), len(want))
        self.assertTrue(all(abs(a - b) < tol * max(1, abs(b)) for a, b in zip(got, want)))

    def test_every_stream_with_its_tree_rig_and_texture(self) -> None:
        rng = random.Random(40)
        for stream in (83, 100, 130):
            for case in range(8):
                with tempfile.TemporaryDirectory() as tmp:
                    sc, model = make(rng, stream)
                    dds = DXT1 + bytes(rng.randrange(256) for _ in range(8))
                    nif = lay_out(Path(tmp), sc, dds)
                    out = nifmodels.NifDecoder().decode(nif, Path(tmp) / "o", ctx())
                    self.assertEqual((out.kind, out.files, out.error), (OutcomeKind.OK, 1, ""))
                    self.assertIn("1 of 2 material(s) untextured", out.notes[0])
                    doc, blob, values = open_glb(Path(tmp) / "o" / "armor.glb")
                    self.check(model, doc, values, stream)
                    view = doc["bufferViews"][doc["images"][0]["bufferView"]]
                    png = blob[view["byteOffset"] : view["byteOffset"] + view["byteLength"]]
                    self.assertEqual((len(doc["images"]), png), (1, png_of(dds)), (stream, case))

    def check(self, model: dict, doc: dict, values, stream: int) -> None:
        index = {node["name"]: i for i, node in enumerate(doc["nodes"])}
        named = {s["ref"]: f"shape{k}" for k, s in enumerate(model["shapes"])}
        world = glb_world(doc)
        for ref in model["local"]:
            got, want = world(index[named.get(ref, f"node{ref}")]), conj(nif_world(model, ref))
            for r in range(3):
                self.close(got[r], want[r])
        names = ["materials\\armor\\iron.bgsm" if stream == 130 else "tex0", "tex1"]
        for s, shape in enumerate(model["shapes"]):
            node = doc["nodes"][index[f"shape{s}"]]
            prim = doc["meshes"][node["mesh"]]["primitives"][0]
            self.assertEqual(doc["materials"][prim["material"]]["name"], names[s])
            self.assertEqual(
                list(values(prim["indices"], "I")), [i for t in shape["tris"] for i in t]
            )
            self.vertex_data(prim["attributes"], shape, values, stream)
            if s == 0:
                self.skinning(model, shape, (doc, node, prim), values, stream)
            else:
                self.assertNotIn("skin", node)

    def vertex_data(self, attr: dict, shape: dict, values, stream: int) -> None:
        held = [stored(v, stream) for v in shape["verts"]]
        self.close(values(attr["POSITION"]), [x for h in held for x in turned(h["p"])])
        normals = [unit3(turned(h["n"])) for h in held]
        self.close(values(attr["NORMAL"]), [x for n in normals for x in n])
        self.close(values(attr["TEXCOORD_0"]), [x for h in held for x in h["uv"]])
        colours = [c / 255 for v in shape["verts"] for c in v["c"]]
        self.close(values(attr["_COLOR_0"]), colours, 2e-3 if stream == 83 else 1e-3)
        tangents = values(attr["TANGENT"])
        for k, (h, n) in enumerate(zip(held, normals)):
            t = unit3(turned(h["u"]))
            side = sum(a * b for a, b in zip(cross(n, t), turned(h["v"])))
            self.close(tangents[4 * k : 4 * k + 3], t)
            self.assertEqual(tangents[4 * k + 3], -1.0 if side < 0 else 1.0)

    def skinning(self, model: dict, shape: dict, found: tuple, values, stream: int) -> None:
        """Each vertex lands where Gamebryo skins it in the file's pose:
        shape * rootParentToSkin * rootParent^-1 * sum(w * bone * skinToBone) * v (Fallout 4:
        the sum alone), turned into glTF's axes."""
        doc, node, prim = found
        skin, world = doc["skins"][node["skin"]], glb_world(doc)
        binds = values(skin["inverseBindMatrices"])
        attr, rig = prim["attributes"], shape["rig"]
        joints, weights = values(attr["JOINTS_0"], "H"), values(attr["WEIGHTS_0"])
        positions = values(attr["POSITION"])
        lead = None
        if rig["to_skin"] is not None:
            lead = gltf.times(nif_world(model, shape["ref"]), rig["to_skin"])
            lead = gltf.times(lead, gltf.inverse(nif_world(model, model["root"])))
        for k, v in enumerate(shape["verts"]):
            held = stored(v, stream)
            want = [0.0, 0.0, 0.0]
            for j, w in held["links"].items():
                bone = gltf.times(nif_world(model, model["bones"][j]), rig["s2b"][j])
                want = [a + w * b for a, b in zip(want, apply(bone, held["p"]))]
            want = turned(apply(lead, want) if lead else want)
            got = [0.0, 0.0, 0.0]
            for slot in range(4 * k, 4 * k + 4):
                cols = binds[16 * joints[slot] : 16 * joints[slot] + 16]
                inverse = [[cols[4 * c + r] for c in range(4)] for r in range(3)]
                m = gltf.times(world(skin["joints"][joints[slot]]), inverse)
                p = apply(m, positions[3 * k : 3 * k + 3])
                got = [a + weights[slot] * b for a, b in zip(got, p)]
            self.close(got, want, 2e-3)

    def test_an_asymmetric_shape_keeps_its_sides_and_its_front(self) -> None:
        """NIF: forward +Y, right +X, up +Z (right-handed), front faces counter-clockwise, so
        cross(b - a, c - a) points out of the shape. In glTF the nose must face +Z, the model's
        left lie on +X (forward x up = right = -X) and every triangle still face outward."""
        sc = Scene(random.Random(41), 83)
        root, shape, data = sc.ref("BSFadeNode"), sc.ref("NiTriShape"), sc.ref("NiTriShapeData")
        nose, left, top, right = [0, 90, 0], [-40, 0, 0], [0, 0, 170], [40, 0, 0]
        corners = [nose, left, top, right]
        middle = [sum(c[k] for c in corners) / 4 for k in range(3)]
        tris = []
        for tri in ((0, 1, 2), (0, 2, 3), (0, 3, 1), (1, 3, 2)):
            a, b, c = (corners[i] for i in tri)
            out = [(a[k] + b[k] + c[k]) / 3 - middle[k] for k in range(3)]
            normal = cross([b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)])
            outward = sum(x * y for x, y in zip(normal, out)) > 0
            tris.append(tri if outward else (tri[0], tri[2], tri[1]))
        verts = [{"p": c, "uv": [0, 0], "nb": [128] * 9, "c": [255] * 4} for c in corners]
        same = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]
        sc.blocks[data][1] = tri_data(sc, verts, tris, 0x1)
        sc.blocks[shape][1] = sc.av("tip", same) + struct.pack(
            "<iiIiBii", data, -1, 0, -1, 0, -1, -1
        )
        sc.blocks[root][1] = sc.av("root", same) + struct.pack("<IiI", 1, shape, 0)
        with tempfile.TemporaryDirectory() as tmp:
            nif = lay_out(Path(tmp), sc, DXT1 + bytes(8))
            out = nifmodels.NifDecoder().decode(nif, Path(tmp) / "o", ctx())
            self.assertIn("1 of 1 material(s) untextured", out.notes[0])  # it has no shader
            doc, _, values = open_glb(Path(tmp) / "o" / "armor.glb")
        prim = doc["meshes"][0]["primitives"][0]
        p = values(prim["attributes"]["POSITION"])
        g = [list(p[3 * v : 3 * v + 3]) for v in range(4)]
        self.close(g[0], [0, 0, 90])  # the nose faces glTF's +Z
        self.close(g[1], [40, 0, 0])  # the model's left on +X
        self.close(g[2], [0, 170, 0])  # up is +Y
        got, centre = (
            list(values(prim["indices"], "I")),
            [sum(q[k] for q in g) / 4 for k in range(3)],
        )
        for t in range(4):
            a, b, c = (g[i] for i in got[3 * t : 3 * t + 3])
            out = [(a[k] + b[k] + c[k]) / 3 - centre[k] for k in range(3)]
            normal = cross([b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)])
            self.assertGreater(sum(x * y for x, y in zip(normal, out)), 0)

    def test_what_is_not_read_is_refused_by_name_and_counted(self) -> None:
        rng = random.Random(42)
        cases = {}
        sc, _ = make(rng, 83)
        good = sc.bytes()
        cases["oblivion.nif"] = nif_file(11, [("NiNode", bytes(64))], [], head=(0x14000005, 11))
        cases["fallout3.nif"] = nif_file(34, [("NiNode", bytes(64))], [], head=(0x14020007, 11))
        cases["strips.nif"] = nif_file(83, [("NiNode", bytes(80)), ("NiTriStrips", bytes(9))], [])
        sse = Scene(rng, 100)  # a skinned Skyrim SE shape: its vertices are in its partition
        top, body = sse.ref("BSFadeNode"), sse.ref("BSTriShape")
        sse.blocks[top][1] = sse.av("root", place(rng)) + struct.pack("<IiI", 1, body, 0)
        sse.blocks[body][1] = sse.av("body", place(rng)) + bytes(16)
        sse.blocks[body][1] += struct.pack("<3iQHHII", 5, -1, -1, 0, 10, 20, 0, 0)
        cases["partition.nif"] = sse.bytes()
        cases["cut.nif"] = good[: rng.randrange(60, len(good) // 2)]
        bare = Scene(rng, 83)
        bare.blocks.append(["NiNode", bare.av("root", place(rng)) + bytes(8)])
        cases["skeleton.nif"] = bare.bytes()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nif").mkdir()
            (root / "nif" / "good.nif").write_bytes(good)
            for name, raw in cases.items():
                (root / "nif" / name).write_bytes(raw)
            paths = sorted((root / "nif").iterdir())
            out = nifmodels.NifDecoder().decode_many(paths, root / "o", ctx())
            self.assertEqual((out.kind, out.files), (OutcomeKind.OK, 1))
            self.assertIn("7 NIF(s): 1 written as .glb, 1 without a shape", out.notes[0])
            self.assertTrue(out.error.startswith("5 NIF(s) refused, e.g. "), out.error)
            self.assertEqual([p.name for p in (root / "o").iterdir()], ["good.glb"])
            for name, why in (
                ("oblivion.nif", "user version 11"),
                ("fallout3.nif", "stream 34: 20.2.0.7, 12, stream 83/100/130 are read"),
                ("strips.nif", "NiTriStrips blocks are not read"),
                ("partition.nif", "keeps its vertices in its NiSkinPartition"),
            ):
                alone = nifmodels.NifDecoder().decode(root / "nif" / name, root / name, ctx())
                self.assertEqual(alone.kind, OutcomeKind.FAILED, name)
                self.assertIn(why, alone.error)


if __name__ == "__main__":
    unittest.main()
