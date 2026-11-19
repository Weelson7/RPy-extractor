"""L1: Total War rigid models of version 5 (UTF-16 names) and of the material layouts beside the
default block (decode.rigid_model_v2: viwo/plugins/warscape/rigid.py and models.py). Properties
over random models the test lays out byte by byte as Rome II's files hold them: versions 5, 6
and 7, groups of every layout read (static, collision, weighted, cinematic and water in a
default block; banner, bow wave and decal boxes in their own blocks) beside a flag placement
and a group of a type not read; the skeleton named in UTF-16 at version 5. Every group read is
a primitive whose every vertex is there with X mirrored and every channel its layout holds;
each layout's other data stays as data; a decal box is see-through; what is not read is counted
by name, and a file of only that is refused with it."""

import random
import struct
import tempfile
import unittest
from pathlib import Path

from tests.test_owmdl import open_glb
from tests.test_rigid_models import (
    DXT1,
    ctx,
    half,
    lay_out,
    links,
    mirror,
    new_skeleton,
    new_vertex,
    norm,
    png_of,
    unit3,
    vertex,  # fmt: skip
)
from viwo.contracts.types import OutcomeKind
from viwo.plugins.warscape import models

DEFAULT = {"static": (0, 68), "collision": (1, 62), "weighted": (3, 65), "cinematic": (4, 70),
           "water": (8, 83)}  # fmt: skip
OTHER = {"banner": 30, "bow wave": 22, "decal": 87}
SKINNED = {"weighted": 3, "cinematic": 4}


def text(value: str, size: int, wide: bool) -> bytes:
    return value.encode("utf-16-le" if wide else "latin-1").ljust(size, b"\0")


def vert(v: dict, layout: str) -> bytes:
    n, u, w = v["nb"][0:3], v["nb"][3:6], v["nb"][6:9]
    if layout == "collision":
        return struct.pack("<6f", *v["p"], *norm(n))
    if layout == "water":
        return struct.pack("<6e", *v["p"], 1.0, *v["uv"])
    if layout == "decal":
        return struct.pack("<4f", *v["p"], 1.0)
    if layout == "bow wave":
        return struct.pack("<10ef", *v["p"], 1.0, *v["q"], 1.0, *v["uv"], v["f"])
    if layout == "banner":
        directions = bytes([*n[::-1], 0, *u[::-1], 0, *w[::-1], 0])
        return struct.pack("<6e", *v["p"], 1.0, *v["uv"]) + directions + bytes(v["c"])
    return vertex(v, SKINNED.get(layout, 0))  # static (and the type not read)


def default_block(g: dict, wide: bool) -> bytes:
    """From the shader (@48) to the vertices: format, name, folders, pivot, matrices, counts,
    one attachment point, the textures, 8 bytes of parameters."""
    size = 512 if wide else 256
    textures = b"".join(struct.pack("<I", k) + text(p, size, wide) for k, p in g["textures"])
    out = text("default_dry", 64 if wide else 32, wide) + struct.pack("<H", g["format"])
    out += text(g["name"], 64 if wide else 32, wide) + bytes(2 * size + 2)
    out += struct.pack("<3f", *g["pivot"]) + bytes(144) + struct.pack("<ii", -1, -1)
    out += struct.pack("<II", 1, len(g["textures"])) + bytes(140)
    return out + bytes(116 if wide else 84) + textures + bytes(8)


def other_block(g: dict, wide: bool) -> bytes:
    shader = text("default_dry", 64 if wide else 32, wide)
    if g["layout"] == "decal":
        return shader + text(g["decal"], 512 if wide else 256, wide) + bytes(36)
    if g["layout"] == "banner":
        return shader + text(g["name"], 32, False) + bytes(256)
    if g["layout"] == "flag":  # a placement: its quad's matrix, no vertices
        return shader + text(g["name"], 32, False) + struct.pack("<12f", *[0.0] * 12)
    return shader


def group(g: dict, wide: bool) -> bytes:
    """Common header, bounding box, the block, vertices, indices."""
    block = default_block(g, wide) if g["layout"] in DEFAULT else other_block(g, wide)
    if g["layout"] == "unknown":
        block = default_block(g | {"format": 26994}, wide)
    verts = b"".join(vert(v, g["layout"]) for v in g["verts"]) if g["layout"] != "flag" else b""
    flat = [i for t in g["tris"] for i in t]
    first = 48 + len(block)
    size = first + len(verts) + 2 * len(flat)
    head = struct.pack("<HH5I", g["type"], 0, size, first, len(g["verts"]), first + len(verts),
                       len(flat))  # fmt: skip
    return head + bytes(24) + block + verts + struct.pack(f"<{len(flat)}H", *flat)


def rmv2(version: int, skeleton: str, groups: list) -> bytes:
    wide, lod = version == 5, 28 if version == 7 else 20
    name = 256 if wide else 128
    body = b"".join(group(g, wide) for g in groups)
    head = struct.pack("<4sII", b"RMV2", version, 1) + text(skeleton, name, wide)
    head += struct.pack("<4If", len(groups), 0, 0, 12 + name + lod, 100.0) + bytes(lod - 20)
    return head + body


