"""L1: UEFormat models into .glb (viwo/plugins/unreal/uemodel.py over viwo/contracts/gltf.py).
Properties over random models written the way CUE4Parse writes UEFormat version 10 (plain and
gzip): LOD 0 is read, never the Nanite LOD before it; every vertex, normal, tangent, UV set and
colour set is in the .glb with Y and Z swapped, the tangent's handedness turned by the mirror;
every section is a primitive with its material's name and its triangles in Unreal's order; a
known asymmetric shape keeps its right, its up, its forward and its front faces; every bone
weight survives; every bone sits where Unreal's reference pose puts it, mirrored, and its
inverse bind matrix undoes that; a skeleton alone is no model; a file cut short, of another
version or compressed with zstd on a Python that cannot inflate it is refused with its reason,
never half-written."""

import gzip
import math
import random
import struct
import sys
import tempfile
import unittest
from array import array
from pathlib import Path
from unittest import mock

from tests.test_owmdl import open_glb
from viwo.contracts import gltf
from viwo.plugins.unreal import uemodel

SWAP = (0, 2, 1)  # glTF axis n is Unreal axis SWAP[n]


def s(text: str) -> bytes:
    raw = text.encode()
    return struct.pack("<i", len(raw)) + raw


def attrs(*items: tuple[str, bytes]) -> bytes:
    out = struct.pack("<i", len(items))
    return out + b"".join(s(name) + struct.pack("<i", len(blob)) + blob for name, blob in items)


def arr(rows: list[bytes]) -> bytes:
    return struct.pack("<i", len(rows)) + b"".join(rows)


def floats(*values) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def header(body: bytes, method: str = "", version: int = 10) -> bytes:
    head = b"UEFORMAT" + s("UEMODEL") + bytes([version]) + s("SK_Thing") + s("/Game/SK_Thing")
    if not method:
        return head + b"\0" + body
    stored = gzip.compress(body) if method == "GZIP" else body
    return head + b"\1" + s(method) + struct.pack("<ii", len(body), len(stored)) + stored


def unit(rng: random.Random) -> list[float]:
    q = [rng.gauss(0, 1) for _ in range(4)]
    size = math.sqrt(sum(v * v for v in q))
    return [v / size for v in q]


def lod(m: dict) -> bytes:
    """One LOD's attribute set from the made model."""
    n = m["count"]
    items = [("VERTICES", arr([floats(*p) for p in m["pos"]]))]
    items += [("NORMALS", arr([floats(w, *v) for w, v in zip(m["sign"], m["nor"])]))]
    items += [("TANGENTS", arr([floats(*t) for t in m["tan"]]))]
    uvs = [s(f"UV{k}") + arr([floats(*uv) for uv in m["uv"][k]]) for k in range(len(m["uv"]))]
    items += [("TEXCOORDS", struct.pack("<i", len(uvs)) + b"".join(uvs))]
    items += [("INDICES", arr([struct.pack("<I", i) for i in m["idx"]]))]
    sets = [s("COL0") + struct.pack("<i", n) + bytes(m["col"])]
    items += [("VERTEXCOLORS", struct.pack("<i", 1) + b"".join(sets))]
    mats = [s(name) + s(f"/Game/M/{name}") + struct.pack("<ii", a, b) for name, a, b in m["sec"]]
    items += [("MATERIALS", arr(mats))]
    if m["bones"]:
        rows = [struct.pack("<Hif", b, v, w) for v, b, w in m["links"]]
        items += [("WEIGHTS", arr(rows)), ("MORPHTARGETS", arr([]))]
    return attrs(*items)


def make(rng: random.Random, skinned: bool) -> dict:
    n = rng.randint(3, 25)
    f = lambda k: [rng.uniform(-50, 50) for _ in range(k)]  # noqa: E731
    m = {"count": n, "pos": [f(3) for _ in range(n)], "nor": [f(3) for _ in range(n)]}
    m |= {"tan": [f(3) for _ in range(n)], "sign": [rng.choice((-1.0, 1.0)) for _ in range(n)]}
    m |= {"uv": [[f(2) for _ in range(n)] for _ in range(rng.randint(1, 3))]}
    m |= {"col": [rng.randrange(256) for _ in range(4 * n)]}
    tris = [rng.randint(1, 6) for _ in range(rng.randint(1, 3))]
    m["idx"] = [rng.randrange(n) for _ in range(3 * sum(tris))]
    starts = [3 * sum(tris[:k]) for k in range(len(tris))]
    m["sec"] = [(f"MI_{k}", start, t) for k, (start, t) in enumerate(zip(starts, tris))]
    m["bones"] = [
        (f"b{i}", rng.randint(-1, i - 1), f(3), unit(rng), [rng.uniform(0.5, 2) for _ in "xyz"])
        for i in range(rng.randint(1, 6) if skinned else 0)
    ]
    m["links"] = [
        (v, rng.randrange(len(m["bones"])), rng.random())
        for v in range(n)
        for _ in range(rng.randint(0, 6) if m["bones"] else 0)
    ]
    return m


