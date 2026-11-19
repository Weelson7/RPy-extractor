"""L1: Source engine models into .glb (decode.mdl: viwo/plugins/source/models.py over studio.py).
Properties over random model triples the test lays out byte by byte (.mdl versions 44 to 49,
.vvd with and without fixups, .vtx with triangle lists, split lists and strips, the narrow and
CS:GO's wide strip groups), in the workspace's layout: the .vvd and .vtx of the model are found
by name and checksum among others of that name; every vertex of the default model of every body
part is in the .glb, turned from Source's Z-up axes to glTF's Y-up, with its UV and up to three
weights (unused slots weigh nothing); every triangle is there, wound the other way; each mesh
is a primitive named after its material through skin family 0; a material's $basetexture is
embedded as the PNG decode.vtf makes, the .vmt in a cdmaterials folder of the model first, and
what has none is counted; each joint's poseToBone undoes its place in the reference pose; a
known asymmetric shape keeps its sides and its front faces; a model without a mesh is counted,
a broken one refused with its reason, and nothing half-written."""

import math
import random
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.test_owmdl import open_glb
from tests.test_vtf import vtf
from viwo.contracts import gltf
from viwo.contracts.types import OutcomeKind
from viwo.plugins.source import models
from viwo.plugins.source import vtf as vtf_module

AXES = (1, 2, 0)  # glTF axis n is Source axis AXES[n]


class Out:
    def __init__(self, head: bytes, size: int) -> None:
        self.raw = bytearray(head) + bytes(size - len(head))

    def add(self, data: bytes) -> int:
        self.raw += b"\0" * (-len(self.raw) % 4)
        self.raw += data
        return len(self.raw) - len(data)

    def put(self, fmt: str, at: int, *values) -> None:
        struct.pack_into(fmt, self.raw, at, *values)


def unit(rng):
    q = [rng.gauss(0, 1) for _ in range(4)]
    return [v / math.sqrt(sum(x * x for x in q)) for v in q]


