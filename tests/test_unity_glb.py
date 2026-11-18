"""L1: Unity meshes as .glb (viwo/plugins/unity/meshes.py over viwo/contracts/gltf.py).
Properties over random meshes given the way UnityPy's MeshHandler gives them: every vertex,
normal, tangent, UV set and colour is in the .glb with X mirrored (Unity is left-handed), V
turned and a tangent's handedness turned; every triangle of every sub-mesh is there, wound the
other way, with 16-bit indices while they fit and 32-bit past them; a known asymmetric shape
keeps its right, its up, its forward and its front faces; every bone weight survives; each
joint sits where its bind pose says, under the parent its renderer gives; the main texture is
embedded; a mesh that cannot be converted is counted and its first reason said."""

import io
import random
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tests.test_owmdl import open_glb
from viwo.contracts import gltf
from viwo.plugins.unity import meshes

NS = types.SimpleNamespace


def handler(rng: random.Random, count: int, subs: int, bones: int = 0) -> NS:
    """A processed MeshHandler: its channels as lists of tuples, its triangles per sub-mesh."""
    f = lambda n: tuple(rng.uniform(-5, 5) for _ in range(n))  # noqa: E731
    rows = lambda n: [f(n) for _ in range(count)]  # noqa: E731
    h = NS(m_VertexCount=count, m_Vertices=rows(3), m_Normals=rows(3), m_Tangents=rows(4))
    h.m_Colors = [tuple(rng.randrange(256) for _ in range(4)) for _ in range(count)]
    for n in range(8):
        setattr(h, f"m_UV{n}", rows(rng.choice((2, 3))) if n < 3 else None)
    many = rng.randint(0 if subs > 1 else 1, 9)  # an empty sub-mesh beside others
    tris = [[tuple(rng.randrange(count) for _ in range(3)) for _ in range(many)]]
    tris += [[tuple(rng.randrange(count) for _ in range(3))] for _ in range(subs - 1)]
    h.get_triangles = lambda: tris
    per = rng.choice((1, 2, 3, 4))
    h.m_BoneIndices = h.m_BoneWeights = None
    if bones:
        h.m_BoneIndices = [tuple(rng.randrange(bones) for _ in range(per)) for _ in range(count)]
        h.m_BoneWeights = rows(per) if per > 1 else None
    return h


def matrix4(m) -> NS:
    """A Unity Matrix4x4f (eRC) from a 3x4 affine matrix."""
    full = [*m, [0.0, 0.0, 0.0, 1.0]]
    return NS(**{f"e{r}{c}": full[r][c] for r in range(4) for c in range(4)})


def rotation(rng: random.Random) -> list[float]:
    q = [rng.gauss(0, 1) for _ in range(4)]
    size = sum(v * v for v in q) ** 0.5
    return [v / size for v in q]


class Pointer:
    """A UnityPy PPtr to an object in a loaded file."""

    def __init__(self, path_id: int, target=None, file: str = "level0") -> None:
        self.path_id, self.target = path_id, target
        self.reader = NS(assets_file=NS(name=file), path_id=path_id, parse_as_object=self.get)

    def get(self):
        return self.target

    def deref(self):
        if self.target is None:
            raise FileNotFoundError("not loaded")
        return self.reader

    def deref_parse_as_object(self):
        return self.deref().parse_as_object()

    def __bool__(self) -> bool:
        return self.path_id != 0


def rig(rng: random.Random, bones: int) -> tuple[list, list, list]:
    """Bone transforms (a random tree), their world matrices (Unity space), bind poses."""
    parents = [rng.randrange(i) if i else -1 for i in range(bones)]
    world, ptrs = [], []
    for i, parent in enumerate(parents):
        local = gltf.matrix([rng.uniform(-2, 2) for _ in range(3)], rotation(rng), [1, 1, 1])
        world.append(gltf.times(world[parent], local) if parent >= 0 else local)
        father = ptrs[parent] if parent >= 0 else Pointer(0)
        bone = NS(m_Father=father, m_GameObject=Pointer(900 + i, NS(m_Name=f"bone{i}")))
        ptrs.append(Pointer(100 + i, bone))
    return ptrs, parents, [matrix4(gltf.inverse(w)) for w in world]


