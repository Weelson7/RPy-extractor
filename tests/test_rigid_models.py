"""L1: Total War rigid models into .glb (decode.rigid_model_v2: viwo/plugins/warscape/models.py
over rigid.py). Properties over random models the test lays out byte by byte (versions 6 and 7;
static, weighted and cinematic groups beside one of a format not read; the skeleton's .anim and
.bone_inv_trans_mats in the workspace's groups or in an extracted pack's folders, or missing):
every group of LOD 0 is a primitive named after it, every vertex is there from its pivot with X
mirrored, with its normal, tangent along U (handedness after the mirror), UVs and colour; every
triangle is there wound the other way; the colour map is embedded as the PNG Pillow makes of its
.dds; the bones are joints whose world matrix undoes their bind matrix, and each vertex keeps its
links, summing to one; without the skeleton the links stay as data and that is said; a lopsided
shape keeps its sides and its front faces; what is not read is refused by name or counted."""

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
from viwo.plugins.warscape import models

DXT1 = struct.pack("<4sIIIIIII44x", b"DDS ", 124, 0x81007, 4, 4, 8, 0, 1)
DXT1 += struct.pack("<II4s20x", 32, 0x4, b"DXT1") + struct.pack("<I16x", 0x1000)
SIGN = (-1.0, 1.0, 1.0, 1.0)  # the mirror (X); the translation column keeps the row's sign


def half(values) -> list[float]:
    return list(struct.unpack(f"<{len(values)}e", struct.pack(f"<{len(values)}e", *values)))


def norm(values) -> list[float]:
    return [v / 127.5 - 1.0 for v in values]


def vertex(v: dict, fmt: int) -> bytes:
    """One vertex: static directions as B, G, R; weighted and cinematic as R, G, B, V first."""
    n, u, w = v["nb"][0:3], v["nb"][3:6], v["nb"][6:9]
    pos = struct.pack("<4e", *v["p"], 1.0 if fmt == 0 else 0.0)
    if fmt == 0:
        uv = struct.pack("<4e", *v["uv"], *v["uv2"])
        return pos + uv + bytes([*n[::-1], 0, *u[::-1], 0, *w[::-1], 0]) + bytes(v["c"])
    links = bytes(v["j"][:2] + [v["w"][0], 0]) if fmt == 3 else bytes(v["j"] + v["w"])
    rest = bytes([*n, 0]) + struct.pack("<2e", *v["uv"]) + bytes([*w, 0, *u, 0])
    return pos + links + rest


def new_vertex(rng, bones: int) -> dict:
    w = [rng.randrange(1, 60) for _ in range(3)]
    return {
        "p": [rng.uniform(-3, 3) for _ in range(3)],
        "uv": [rng.random(), rng.random()],
        "uv2": [rng.random(), rng.random()],
        "nb": [rng.randrange(256) for _ in range(9)],
        "c": [rng.randrange(256) for _ in range(4)],
        "j": [rng.randrange(max(1, bones)) for _ in range(4)],
        "w": [*w, 255 - sum(w) + rng.randint(-1, 1)],  # stored bytes round: 254 to 256
    }


def group(g: dict) -> bytes:
    """A mesh group: common header, material block, textures, a parameter, vertices, indices."""
    verts = b"".join(vertex(v, g["format"]) for v in g["verts"])
    flat = [i for t in g["tris"] for i in t]
    textures = b"".join(struct.pack("<I", kind) + path.encode().ljust(256, b"\0")
                        for kind, path in g["textures"])  # fmt: skip
    block = struct.pack("<H", g["format"]) + g["name"].encode().ljust(32, b"\0") + bytes(514)
    block += struct.pack("<3f", *g["pivot"]) + bytes(144) + struct.pack("<ii", -1, -1)
    block += struct.pack("<II", 1, len(g["textures"])) + bytes(140) + bytes(84) + textures
    first = 80 + len(block) + 8
    index_at = first + len(verts)
    size = index_at + 2 * len(flat)
    head = struct.pack("<HH5I", g["type"], 0, size, first, len(g["verts"]), index_at, len(flat))
    head += bytes(24) + b"default_dry".ljust(32, b"\0")
    return head + block + struct.pack("<ii", 3, 1) + verts + struct.pack(f"<{len(flat)}H", *flat)