def write(path: Path, m: dict, method: str = "") -> None:
    nanite = dict(m, pos=[[9e9] * 3] * m["count"], bones=[])  # never what comes out
    items = [("LODS", arr([s("Nanite") + lod(nanite), s("LOD0") + lod(m)]))]
    if m["bones"]:
        bones = [s(n) + struct.pack("<i", p) + floats(*t, *q, *z) for n, p, t, q, z in m["bones"]]
        items += [("SKELETON", attrs(("METADATA", s("/Game/Skel")), ("BONES", arr(bones))))]
    items += [("COLLISION", arr([]))]
    path.write_bytes(header(attrs(*items), method))


def cross(a, b) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def sub(a, b) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def ue_world(bones: list, i: int):
    _, parent, move, turn, scale = bones[i]
    local = gltf.matrix(move, turn, scale)
    return gltf.times(ue_world(bones, parent), local) if parent >= 0 else local


class UemodelTests(unittest.TestCase):
    def close(self, got, want) -> None:
        self.assertEqual(len(got), len(want))
        self.assertTrue(all(abs(a - b) < 1e-3 * max(1, abs(b)) for a, b in zip(got, want)))

    def test_nothing_of_lod_0_is_lost_and_the_axes_swap(self) -> None:
        rng = random.Random(90)
        for case in range(30):
            with tempfile.TemporaryDirectory() as tmp:
                m, src, out = make(rng, case % 2 == 1), Path(tmp) / "m.uemodel", Path(tmp) / "o.glb"
                write(src, m, rng.choice(("", "GZIP")))
                self.assertTrue(uemodel.convert(src, out))
                doc, _, values = open_glb(out)
                parts = doc["meshes"][0]["primitives"]
                at = parts[0]["attributes"]
                for key, rows in (("POSITION", m["pos"]), ("NORMAL", m["nor"])):
                    self.close(values(at[key]), [r[SWAP[k]] for r in rows for k in range(3)])
                tangent = [r[SWAP[k]] for r in m["tan"] for k in range(3)]
                self.close([v for i, v in enumerate(values(at["TANGENT"])) if i % 4 < 3], tangent)
                self.close(values(at["TANGENT"])[3::4], [-w for w in m["sign"]])
                for k, uv in enumerate(m["uv"]):
                    self.close(values(at[f"TEXCOORD_{k}"]), [v for row in uv for v in row])
                self.close(values(at["_COLOR_0"]), [v / 255 for v in m["col"]])
                self.assertNotIn("COLOR_0", at)
                self.assertEqual(len(parts), len(m["sec"]))
                for part, (name, first, tris) in zip(parts, m["sec"]):
                    self.assertEqual(doc["materials"][part["material"]]["name"], name)
                    want = m["idx"][first : first + 3 * tris]
                    self.assertEqual(list(values(part["indices"], "I")), want)
                if m["bones"]:
                    self.links(m, at, values)
                    self.skeleton(m, doc, values)
                else:
                    self.assertNotIn("skins", doc)

    def links(self, m, at, values) -> None:
        sets = sum(k.startswith("JOINTS_") for k in at)
        for vertex in range(m["count"]):
            want, got = {}, {}
            for v, bone, weight in m["links"]:
                if v == vertex:
                    want[bone] = want.get(bone, 0.0) + weight
            for g in range(sets):
                joints = values(at[f"JOINTS_{g}"], "H")[vertex * 4 : vertex * 4 + 4]
                weights = values(at[f"WEIGHTS_{g}"])[vertex * 4 : vertex * 4 + 4]
                for joint, weight in zip(joints, weights):
                    got[joint] = got.get(joint, 0.0) + weight
            for joint in set(want) | set(got):
                self.assertAlmostEqual(got.get(joint, 0.0), want.get(joint, 0.0), 4)

    def skeleton(self, m, doc, values) -> None:
        """Each joint, placed by its glTF nodes, is Unreal's reference pose mirrored; its
        inverse bind matrix undoes it."""
        bones, nodes = m["bones"], doc["nodes"]
        inverse = values(doc["skins"][0]["inverseBindMatrices"])

        def placed(i: int):
            node = nodes[i]
            local = gltf.matrix(node["translation"], node["rotation"], node["scale"])
            parent = next((p for p, n in enumerate(nodes) if i in n.get("children", ())), -1)
            return gltf.times(placed(parent), local) if parent >= 0 else local

        for i, bone in enumerate(bones):
            self.assertEqual(nodes[i]["name"], bone[0])
            ue, got = ue_world(bones, i), placed(i)
            for r in range(3):
                self.close(got[r], [ue[SWAP[r]][SWAP[c]] for c in range(3)] + [ue[SWAP[r]][3]])
            cols = inverse[i * 16 : i * 16 + 16]
            one = gltf.times([[cols[c * 4 + r] for c in range(4)] for r in range(3)], got)
            for r in range(3):
                self.close(one[r], [float(r == c) for c in range(4)])

    def test_an_asymmetric_shape_keeps_its_sides_and_its_front(self) -> None:
        """Unreal: forward +X, right +Y, up +Z (left-handed). Each triangle faces out, front
        counter-clockwise as a viewer sees it: in Unreal's left-handed numbers its normal is
        against cross(b - a, c - a). In glTF the same shape must have forward x up = right and
        every triangle's cross product along its normal (counter-clockwise front)."""
        nose, right, top = [100, 0, 0], [0, 50, 0], [0, 0, 180]
        pos, idx = [nose, right, top, [0, 0, 0]], [0, 1, 2, 0, 2, 3, 0, 3, 1, 1, 3, 2]
        nor = []
        for v in range(4):  # each vertex's normal: away from the opposite corner
            rest = [p for k, p in enumerate(pos) if k != v]
            middle = [sum(p[k] for p in rest) / 3 for k in range(3)]
            nor.append([pos[v][k] - middle[k] for k in range(3)])
        m = make(random.Random(5), False) | {"count": 4, "pos": pos, "nor": nor}
        m |= {"tan": [[1, 0, 0]] * 4, "sign": [1.0] * 4, "uv": [[[0, 0]] * 4], "col": [0] * 16}
        centre = [sum(p[k] for p in pos) / 4 for k in range(3)]
        faces = []
        for t in range(4):  # wound so that Unreal's front faces out (left-handed: cross inward)
            a, b, c = idx[3 * t : 3 * t + 3]
            out = sub([sum(pos[i][k] for i in (a, b, c)) / 3 for k in range(3)], centre)
            faces += (
                [a, b, c]
                if dot(cross(sub(pos[b], pos[a]), sub(pos[c], pos[a])), out) < 0
                else [a, c, b]
            )
        m |= {"idx": faces, "sec": [("M", 0, 4)]}
        with tempfile.TemporaryDirectory() as tmp:
            write(Path(tmp) / "a.uemodel", m)
            uemodel.convert(Path(tmp) / "a.uemodel", Path(tmp) / "a.glb")
            doc, _, values = open_glb(Path(tmp) / "a.glb")
        p = values(doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"])
        g = [list(p[3 * v : 3 * v + 3]) for v in range(4)]
        self.close(cross(g[0], g[2]), [v * 100 * 180 / 50 for v in g[1]])  # forward x up = right
        got = list(values(doc["meshes"][0]["primitives"][0]["indices"], "I"))
        self.assertEqual(got, faces)  # Unreal's order kept
        middle = [sum(q[k] for q in g) / 4 for k in range(3)]
        for t in range(4):
            a, b, c = (g[i] for i in got[3 * t : 3 * t + 3])
            out = sub([(a[k] + b[k] + c[k]) / 3 for k in range(3)], middle)
            self.assertGreater(dot(cross(sub(b, a), sub(c, a)), out), 0)  # counter-clockwise

    def test_what_cannot_be_read_is_said_and_nothing_half_written(self) -> None:
        rng = random.Random(91)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "good.uemodel", make(rng, True))
            whole = (root / "good.uemodel").read_bytes()
            (root / "cut.uemodel").write_bytes(whole[: rng.randrange(60, len(whole) - 1)])
            (root / "old.uemodel").write_bytes(header(b"\0" * 8, version=9))
            (root / "z.uemodel").write_bytes(header(b"\0" * 8, "ZSTD"))
            bones = arr([s("root") + struct.pack("<i", -1) + floats(0, 0, 0, 0, 0, 0, 1, 1, 1, 1)])
            skeleton = attrs(("SKELETON", attrs(("BONES", bones))))
            (root / "skel.uemodel").write_bytes(header(skeleton))
            with mock.patch.dict(sys.modules, {"compression": None}):  # no compression.zstd
                made, lost, bare = uemodel.convert_all(root)
            self.assertEqual((made, len(lost), bare), (1, 3, 1))
            said = " ".join(lost)
            self.assertIn("only UEMODEL version 10", said)
            self.assertIn("zstd-compressed: this Python cannot inflate it", said)
            self.assertIn("cut.uemodel", said)
            self.assertEqual(sorted(p.name for p in root.glob("*.glb")), ["good.glb"])
            self.assertEqual(array("B", (root / "good.glb").read_bytes()[:4]).tobytes(), b"glTF")


if __name__ == "__main__":
    unittest.main()