def mesh_data(h: NS, binds: list = (), base: int = 0) -> NS:
    subs = [NS(baseVertex=base if n == 0 else 0) for n in range(len(h.get_triangles()))]
    hashes = [0xABCD0000 + i for i in range(len(binds))]
    return NS(m_Name="rock", m_SubMeshes=subs, m_BindPose=list(binds), m_BoneNameHashes=hashes)


def column(values, i: int) -> list[list[float]]:
    cols = values[i * 16 : i * 16 + 16]
    return [[cols[c * 4 + r] for c in range(4)] for r in range(3)]


class UnityGlbTests(unittest.TestCase):
    def close(self, got, want, places: float = 1e-3) -> None:
        self.assertEqual(len(got), len(want))
        self.assertTrue(all(abs(a - b) < places for a, b in zip(got, want)), (got, want))

    def convert(self, h, data, drawn=None) -> tuple:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "m.glb"
            said = meshes.convert(h, data, drawn, out, {})
            return said, *open_glb(out)

    def test_every_vertex_and_triangle_mirrored_into_gltf(self) -> None:
        rng = random.Random(80)
        for case in range(30):
            count = 70_000 if case == 29 else rng.choice((3, rng.randint(4, 60)))
            h = handler(rng, count, rng.randint(1, 3))
            first = h.get_triangles()[0]
            base = rng.randrange(2) * (count // 2) if count <= 0xFFFF else 0
            first[:] = [tuple(v % (count - base) for v in t) for t in first]
            if count > 0xFFFF:  # one index past 16 bits
                first.append((count - 1, 0, 1))
            _, doc, _, values = self.convert(h, mesh_data(h, base=base))
            prims = doc["meshes"][0]["primitives"]
            at = prims[0]["attributes"]
            x, y, z = ([p[n] for p in h.m_Vertices] for n in range(3))
            self.close(
                values(at["POSITION"]), [v for p in zip(x, y, z) for v in (-p[0], p[1], p[2])]
            )
            self.close(values(at["NORMAL"])[0::3], [-n[0] for n in h.m_Normals])
            tangent = values(at["TANGENT"])
            self.close(tangent[0::4], [-t[0] for t in h.m_Tangents])
            self.close(tangent[3::4], [-t[3] for t in h.m_Tangents])  # handedness turns
            self.close(values(at["_COLOR_0"]), [c / 255 for row in h.m_Colors for c in row])
            self.assertNotIn("COLOR_0", at)  # data, never a tint
            for n in range(3):
                uv, rows = values(at[f"TEXCOORD_{n}"]), getattr(h, f"m_UV{n}")
                self.close(uv[1::2], [1 - r[1] for r in rows])
                self.assertEqual(f"_UV{n}" in at, len(rows[0]) == 3)  # a 3-number set kept whole
            self.triangles(h, doc, values, prims, base)

    def triangles(self, h, doc, values, prims, base) -> None:
        wanted = [(t, b) for t, b in zip(h.get_triangles(), [base, 0, 0]) if t]
        self.assertEqual(len(prims), len(wanted))
        for part, (tris, shift) in zip(prims, wanted):
            accessor = doc["accessors"][part["indices"]]
            want = [shift + i for a, b, c in tris for i in (a, c, b)]
            small = accessor["componentType"] == gltf.USHORT
            self.assertEqual(small, max(want) < 0xFFFF)  # 32-bit only when needed
            self.assertEqual(list(values(part["indices"], "H" if small else "I")), want)

    def test_an_asymmetric_shape_keeps_its_sides_and_its_front_faces(self) -> None:
        """A tetrahedron with its right (+X), up (+Y) and forward (+Z) arms of different length,
        faces wound as Unity draws their fronts (clockwise seen from outside)."""
        points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 3.0)]
        tris = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
        h = NS(m_VertexCount=4, m_Vertices=points, m_Normals=None, m_Tangents=None, m_Colors=None)
        h.m_BoneIndices, h.get_triangles = None, lambda: [tris]
        for n in range(8):
            setattr(h, f"m_UV{n}", None)
        _, doc, _, values = self.convert(h, mesh_data(h))
        pos = values(doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"])
        at = [pos[i * 3 : i * 3 + 3] for i in range(4)]
        self.assertEqual([list(p) for p in at[1:]], [[-1, 0, 0], [0, 2, 0], [0, 0, 3]])
        centre = [sum(p[k] for p in at) / 4 for k in range(3)]
        flat = list(values(doc["meshes"][0]["primitives"][0]["indices"], "H"))
        for a, b, c in zip(flat[0::3], flat[1::3], flat[2::3]):  # glTF: counter-clockwise front
            u, v = ([at[q][k] - at[a][k] for k in range(3)] for q in (b, c))
            normal = [
                u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0],
            ]
            middle = [(at[a][k] + at[b][k] + at[c][k]) / 3 - centre[k] for k in range(3)]
            self.assertGreater(sum(n * m for n, m in zip(normal, middle)), 0)  # faces outwards

    def test_skin_weights_bind_poses_and_bone_tree_survive(self) -> None:
        rng = random.Random(81)
        for case in range(20):
            count, bones = rng.randint(3, 30), rng.randint(1, 7)
            h = handler(rng, count, 1, bones)
            ptrs, parents, binds = rig(rng, bones)
            renderer = (ptrs, []) if case % 4 else None  # no renderer: names by hash, flat
            (_, hashed), doc, _, values = self.convert(h, mesh_data(h, binds), renderer)
            self.assertEqual(hashed, renderer is None)  # counted: bones named by hash
            at = doc["meshes"][0]["primitives"][0]["attributes"]
            self.weights(h, at, values)
            self.assertEqual(doc["skins"][0]["joints"], list(range(bones)))
            inverse = values(doc["skins"][0]["inverseBindMatrices"])
            nodes = doc["nodes"][:bones]
            parent = {k: i for i, node in enumerate(nodes) for k in node.get("children", [])}
            want = parents if renderer else [-1] * bones
            self.assertEqual([parent.get(i, -1) for i in range(bones)], want)
            names = [f"bone{i}" if renderer else f"bone_{0xABCD0000 + i:08X}" for i in range(bones)]
            self.assertEqual([n["name"] for n in nodes], names)

            def world(i: int):
                local = column(nodes[i]["matrix"], 0)
                return gltf.times(world(parent[i]), local) if i in parent else local

            for i in range(bones):
                one = gltf.times(column(inverse, i), world(i))
                for r in range(3):
                    self.close(one[r], [float(r == c) for c in range(4)])
                flip = [-1, 1, 1, 1]  # the bind pose mirrored on both sides of X
                want = [
                    [getattr(binds[i], f"e{r}{c}") * flip[r] * flip[c] for c in range(4)]
                    for r in range(3)
                ]
                self.close(sum(column(inverse, i), []), sum(want, []))
        h = handler(rng, 5, 1)  # bind poses without weights: no skin glTF would refuse
        (_, hashed), doc, _, _ = self.convert(h, mesh_data(h, rig(rng, 2)[2]))
        self.assertEqual((hashed, "skins" in doc), (False, False))

    def weights(self, h, at, values) -> None:
        per = len(h.m_BoneIndices[0])
        sets = -(-per // 4)
        self.assertEqual(sum(k.startswith("JOINTS_") for k in at), sets)
        for vertex in range(h.m_VertexCount):
            want, got = {}, {}
            given = h.m_BoneWeights[vertex] if h.m_BoneWeights else (1.0,)
            for joint, weight in zip(h.m_BoneIndices[vertex], given):
                want[joint] = want.get(joint, 0.0) + weight
            for group in range(sets):
                joints = values(at[f"JOINTS_{group}"], "H")[vertex * 4 : vertex * 4 + 4]
                for joint, w in zip(
                    joints, values(at[f"WEIGHTS_{group}"])[vertex * 4 : vertex * 4 + 4]
                ):
                    got[joint] = got.get(joint, 0.0) + w
            for joint in set(want) | set(got):
                self.assertAlmostEqual(got.get(joint, 0.0), want.get(joint, 0.0), 3)

    def test_main_texture_embedded_and_renderers_found(self) -> None:
        from PIL import Image

        rng = random.Random(82)
        h = handler(rng, 12, 2)
        h.get_triangles = lambda: [[(0, 1, 2)], [(3, 4, 5)]]
        image = Image.new("RGBA", (2, 3), (9, 8, 7, 255))
        texture = Pointer(50, NS(m_Name="skin", image=image))
        sheet = NS(
            m_TexEnvs=[
                (NS(name="_BumpMap"), NS(m_Texture=Pointer(0))),
                ("_MainTex", NS(m_Texture=texture)),
            ]
        )
        material = Pointer(40, NS(m_SavedProperties=sheet))
        mesh, owner = Pointer(30, "mesh"), Pointer(20, "go")
        objects = [
            NS(
                type=NS(name="MeshFilter"),
                parse_as_object=lambda: NS(m_GameObject=owner, m_Mesh=mesh),
            ),
            NS(
                type=NS(name="MeshRenderer"),
                parse_as_object=lambda: NS(m_GameObject=owner, m_Materials=[material]),
            ),
            NS(
                type=NS(name="MeshFilter"), parse_as_object=lambda: NS(m_GameObject=Pointer(0))
            ),  # broken
        ]
        found = meshes.renderers(NS(objects=objects))
        self.assertEqual(found, {("level0", 30): ([], [material])})
        (textured, _), doc, blob, _ = self.convert(h, mesh_data(h), found[("level0", 30)])
        self.assertTrue(textured)
        parts = doc["meshes"][0]["primitives"]
        self.assertEqual([p.get("material") for p in parts], [0, None])  # one material given
        view = doc["bufferViews"][doc["images"][0]["bufferView"]]
        png = blob[view["byteOffset"] : view["byteOffset"] + view["byteLength"]]
        self.assertEqual(Image.open(io.BytesIO(png)).getpixel((1, 2)), (9, 8, 7, 255))
        self.assertEqual(doc["images"][0]["name"], "skin.png")

    def test_a_mesh_that_cannot_be_converted_is_counted_and_said(self) -> None:
        rng = random.Random(83)
        good, bad, empty = handler(rng, 9, 1), handler(rng, 9, 1), handler(rng, 9, 1)
        bad.get_triangles = lambda: [[(0, 1, 99)]]
        empty.get_triangles = lambda: [[]]
        fake = types.ModuleType("UnityPy.helpers.MeshHelper")
        fake.MeshHandler = lambda data: data.h
        modules = {"UnityPy": types.ModuleType("UnityPy"), "UnityPy.helpers": types.ModuleType("h")}
        modules["UnityPy.helpers.MeshHelper"] = fake
        log = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, modules):
            ctx = NS(
                staging=Path(tmp), selected_exts=None, log=lambda text, stage: log.append(text)
            )
            record = {"shared": {}, "env": NS(objects=[])}
            made = []
            for name, h in (("good", good), ("bad", bad), ("empty", empty)):
                h.process = lambda: None
                data = mesh_data(h)
                data.h = h
                made.append(
                    meshes.write(ctx, NS(assets_file=NS(name="f"), path_id=1), data, name, record)
                )
            self.assertEqual(made, [1, 0, 0])
            self.assertEqual(sorted(p.name for p in (Path(tmp) / "mesh").iterdir()), ["good.glb"])
            notes = meshes.summary(ctx, record["shared"])
            self.assertIn("2 mesh(es) not written as .glb", notes[0])
            self.assertIn("bad: a sub-mesh points at vertex 99 of 9", notes[0])
            self.assertIn("1 .glb mesh(es) untextured", notes[1])
            self.assertEqual(log, ["glTF: 1 mesh(es) also as .glb (mesh/)"])
            skipped = NS(staging=Path(tmp), selected_exts={".png"}, log=log.append)
            self.assertEqual(meshes.write(skipped, None, None, "x", record), 0)  # filtered out
        self.assertEqual(meshes.summary(ctx, {}), [])


if __name__ == "__main__":
    unittest.main()