def rmv2(version: int, skeleton: str, groups: list) -> bytes:
    lod = 20 if version == 6 else 28
    body = b"".join(map(group, groups))
    head = struct.pack("<4sII", b"RMV2", version, 1) + skeleton.encode().ljust(128, b"\0")
    head += struct.pack("<4If", len(groups), 0, 0, 140 + lod, 100.0) + bytes(lod - 20)
    return head + body


def new_group(rng, fmt: int, bones: int, k: int) -> dict:
    verts = [new_vertex(rng, bones) for _ in range(rng.randint(3, 9))]
    tris = [tuple(rng.randrange(len(verts)) for _ in range(3)) for _ in range(rng.randint(1, 5))]
    pivot = [rng.uniform(-2, 2) for _ in range(3)] if fmt == 0 else [0.0] * 3
    textures = [(1, "tex/x_normal.dds"), (0, "variantmeshes/tex/unit_diffuse.dds")][: 1 + k % 2]
    kind = {0: 68, 3: 65, 4: 70}[fmt]
    return {"format": fmt, "type": kind, "name": f"group{k}", "verts": verts, "tris": tris,
            "pivot": pivot, "textures": textures}  # fmt: skip


def new_skeleton(rng) -> dict:
    n = rng.randint(1, 5)
    worlds = []
    for _ in range(n):
        q = [rng.gauss(0, 1) for _ in range(4)]
        q = [x / math.sqrt(sum(y * y for y in q)) for x in q]
        worlds.append(gltf.matrix([rng.uniform(-2, 2) for _ in range(3)], q, [1] * 3))
    return {"names": [f"bn_{i}" for i in range(n)],
            "parents": [rng.randrange(-1, i) for i in range(n)], "worlds": worlds}  # fmt: skip


def skeleton_files(sk: dict) -> tuple[bytes, bytes]:
    n = len(sk["names"])
    anim = struct.pack("<IIfH", 5, 1, 20.0, 4) + b"skel" + struct.pack("<fI", 0.1, n)
    for name, parent in zip(sk["names"], sk["parents"]):
        anim += struct.pack("<H", len(name)) + name.encode() + struct.pack("<i", parent)
    inverse = struct.pack("<II", 1, n)
    for world in sk["worlds"]:
        a = gltf.inverse(world)
        inverse += struct.pack("<12f", *(a[r][c] for c in range(4) for r in range(3)))
    return anim + bytes(16), inverse


def lay_out(root: Path, raw: bytes, sk: dict | None, png_src: bytes, packed: bool) -> Path:
    """The workspace's groups, or an extracted pack's folders."""
    anim, inverse = skeleton_files(sk) if sk else (None, None)
    names = ("unit.rigid_model_v2", "unit_diffuse.dds", "skel.anim", "skel.bone_inv_trans_mats")
    folders = ("variantmeshes/units", "variantmeshes/tex") + ("animations/skeletons",) * 2
    if not packed:  # the workspace's group of each kind
        folders = ("rigid_model_v2", "dds", "anim", "bone_inv_trans_mats")
    place = {k: f"{f}/{n}" for k, f, n in zip(("model", "dds", "anim", "inv"), folders, names)}
    if sk and not packed and len(sk["names"]) % 2:  # another skeleton's files took the name
        other = skeleton_files(sk | {"names": sk["names"] + ["bn_x"]})[0]
        place |= {"other": place["anim"], "anim": "anim/skel__1.anim"}
        (root / "anim").mkdir(parents=True)
        (root / place["other"]).write_bytes(other)
    for key, data in (("model", raw), ("dds", png_src), ("anim", anim), ("inv", inverse)):
        if data is not None:
            (root / place[key]).parent.mkdir(parents=True, exist_ok=True)
            (root / place[key]).write_bytes(data)
    return root / place["model"]