def new_group(rng, layout: str, bones: int, k: int) -> dict:
    verts = [new_vertex(rng, bones) for _ in range(rng.randint(3, 9))]
    for v in verts:
        v |= {"q": [rng.uniform(-3, 3) for _ in range(3)], "f": rng.uniform(0, 1)}
    tris = [tuple(rng.randrange(len(verts)) for _ in range(3)) for _ in range(rng.randint(1, 5))]
    fmt, kind = DEFAULT.get(layout, (-1, OTHER.get(layout, 26 if layout == "flag" else 99)))
    pivot = [rng.uniform(-2, 2) for _ in range(3)] if fmt in (0, 1, 8) else [0.0] * 3
    textures = [(1, "tex/x_normal.dds"), (0, "variantmeshes/tex/unit_diffuse.dds")][: 1 + k % 2]
    return {"layout": layout, "format": fmt, "type": kind, "name": f"group{k}", "verts": verts,
            "tris": tris, "pivot": pivot, "textures": textures,
            "decal": f"rigidmodels/decals/battle/mud_{k}"}  # fmt: skip


class RigidLayoutTests(unittest.TestCase):
    def close(self, got, want, tol: float = 1e-3) -> None:
        self.assertEqual(len(got), len(want))
        self.assertTrue(all(abs(a - b) < tol * max(1, abs(b)) for a, b in zip(got, want)))

    def test_every_layout_of_every_version(self) -> None:
        rng = random.Random(53)
        for case in range(30):
            version = (5, 6, 7)[case % 3]
            sk = new_skeleton(rng) if case % 4 else None
            bones = len(sk["names"]) if sk else 3
            kinds = list(DEFAULT) + ["decal"] + (["banner", "bow wave"] if version > 5 else [])
            chosen = [rng.choice(kinds) for _ in range(rng.randint(2, 5))]
            groups = [new_group(rng, kind, bones, k) for k, kind in enumerate(chosen)]
            odd = [new_group(rng, kind, bones, 9) for kind in ("flag", "unknown")]
            raw = rmv2(version, "skel", groups[:1] + odd + groups[1:])
            dds = DXT1 + bytes(rng.randrange(256) for _ in range(8))
            with tempfile.TemporaryDirectory() as tmp:
                model = lay_out(Path(tmp), raw, sk, dds, rng.random() < 0.5)
                out = models.RigidModelDecoder().decode(model, Path(tmp) / "o", ctx())
                self.assertEqual((out.kind, out.files, out.error), (OutcomeKind.OK, 1, ""), case)
                self.assertIn("2 mesh group(s) of layouts not read left out, e.g. material type "
                              "26, flag placement: no vertex data", out.notes[-1])  # fmt: skip
                doc, blob, values = open_glb(Path(tmp) / "o" / "unit.glb")
            self.groups(groups, doc, values, sk)
            images = [doc["bufferViews"][i["bufferView"]] for i in doc.get("images", [])]
            kept = {blob[v["byteOffset"] : v["byteOffset"] + v["byteLength"]] for v in images}
            textured = any(len(g["textures"]) > 1 and g["layout"] in DEFAULT for g in groups)
            self.assertEqual(kept, {png_of(dds)} if textured else set(), case)

    def groups(self, groups: list, doc: dict, values, sk) -> None:
        prims = doc["meshes"][0]["primitives"]
        self.assertEqual(len(prims), len(groups))
        rigged = sk and any(g["layout"] in SKINNED for g in groups)
        self.assertEqual("skins" in doc, bool(rigged))
        for g, prim in zip(groups, prims):
            material = doc["materials"][prim["material"]]
            self.assertEqual(material["extras"]["layout"], g["layout"])
            decal = g["layout"] == "decal"
            self.assertEqual(material.get("alphaMode"), "BLEND" if decal else None)
            name = g["decal"].rpartition("/")[2] if decal else g["name"]
            self.assertEqual(material["name"], name if g["layout"] != "bow wave" else "group_22")
            flat = [t[d] for t in g["tris"] for d in (0, 2, 1)]
            self.assertEqual(list(values(prim["indices"], "I")), flat)
            self.channels(g, prim["attributes"], values)
            if g["layout"] in SKINNED or rigged:
                self.bone_links(g, prim["attributes"], values, sk)

    def channels(self, g: dict, attr: dict, values) -> None:
        layout = g["layout"]
        floats = layout in ("collision", "decal")
        stored = [v["p"] if floats else half(v["p"]) for v in g["verts"]]
        pos = [mirror([a + b for a, b in zip(p, g["pivot"])]) for p in stored]
        self.close(values(attr["POSITION"]), [x for p in pos for x in p])
        has = {"NORMAL": layout in ("static", "collision", "weighted", "cinematic", "banner")}
        has["TEXCOORD_0"] = layout not in ("collision", "decal")
        has |= {
            "TANGENT": has["NORMAL"] and layout != "collision",
            "TEXCOORD_1": layout == "static",
        }
        has |= {"_COLOR_0": layout in ("static", "banner"), "_POSITION_1": layout == "bow wave"}
        self.assertEqual({k for k in has if k in attr}, {k for k, v in has.items() if v}, layout)
        if has["NORMAL"]:
            normals = [unit3(mirror(norm(v["nb"][0:3]))) for v in g["verts"]]
            self.close(values(attr["NORMAL"]), [x for n in normals for x in n])
        if has["TEXCOORD_0"]:
            self.close(values(attr["TEXCOORD_0"]), [x for v in g["verts"] for x in half(v["uv"])])
        if has["_COLOR_0"]:
            self.close(values(attr["_COLOR_0"]), [c / 255 for v in g["verts"] for c in v["c"]])
        if layout == "bow wave":
            self.close(values(attr["_POSITION_1"]), [x for v in g["verts"] for x in half(v["q"])])
            self.close(values(attr["_VALUE_0"]), [v["f"] for v in g["verts"]])
        if has["TANGENT"]:
            self.tangents(g, values(attr["TANGENT"]))

    def tangents(self, g: dict, tangents) -> None:
        for k, v in enumerate(g["verts"]):
            n, t = unit3(mirror(norm(v["nb"][0:3]))), unit3(mirror(norm(v["nb"][3:6])))
            b = mirror(norm(v["nb"][6:9]))
            side = sum(x * y for x, y in zip([n[1] * t[2] - n[2] * t[1], n[2] * t[0] - n[0] * t[2],
                                              n[0] * t[1] - n[1] * t[0]], b))  # fmt: skip
            self.close(tangents[4 * k : 4 * k + 3], t)
            self.assertEqual(tangents[4 * k + 3], -1.0 if side < 0 else 1.0)

    def bone_links(self, g: dict, attr: dict, values, sk) -> None:
        name = "" if sk else "_"
        joints, weights = values(attr[f"{name}JOINTS_0"], "H"), values(attr[f"{name}WEIGHTS_0"])
        fmt = SKINNED.get(g["layout"], 0)
        for k, v in enumerate(g["verts"]):
            want = links(v, fmt) if fmt else {0: 1.0}
            got = {}
            for slot in range(4 * k, 4 * k + 4):
                got[joints[slot]] = got.get(joints[slot], 0.0) + weights[slot]
            for j in set(got) | set(want):
                self.assertAlmostEqual(got.get(j, 0.0), want.get(j, 0.0), 5)

    def test_what_is_not_read_is_named(self) -> None:
        rng = random.Random(54)
        flags = rmv2(6, "", [new_group(rng, "flag", 1, k) for k in range(2)])
        effect = rmv2(5, "", [new_group(rng, "flag", 1, 0) | {"type": 45}])
        bent = new_group(rng, "decal", 1, 0)
        cut = bytearray(rmv2(6, "", [bent, new_group(rng, "static", 1, 1)]))
        struct.pack_into("<I", cut, 160 + 16, struct.unpack_from("<I", cut, 160 + 16)[0] - 2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "rigid_model_v2"
            root.mkdir()
            for name, raw in (("flags", flags), ("effect", effect), ("bent", bytes(cut))):
                (root / f"{name}.rigid_model_v2").write_bytes(raw)
            for name, kind, why in (
                ("flags", OutcomeKind.FAILED, "(material type 26, flag placement: no vertex"),
                ("effect", OutcomeKind.FAILED, "(material type 45, light or effect: no vertex"),
                ("bent", OutcomeKind.OK, "type 87, its vertices do not fit the decal layout"),
            ):
                out = models.RigidModelDecoder().decode(root / f"{name}.rigid_model_v2",
                                                        Path(tmp) / name, ctx())  # fmt: skip
                self.assertEqual(out.kind, kind, name)
                self.assertIn(why, out.error + "".join(out.notes), name)

    def test_a_skeleton_too_short_keeps_the_links_as_data(self) -> None:
        rng = random.Random(55)
        sk = new_skeleton(rng)
        g = new_group(rng, "cinematic", 1, 0)
        for v in g["verts"]:
            v["j"] = [len(sk["names"]) + 2] * 4
        with tempfile.TemporaryDirectory() as tmp:
            model = lay_out(Path(tmp), rmv2(5, "skel", [g]), sk, DXT1 + bytes(8), False)
            out = models.RigidModelDecoder().decode(model, Path(tmp) / "o", ctx())
            self.assertEqual((out.kind, out.files), (OutcomeKind.OK, 1))
            want = f"has {len(sk['names'])} bones, a vertex weighs on bone {len(sk['names']) + 2}"
            self.assertIn(want, out.notes[1])
            doc, _, values = open_glb(Path(tmp) / "o" / "unit.glb")
        self.assertNotIn("skins", doc)
        self.bone_links(g, doc["meshes"][0]["primitives"][0]["attributes"], values, None)


if __name__ == "__main__":
    unittest.main()