def group(rng, n: int) -> dict:
    """A strip group over a mesh of n vertices: a list, a list in two strips, a strip, or a
    list with no strip header at all."""
    verts = [rng.randrange(n) for _ in range(rng.randint(3, 10))]
    kind = rng.choice(("list", "two", "strip", "bare"))
    idx = [
        rng.randrange(len(verts))
        for _ in range(rng.randint(3, 9) if kind == "strip" else 3 * rng.randint(1, 5))
    ]
    cut = 3 * rng.randint(1, max(1, len(idx) // 3 - 1))  # no strip is empty
    two = [(cut, 0, 1), (len(idx) - cut, cut, 1)] if len(idx) > cut else [(len(idx), 0, 1)]
    strips = {"list": [(len(idx), 0, 1)], "two": two}
    return {
        "verts": verts,
        "idx": idx,
        "strips": strips.get(kind, [(len(idx), 0, 2)] * (kind == "strip")),
    }


def triangles(g: dict) -> list[int]:
    """The reference reading: mesh vertex ids in the file's winding."""
    out = []
    for n, first, flags in g["strips"] or [(len(g["idx"]), 0, 1)]:
        s = g["idx"][first : first + n]
        if not flags & 2:
            out += s
            continue
        for k in range(len(s) - 2):
            a, b, c = s[k : k + 3]
            if len({a, b, c}) == 3:
                out += [a, b, c] if k % 2 == 0 else [b, a, c]
    return [g["verts"][i] for i in out]


def new_mesh(rng) -> dict:
    count = rng.randint(3, 12)
    groups = [group(rng, count) for _ in range(rng.randint(1, 2))]
    return {"material": rng.randrange(3), "count": count, "groups": groups}


def drawn(m: dict) -> set[int]:
    """The textures of the default models' meshes that have a triangle."""
    meshes = [mesh for part in m["parts"] for mesh in part[0]]
    return {m["skins"][x["material"]] for x in meshes if any(map(triangles, x["groups"]))}


def make(rng, bones: int = 0) -> dict:
    m = {
        "version": rng.randint(44, 49),
        "checksum": rng.getrandbits(31),
        "wide": rng.random() < 0.5,
    }
    m["bones"] = []
    for i in range(bones or rng.randint(1, 5)):
        m["bones"].append(
            (f"bone{i}", rng.randint(-1, i - 1), [rng.uniform(-9, 9) for _ in "xyz"], unit(rng))
        )
    m["textures"] = ["tex0", "tex1", "tex2"]
    m["skins"] = rng.sample(range(3), 3)
    m["parts"] = [  # body parts of one or two models of one to three meshes
        [[new_mesh(rng) for _ in range(rng.randint(1, 3))] for _ in range(rng.randint(1, 2))]
        for _ in range(rng.randint(1, 3))
    ]
    m["vertices"] = []
    for part in m["parts"]:
        for model in part:
            for mesh in model:
                for _ in range(mesh["count"]):
                    used = rng.randint(1, 3)
                    slots = [rng.randrange(len(m["bones"])) if k < used else 250 for k in range(3)]
                    m["vertices"].append(
                        (
                            [rng.random() for _ in range(3)],
                            slots,
                            used,
                            [rng.uniform(-40, 40) for _ in range(8)],
                        )
                    )
    return m


def world(bones, i):
    _, parent, move, turn = bones[i]
    local = gltf.matrix(move, turn, [1, 1, 1])
    return gltf.times(world(bones, parent), local) if parent >= 0 else local


def write_mdl(m: dict) -> bytes:
    out = Out(struct.pack("<4sii", b"IDST", m["version"], m["checksum"]), 240)
    bone_at = out.add(bytes(216 * len(m["bones"])))
    for i, (name, parent, move, turn) in enumerate(m["bones"]):
        at = bone_at + 216 * i
        pose = [v for row in gltf.inverse(world(m["bones"], i)) for v in row]
        out.put("<ii", at, out.add(name.encode() + b"\0") - at, parent)
        out.put("<3f4f", at + 32, *move, *turn)
        out.put("<12f", at + 96, *pose)
    tex_at = out.add(bytes(64 * 3))
    for i, name in enumerate(m["textures"]):
        out.put("<i", tex_at + 64 * i, out.add(name.encode() + b"\0") - tex_at - 64 * i)
    dir_at = out.add(bytes(8))
    for i, folder in enumerate(("models\\props\\", "models\\more\\")):
        out.put("<i", dir_at + 4 * i, out.add(folder.encode() + b"\0"))
    skin_at = out.add(struct.pack("<6h", *m["skins"], 0, 1, 2))
    part_at, first = out.add(bytes(16 * len(m["parts"]))), 0
    for p, part in enumerate(m["parts"]):
        model_at = out.add(bytes(148 * len(part)))
        out.put("<iii", part_at + 16 * p + 4, len(part), 0, model_at - part_at - 16 * p)
        for k, meshes in enumerate(part):
            mesh_at, offset = out.add(bytes(116 * len(meshes))), 0
            total = sum(mesh["count"] for mesh in meshes)
            out.put(
                "<4i",
                model_at + 148 * k + 72,
                len(meshes),
                mesh_at - model_at - 148 * k,
                total,
                48 * first,
            )
            for j, mesh in enumerate(meshes):
                out.put("<4i", mesh_at + 116 * j, mesh["material"], 0, mesh["count"], offset)
                offset += mesh["count"]
            first += total
    out.put("<ii", 156, len(m["bones"]), bone_at)
    out.put("<4i", 204, 3, tex_at, 2, dir_at)
    out.put("<5i", 220, 3, 2, skin_at, len(m["parts"]), part_at)
    return bytes(out.raw)


def write_vvd(m: dict, rng, checksum: int) -> bytes:
    rows = [struct.pack("<3f3BB8f", *w, *b, u, *rest) for w, b, u, rest in m["vertices"]]
    head = struct.pack("<4siii", b"IDSV", 4, checksum, 1) + struct.pack("<8i", len(rows), *[0] * 7)
    out = Out(head, 64)
    if rng.random() < 0.5:  # the data stored in another order, fixups give LOD 0's
        cut = rng.randint(1, len(rows))
        data = out.add(b"".join(rows[cut:] + rows[:cut]))
        fix = [(0, len(rows) - cut, cut), (0, 0, len(rows) - cut)]
        out.put("<3i", 48, 2, out.add(b"".join(struct.pack("<3i", *f) for f in fix)), data)
    else:
        out.put("<3i", 48, 0, 0, out.add(b"".join(rows)))
    return bytes(out.raw)


def write_vtx(m: dict, checksum: int) -> bytes:
    wide = 8 * m["wide"]
    out = Out(struct.pack("<iiHHii", 7, 24, 53, 9, 3, checksum), 36)
    parts = out.add(bytes(8 * len(m["parts"])))
    out.put("<iiii", 20, 1, 0, len(m["parts"]), parts)
    for p, part in enumerate(m["parts"]):
        heads = out.add(bytes(8 * len(part)))
        out.put("<ii", parts + 8 * p, len(part), heads - parts - 8 * p)
        meshes = part[0]
        lod = out.add(struct.pack("<iif", len(meshes), 0, 0.0))
        out.put("<ii", heads, 1, lod - heads)
        mesh_at = out.add(bytes(9 * len(meshes) + 3))
        out.put("<i", lod + 4, mesh_at - lod)
        for k, mesh in enumerate(meshes):
            at = out.add(bytes((25 + wide) * len(mesh["groups"])))
            out.put("<ii", mesh_at + 9 * k, len(mesh["groups"]), at - mesh_at - 9 * k)
            for g, grp in enumerate(mesh["groups"]):
                base = at + (25 + wide) * g
                verts = out.add(
                    b"".join(struct.pack("<4BH3b", 0, 1, 2, 1, v, 0, 0, 0) for v in grp["verts"])
                )
                idx = out.add(struct.pack(f"<{len(grp['idx'])}H", *grp["idx"]))
                strips = out.add(
                    b"".join(
                        struct.pack("<4ihBii", n, f, 0, 0, 1, fl, 0, 0) + bytes(wide)
                        for n, f, fl in grp["strips"]
                    )
                )
                out.put(
                    "<6i",
                    base,
                    len(grp["verts"]),
                    verts - base,
                    len(grp["idx"]),
                    idx - base,
                    len(grp["strips"]),
                    strips - base,
                )
    return bytes(out.raw)


def lay_out(root: Path, m: dict, rng) -> Path:
    """The workspace's groups, with another model's files of the same name beside the right
    ones (COLLECT's `name__1`), in a random order."""
    for ext in ("mdl", "vvd", "vtx", "vmt", "vtf"):
        (root / ext).mkdir(parents=True, exist_ok=True)
    other = m["checksum"] + 1
    good, bad = rng.sample(["", "__1"], 2)
    (root / "vvd" / f"prop{good}.vvd").write_bytes(write_vvd(m, rng, m["checksum"]))
    (root / "vvd" / f"prop{bad}.vvd").write_bytes(write_vvd(m, rng, other))
    (root / "vtx" / f"prop.dx80{good}.vtx").write_bytes(write_vtx(m, m["checksum"]))
    (root / "vtx" / f"prop.dx90{bad}.vtx").write_bytes(write_vtx(m, other))
    (root / "mdl" / "prop__2.mdl").write_bytes(write_mdl(m))
    return root / "mdl" / "prop__2.mdl"


def textures(root: Path, rng) -> bytes:
    """tex0: two .vmt of that name, the one in a cdmaterials folder of the model names the
    texture; tex1: a .vmt with no $basetexture; tex2: none. The PNG tex0 must embed."""
    good = vtf(rng, 2, (4, 4), 1, 2, 1, bytes(range(48)))
    (root / "vtf" / "tex0_color.vtf").write_bytes(good)
    (root / "vtf" / "elsewhere.vtf").write_bytes(vtf(rng, 2, (4, 4), 1, 2, 1, bytes(48)))
    first, second = rng.sample(["", "__1"], 2)
    (root / "vmt" / f"tex0{first}.vmt").write_text(
        '"VertexLitGeneric"\n{\n "$basetexture" "models\\props\\tex0_color"\n}\n'
    )
    (root / "vmt" / f"tex0{second}.vmt").write_text(
        "VertexLitGeneric { $basetexture other/elsewhere }"
    )
    (root / "vmt" / "tex1.vmt").write_text('"UnlitGeneric" { "$color" "[1 1 1]" }')
    return vtf_module.to_png(good)


def ctx():
    return SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


class SourceModelTests(unittest.TestCase):
    def close(self, got, want) -> None:
        self.assertEqual(len(got), len(want))
        self.assertTrue(all(abs(a - b) < 1e-3 * max(1, abs(b)) for a, b in zip(got, want)))

    def test_lod_0_of_every_body_part_with_its_rig_and_texture(self) -> None:
        rng = random.Random(30)
        for case in range(25):
            with tempfile.TemporaryDirectory() as tmp:
                root, m = Path(tmp), make(rng)
                model, png = lay_out(root / "ws", m, rng), textures(root / "ws", rng)
                out = models.MdlDecoder().decode(model, root / "out", ctx())
                self.assertEqual((out.kind, out.files, out.error), (OutcomeKind.OK, 1, ""), case)
                doc, blob, values = open_glb(root / "out" / "prop__2.glb")
                self.check(m, doc, values)
                images = [doc["bufferViews"][i["bufferView"]] for i in doc.get("images", [])]
                kept = [blob[v["byteOffset"] : v["byteOffset"] + v["byteLength"]] for v in images]
                self.assertEqual(kept, [png] if 0 in drawn(m) else [])  # decode.vtf's PNG
                bare, used = len(drawn(m) - {0}), len(drawn(m))
                self.assertIn(f"{bare} of {used} material(s) untextured", out.notes[0])

    def tex(self, m, mesh) -> int:
        return m["skins"][mesh["material"]]

    def check(self, m: dict, doc: dict, values) -> None:
        kept, starts, at = [], [], 0
        for part in m["parts"]:
            starts.append(len(kept))
            count = sum(mesh["count"] for mesh in part[0])
            kept += m["vertices"][at : at + count]
            at += sum(mesh["count"] for model in part for mesh in model)
        prims = doc["meshes"][0]["primitives"]
        attr = prims[0]["attributes"]
        self.close(values(attr["POSITION"]), [v[3][AXES[k]] for v in kept for k in range(3)])
        self.close(values(attr["NORMAL"]), [v[3][3 + AXES[k]] for v in kept for k in range(3)])
        self.close(values(attr["TEXCOORD_0"]), [x for v in kept for x in v[3][6:8]])
        joints, weights = values(attr["JOINTS_0"], "H"), values(attr["WEIGHTS_0"])
        for n, (w, b, used, _) in enumerate(kept):
            got = {}
            for k in range(4):
                got[joints[4 * n + k]] = got.get(joints[4 * n + k], 0.0) + weights[4 * n + k]
            want = {}
            for k in range(used):
                want[b[k]] = want.get(b[k], 0.0) + w[k]
            for j in set(got) | set(want):
                self.assertAlmostEqual(got.get(j, 0.0), want.get(j, 0.0), 4)
        want_prims = []
        for part, start in zip(m["parts"], starts):
            offset = 0
            for mesh in part[0]:
                tris = [start + offset + v for g in mesh["groups"] for v in triangles(g)]
                if tris:
                    want_prims.append(
                        (
                            m["textures"][self.tex(m, mesh)],
                            [tris[t + d] for t in range(0, len(tris), 3) for d in (0, 2, 1)],
                        )
                    )
                offset += mesh["count"]
        got_prims = [
            (doc["materials"][p["material"]]["name"], list(values(p["indices"], "I")))
            for p in prims
        ]
        self.assertEqual(got_prims, want_prims)
        self.skeleton(m, doc, values)

    def skeleton(self, m, doc, values) -> None:
        nodes, inverse = doc["nodes"], values(doc["skins"][0]["inverseBindMatrices"])

        def placed(i):
            local = gltf.matrix(nodes[i]["translation"], nodes[i]["rotation"], [1, 1, 1])
            parent = next((p for p, n in enumerate(nodes) if i in n.get("children", ())), -1)
            return gltf.times(placed(parent), local) if parent >= 0 else local

        for i, bone in enumerate(m["bones"]):
            self.assertEqual(nodes[i]["name"], bone[0])
            src, got = world(m["bones"], i), placed(i)
            for r in range(3):
                self.close(got[r], [src[AXES[r]][AXES[c]] for c in range(3)] + [src[AXES[r]][3]])
            cols = inverse[16 * i : 16 * i + 16]
            one = gltf.times([[cols[4 * c + r] for c in range(4)] for r in range(3)], got)
            for r in range(3):
                self.close(one[r], [float(r == c) for c in range(4)])

    def test_an_asymmetric_shape_keeps_its_sides_and_its_front(self) -> None:
        """Source: forward +X, left +Y, up +Z (right-handed); front faces clockwise as a viewer
        sees them, so cross(b - a, c - a) points into the shape. In glTF the nose must face
        +Z, forward x up = right, and every triangle wind counter-clockwise (outward)."""
        rng = random.Random(31)
        m = make(rng, bones=1)
        nose, left, top, right = [90, 0, 0], [0, 40, 0], [0, 0, 170], [0, -40, 0]
        corners = [nose, left, top, right]
        m["parts"] = [
            [
                [
                    {
                        "material": 0,
                        "count": 4,
                        "groups": [{"verts": [0, 1, 2, 3], "idx": [], "strips": []}],
                    }
                ]
            ]
        ]
        m["vertices"] = [([1, 0, 0], [0, 0, 0], 1, [*c, 0, 0, 1, 0, 0]) for c in corners]
        centre = [sum(c[k] for c in corners) / 4 for k in range(3)]
        idx = []
        for tri in ((0, 1, 2), (0, 2, 3), (0, 3, 1), (1, 3, 2)):
            a, b, c = (corners[i] for i in tri)
            out = [(a[k] + b[k] + c[k]) / 3 - centre[k] for k in range(3)]
            normal = gltf_cross([b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)])
            idx += (
                list(tri)
                if sum(x * y for x, y in zip(normal, out)) < 0
                else [tri[0], tri[2], tri[1]]
            )
        m["parts"][0][0][0]["groups"][0]["idx"] = idx
        with tempfile.TemporaryDirectory() as tmp:
            model = lay_out(Path(tmp), m, rng)
            models.MdlDecoder().decode(model, Path(tmp) / "out", ctx())
            doc, _, values = open_glb(Path(tmp) / "out" / "prop__2.glb")
        part = doc["meshes"][0]["primitives"][0]
        p = values(part["attributes"]["POSITION"])
        g = [list(p[3 * v : 3 * v + 3]) for v in range(4)]
        self.close(g[0], [0, 0, 90])  # the nose faces glTF's +Z
        self.close(gltf_cross(g[0], g[2]), [-v * 90 * 170 / 40 for v in g[1]])  # right = -left
        middle = [sum(q[k] for q in g) / 4 for k in range(3)]
        got = list(values(part["indices"], "I"))
        for t in range(4):
            a, b, c = (g[i] for i in got[3 * t : 3 * t + 3])
            out = [(a[k] + b[k] + c[k]) / 3 - middle[k] for k in range(3)]
            normal = gltf_cross([b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)])
            self.assertGreater(sum(x * y for x, y in zip(normal, out)), 0)

    def test_what_cannot_be_converted_is_counted_and_said(self) -> None:
        rng = random.Random(32)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = lay_out(root, make(rng), rng)
            empty = make(rng)
            empty["parts"] = []
            (root / "mdl" / "anims.mdl").write_bytes(write_mdl(empty))
            (root / "mdl" / "lone.mdl").write_bytes(write_mdl(make(rng)))  # no .vvd, no .vtx
            old = bytearray(write_mdl(make(rng)))
            old[4:8] = struct.pack("<i", 37)
            (root / "mdl" / "old.mdl").write_bytes(bytes(old))
            cut = good.read_bytes()
            (root / "mdl" / "cut.mdl").write_bytes(cut[: rng.randrange(8, 240)])
            paths = sorted((root / "mdl").iterdir())
            out = models.MdlDecoder().decode_many(paths, root / "out", ctx())
            self.assertEqual((out.kind, out.files), (OutcomeKind.OK, 1))
            self.assertIn("5 model(s): 1 written as .glb, 1 without a mesh", out.notes[0])
            self.assertTrue(out.error.startswith("3 model(s) not converted, e.g. "), out.error)
            self.assertEqual([p.name for p in (root / "out").iterdir()], ["prop__2.glb"])
            alone = models.MdlDecoder().decode(root / "mdl" / "old.mdl", root / "o2", ctx())
            self.assertEqual(alone.kind, OutcomeKind.FAILED)
            self.assertIn("versions 44 to 49 are read", alone.error)


def gltf_cross(a, b) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


if __name__ == "__main__":
    unittest.main()