def ctx():
    return SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


def png_of(dds: bytes) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    with Image.open(io.BytesIO(dds)) as image:
        image.save(out, "PNG")
    return out.getvalue()


def mirror(v) -> list[float]:
    return [-v[0], v[1], v[2]]


def unit3(v) -> list[float]:
    size = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / size for x in v]


def cross(a, b) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def links(v: dict, fmt: int) -> dict:
    pairs = (
        [(v["j"][0], v["w"][0]), (v["j"][1], 255 - v["w"][0])] if fmt == 3 else zip(v["j"], v["w"])
    )
    out = {}
    for j, w in pairs:
        out[j] = out.get(j, 0) + w
    total = sum(out.values())
    return {j: w / total for j, w in out.items() if w}


class RigidModelTests(unittest.TestCase):
    def close(self, got, want, tol: float = 1e-3) -> None:
        self.assertEqual(len(got), len(want))
        self.assertTrue(all(abs(a - b) < tol * max(1, abs(b)) for a, b in zip(got, want)))

    def test_lod_0_of_every_group_with_its_rig_and_texture(self) -> None:
        rng = random.Random(50)
        for case in range(24):
            sk = new_skeleton(rng) if case % 3 else None
            bones = len(sk["names"]) if sk else 3
            formats = [rng.choice((0, 3, 4)) for _ in range(rng.randint(1, 3))] + [3]
            groups = [new_group(rng, f, bones, k) for k, f in enumerate(formats)]
            odd = new_group(rng, 0, bones, 9) | {"type": 99, "format": 26994}
            spot = rng.randrange(len(groups) + 1)
            raw = rmv2(rng.choice((6, 7)), "skel", groups[:spot] + [odd] + groups[spot:])
            dds = DXT1 + bytes(rng.randrange(256) for _ in range(8))
            with tempfile.TemporaryDirectory() as tmp:
                model = lay_out(Path(tmp), raw, sk, dds, rng.random() < 0.5)
                out = models.RigidModelDecoder().decode(model, Path(tmp) / "o", ctx())
                self.assertEqual((out.kind, out.files, out.error), (OutcomeKind.OK, 1, ""), case)
                self.assertIn("1 mesh group(s) of layouts not read left out, e.g. material "
                              "type 99, vertex format 26994", out.notes[-1])  # fmt: skip
                if sk is None:
                    self.assertIn("keep their bone links as data", out.notes[1])
                    self.assertIn("its skeleton 'skel' is not in the run", out.notes[1])
                doc, blob, values = open_glb(Path(tmp) / "o" / "unit.glb")
            self.check(groups, doc, values, sk)
            images = [doc["bufferViews"][i["bufferView"]] for i in doc.get("images", [])]
            kept = {blob[v["byteOffset"] : v["byteOffset"] + v["byteLength"]] for v in images}
            textured = any(len(g["textures"]) > 1 for g in groups)
            self.assertEqual(kept, {png_of(dds)} if textured else set())
            bare = sum(len(g["textures"]) < 2 for g in groups)
            self.assertIn(f"{bare} of {len(groups)} material(s) untextured", out.notes[0])

    def check(self, groups: list, doc: dict, values, sk) -> None:
        prims = doc["meshes"][0]["primitives"]
        self.assertEqual(len(prims), len(groups))
        for g, prim in zip(groups, prims):
            material = doc["materials"][prim["material"]]
            self.assertEqual(material["name"], g["name"])
            self.assertEqual(material["extras"]["textures"], [p for _, p in g["textures"]])
            flat = [t[d] for t in g["tris"] for d in (0, 2, 1)]
            self.assertEqual(list(values(prim["indices"], "I")), flat)
            self.vertex_data(g, prim["attributes"], values)
            self.bone_links(g, prim["attributes"], values, sk)
        if sk:
            self.skeleton(sk, doc, values)

    def vertex_data(self, g: dict, attr: dict, values) -> None:
        fmt = g["format"]
        pos = [mirror([a + b for a, b in zip(half(v["p"]), g["pivot"])]) for v in g["verts"]]
        self.close(values(attr["POSITION"]), [x for p in pos for x in p])
        normals = [unit3(mirror(norm(v["nb"][0:3]))) for v in g["verts"]]
        self.close(values(attr["NORMAL"]), [x for n in normals for x in n])
        self.close(values(attr["TEXCOORD_0"]), [x for v in g["verts"] for x in half(v["uv"])])
        if fmt == 0:
            self.close(values(attr["TEXCOORD_1"]), [x for v in g["verts"] for x in half(v["uv2"])])
            self.close(values(attr["_COLOR_0"]), [c / 255 for v in g["verts"] for c in v["c"]])
        tangents = values(attr["TANGENT"])
        for k, (v, n) in enumerate(zip(g["verts"], normals)):
            t = unit3(mirror(norm(v["nb"][3:6])))
            side = sum(a * b for a, b in zip(cross(n, t), mirror(norm(v["nb"][6:9]))))
            self.close(tangents[4 * k : 4 * k + 3], t)
            self.assertEqual(tangents[4 * k + 3], -1.0 if side < 0 else 1.0)

    def bone_links(self, g: dict, attr: dict, values, sk) -> None:
        name = "" if sk else "_"
        if g["format"] == 0 and not sk:
            self.assertNotIn("_JOINTS_0", attr)
            return
        joints, weights = values(attr[f"{name}JOINTS_0"], "H"), values(attr[f"{name}WEIGHTS_0"])
        for k, v in enumerate(g["verts"]):
            want = links(v, g["format"]) if g["format"] else {0: 1.0}
            got = {}
            for slot in range(4 * k, 4 * k + 4):
                got[joints[slot]] = got.get(joints[slot], 0.0) + weights[slot]
            for j in set(got) | set(want):
                self.assertAlmostEqual(got.get(j, 0.0), want.get(j, 0.0), 5)

    def skeleton(self, sk: dict, doc: dict, values) -> None:
        nodes, inverse = doc["nodes"], values(doc["skins"][0]["inverseBindMatrices"])
        parent = {k: i for i, node in enumerate(nodes) for k in node.get("children", ())}

        def world(i):
            m = nodes[i]["matrix"]
            local = [[m[4 * c + r] for c in range(4)] for r in range(3)]
            return gltf.times(world(parent[i]), local) if i in parent else local

        for i, (name, up) in enumerate(zip(sk["names"], sk["parents"])):
            self.assertEqual((nodes[i]["name"], parent.get(i, -1)), (name, up))
            m = sk["worlds"][i]
            want = [[m[r][c] * SIGN[r] * SIGN[c] for c in range(4)] for r in range(3)]
            got = world(i)
            for r in range(3):
                self.close(got[r], want[r])
            cols = inverse[16 * i : 16 * i + 16]
            one = gltf.times([[cols[4 * c + r] for c in range(4)] for r in range(3)], got)
            for r in range(3):
                self.close(one[r], [float(r == c) for c in range(4)])

    def test_an_asymmetric_shape_keeps_its_sides_and_its_front(self) -> None:
        """Warscape: right +X, up +Y, forward +Z (left-handed); the stored order of a front
        face makes cross(b - a, c - a) point out of the shape (as Rome II's normals do). In
        glTF the nose must face +Z, the right side lie on -X, every triangle face outward."""
        rng = random.Random(51)
        nose, left, top, right = [0, 0, 9], [-4, 0, 0], [0, 17, 0], [4, 0, 0]
        corners = [nose, left, top, right]
        middle = [sum(c[k] for c in corners) / 4 for k in range(3)]
        tris = []
        for tri in ((0, 1, 2), (0, 2, 3), (0, 3, 1), (1, 3, 2)):
            a, b, c = (corners[i] for i in tri)
            out = [(a[k] + b[k] + c[k]) / 3 - middle[k] for k in range(3)]
            normal = cross([b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)])
            tris.append(tri if sum(x * y for x, y in zip(normal, out)) > 0 else tri[::-1])
        g = new_group(rng, 0, 1, 0) | {"tris": tris, "pivot": [0.0] * 3}
        g["verts"] = [new_vertex(rng, 1) | {"p": c} for c in corners]
        with tempfile.TemporaryDirectory() as tmp:
            model = lay_out(Path(tmp), rmv2(6, "", [g]), None, DXT1 + bytes(8), False)
            models.RigidModelDecoder().decode(model, Path(tmp) / "o", ctx())
            doc, _, values = open_glb(Path(tmp) / "o" / "unit.glb")
        prim = doc["meshes"][0]["primitives"][0]
        p = values(prim["attributes"]["POSITION"])
        got = [list(p[3 * v : 3 * v + 3]) for v in range(4)]
        self.close(got[0], [0, 0, 9])  # the nose faces glTF's +Z
        self.close(got[3], [-4, 0, 0])  # its right side on -X: forward x up = right
        centre = [sum(q[k] for q in got) / 4 for k in range(3)]
        order = list(values(prim["indices"], "I"))
        for t in range(4):
            a, b, c = (got[i] for i in order[3 * t : 3 * t + 3])
            out = [(a[k] + b[k] + c[k]) / 3 - centre[k] for k in range(3)]
            normal = cross([b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)])
            self.assertGreater(sum(x * y for x, y in zip(normal, out)), 0)

    def test_what_is_not_read_is_refused_by_name_and_counted(self) -> None:
        rng = random.Random(52)
        good = rmv2(6, "", [new_group(rng, 0, 1, 0)])
        odd = new_group(rng, 0, 1, 1) | {"type": 99, "format": 26994}
        old = bytearray(good)
        old[4:8] = struct.pack("<I", 1)
        empty = bytearray(good[:148])
        empty[8:12] = struct.pack("<I", 0)  # no LOD: nothing to draw
        short = struct.pack("<HH5I", 30, 0, 380, 368, 2, 380, 0) + bytes(372)  # a shorter block
        combo = struct.pack("<4sII", b"RMV2", 6, 1) + bytes(128)
        combo += struct.pack("<4If", 1, 12, 0, 160, 100.0) + short
        cases = {"good": good, "old": bytes(old), "decal": rmv2(7, "", [odd]),
                 "empty": bytes(empty), "cut": good[: rng.randrange(200, len(good) - 10)],
                 "other": b"RMV3" + good[4:], "combo": combo}  # fmt: skip
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "rigid_model_v2"
            root.mkdir()
            for name, raw in cases.items():
                (root / f"{name}.rigid_model_v2").write_bytes(raw)
            paths = sorted(root.iterdir())
            out = models.RigidModelDecoder().decode_many(paths, Path(tmp) / "o", ctx())
            self.assertEqual((out.kind, out.files), (OutcomeKind.OK, 1))
            self.assertIn("7 model(s): 1 written as .glb, 1 without a mesh", out.notes[0])
            self.assertTrue(out.error.startswith("5 model(s) not converted, e.g. "), out.error)
            self.assertEqual([p.name for p in (Path(tmp) / "o").iterdir()], ["good.glb"])
            for name, why in (
                ("old", "rigid model version 1: versions 5, 6 and 7 are read"),
                ("decal", "no mesh group of a layout read (material type 99, vertex format"),
                ("other", "not a rigid model"),
                ("combo", "(material type 30, its vertices do not fit the banner layout)"),
            ):
                alone = models.RigidModelDecoder().decode(root / f"{name}.rigid_model_v2",
                                                          Path(tmp) / name, ctx())  # fmt: skip
                self.assertEqual(alone.kind, OutcomeKind.FAILED, name)
                self.assertIn(why, alone.error)


if __name__ == "__main__":
    unittest.main()
