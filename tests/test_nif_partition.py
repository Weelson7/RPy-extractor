"""L1: NIF skins whose vertices or weights are in the NiSkinPartition (decode.nif:
viwo/plugins/bethesda/partition.py and nifmodels.py). Properties over random NIFs the test lays
out byte by byte as nif.xml describes the block (no real NIF has been read: no Bethesda game at
hand): a skinned Skyrim SE BSTriShape with data size 0 whose vertices (in BSTriShape's layout),
triangles (each partition's copy with the shape's indices) and links are in its partition, and a
Skyrim NiTriShape whose NiSkinData holds no weights. One to three partitions each have their own
bone list, a vertex map in any order and bone indices into that list; a vertex two partitions
share is in both. Every vertex is there with its channels and lands where Gamebryo's skinning
puts it; a partition that leaves a vertex out, holds no weights or points past its bones is
refused by name."""

import random
import struct
import tempfile
import unittest
from pathlib import Path

from tests.test_nif_models import (
    DXT1,
    NifModelTests,
    Scene,
    add_shape,
    bs_vertex,
    ctx,
    lay_out,
    open_glb,
    pack_transform,
    place,
    shader,
    tri_data,
    vertices,  # fmt: skip
)
from viwo.contracts.types import OutcomeKind
from viwo.plugins.bethesda import nifmodels

STRIDE = 44  # full floats: position and the U direction's x (16), then 28 bytes
DESC = STRIDE // 4 | 4 << 8 | 5 << 16 | 6 << 20 | 7 << 24 | 8 << 28
DESC |= (0x1 | 0x2 | 0x8 | 0x10 | 0x20 | 0x40) << 44  # Skyrim SE: floats without the flag


def sixteenths(rng, verts: list) -> None:
    """Weights half floats and floats hold exactly (the partition stores floats)."""
    for v in verts:
        used = rng.randint(1, 4)
        cuts = sorted(rng.sample(range(1, 16), used - 1))
        parts = [b - a for a, b in zip([0, *cuts], [*cuts, 16])]
        v["w"] = [p / 16 for p in parts] + [0.0] * (4 - used)


def split(rng, verts: list, tris: list) -> list[dict]:
    """Partitions: consecutive runs of triangles, their vertices (a vertex no triangle uses
    goes to one of them), a shuffled bone list and vertex map."""
    cuts = sorted(rng.sample(range(1, len(tris)), rng.randint(0, min(2, len(tris) - 1))))
    runs = [tris[a:b] for a, b in zip([0, *cuts], [*cuts, len(tris)])]
    parts = [{"tris": run, "verts": sorted({i for t in run for i in t})} for run in runs]
    for i in set(range(len(verts))) - {i for p in parts for i in p["verts"]}:
        rng.choice(parts)["verts"].append(i)
    for p in parts:
        rng.shuffle(p["verts"])
        p["bones"] = sorted({j for i in p["verts"] for j in verts[i]["j"]})
        rng.shuffle(p["bones"])
    return parts


def part_bytes(p: dict, verts: list, sse: bool) -> bytes:
    local = {g: i for i, g in enumerate(p["verts"])}
    n, tris = len(p["verts"]), p["tris"]
    written = p["bones"][: len(p["bones"]) - p.get("cut", 0)]  # cut: indices run past it
    out = struct.pack("<5H", n, len(tris), len(written), 0, 4)
    out += struct.pack(f"<{len(written)}H", *written)
    out += b"\1" + struct.pack(f"<{n}H", *p["verts"])
    weights = b"".join(struct.pack("<4f", *verts[g]["w"]) for g in p["verts"])
    out += b"\0" if p.get("bare") else b"\1" + weights
    out += b"\1" + b"".join(struct.pack("<3H", *(local[i] for i in t)) for t in tris)
    out += b"\1" + bytes(p["bones"].index(j) for g in p["verts"] for j in verts[g]["j"])
    out += bytes(2)  # LOD level, global VB
    if sse:
        out += struct.pack("<Q", DESC) + b"".join(struct.pack("<3H", *t) for t in tris)
    return out


def partition(parts: list, verts: list, sse: bool) -> bytes:
    out = struct.pack("<I", len(parts))
    if sse:
        data = b"".join(bs_vertex(v, True) for v in verts)
        out += struct.pack("<IIQ", len(data), STRIDE, DESC) + data
    return out + b"".join(part_bytes(p, verts, sse) for p in parts)


def skin(sc: Scene, root: int, bones: list, part: bytes) -> tuple[int, dict]:
    """NiSkinInstance (or its dismember kind), NiSkinData without weights, NiSkinPartition."""
    rng, n = sc.rng, len(bones)
    s2b, to_skin = [place(rng, rng.uniform(0.5, 2)) for _ in bones], place(rng, 1.5)
    inst = sc.ref(rng.choice(("NiSkinInstance", "BSDismemberSkinInstance")))
    data, held = sc.ref("NiSkinData"), sc.ref("NiSkinPartition")
    sc.blocks[inst][1] = struct.pack(f"<iiiI{n}i", data, held, root, n, *bones) + bytes(4)
    body = pack_transform(to_skin) + struct.pack("<IB", n, 0)
    sc.blocks[data][1] = body + b"".join(pack_transform(m) + bytes(18) for m in s2b)
    sc.blocks[held][1] = part
    return inst, {"s2b": s2b, "to_skin": to_skin}


def skinned(sc: Scene, model: dict, ref: int, parts_of=split) -> None:
    rng, bones = sc.rng, model["bones"]
    verts = vertices(rng, rng.randint(3, 12), len(bones))
    sixteenths(rng, verts)
    tris = [tuple(rng.randrange(len(verts)) for _ in range(3)) for _ in range(rng.randint(1, 8))]
    shade, sse = shader(sc, "BSLightingShaderProperty"), sc.stream == 100
    inst, rig = skin(sc, model["root"], bones, partition(parts_of(rng, verts, tris), verts, sse))
    av = sc.av("shape0", model["local"][ref])
    if sse:
        empty = struct.pack("<3iQHHII", inst, shade, -1, DESC, len(tris), len(verts), 0, 0)
        sc.blocks[ref][1] = av + bytes(16) + empty
    else:
        data = sc.ref("NiTriShapeData")
        sc.blocks[data][1] = tri_data(sc, verts, tris, 0x1001)
        sc.blocks[ref][1] = av + struct.pack("<iiIiBii", data, inst, 0, -1, 0, shade, -1)
    model["shapes"].append({"ref": ref, "verts": verts, "tris": tris, "rig": rig})


def make(rng, stream: int, parts_of=split) -> tuple[Scene, dict]:
    """A root, bones under it, a skinned shape from its partition and an unskinned one."""
    sc = Scene(rng, stream)
    root = sc.ref("BSFadeNode")
    bones = [sc.ref("NiNode") for _ in range(rng.randint(2, 5))]
    parent = {b: rng.choice([root, *bones[:i]]) for i, b in enumerate(bones)}
    shapes = [sc.ref("NiTriShape" if stream == 83 else "BSTriShape") for _ in range(2)]
    parent |= {s: rng.choice([root, *bones]) for s in shapes}
    local = {r: place(rng, rng.uniform(0.5, 2)) for r in [root, *bones, *shapes]}
    model = {"parent": parent, "local": local, "root": root, "bones": bones, "shapes": []}
    skinned(sc, model, shapes[0], parts_of)
    add_shape(sc, model, shapes[1], 1)
    for node in [root, *bones]:
        kids = [r for r, p in parent.items() if p == node]
        sc.blocks[node][1] = sc.av(f"node{node}", local[node])
        sc.blocks[node][1] += struct.pack(f"<I{len(kids)}iI", len(kids), *kids, 0)
    return sc, model


class PartitionTests(unittest.TestCase):
    close, check = NifModelTests.close, NifModelTests.check
    vertex_data, skinning = NifModelTests.vertex_data, NifModelTests.skinning

    def test_a_skin_from_its_partitions(self) -> None:
        rng = random.Random(43)
        for stream in (100, 83):
            for case in range(12):
                sc, model = make(rng, stream)
                with tempfile.TemporaryDirectory() as tmp:
                    nif = lay_out(Path(tmp), sc, DXT1 + bytes(8))
                    out = nifmodels.NifDecoder().decode(nif, Path(tmp) / "o", ctx())
                    self.assertEqual((out.kind, out.files, out.error), (OutcomeKind.OK, 1, ""))
                    doc, _, values = open_glb(Path(tmp) / "o" / "armor.glb")
                self.check(model, doc, values, stream)

    def test_a_partition_that_does_not_hold_is_refused(self) -> None:
        def lost(rng, verts, tris):  # a vertex in no partition
            parts = split(rng, verts, tris)
            verts.append(dict(verts[0]))
            return parts

        def past(rng, verts, tris):  # bone indices past the partition's bones
            return [p | {"cut": 1} for p in split(rng, verts, tris)]

        def bare(rng, verts, tris):  # no weights
            return [p | {"bare": True} for p in split(rng, verts, tris)]

        rng = random.Random(44)
        for parts_of, why in (
            (lost, "1 vertices are in no skin partition"),
            (past, "a skin partition's vertex points past its bones"),
            (bare, "a skin partition without its weights or bone indices: not read"),
        ):
            sc, _ = make(rng, 100, parts_of)
            with tempfile.TemporaryDirectory() as tmp:
                nif = lay_out(Path(tmp), sc, DXT1 + bytes(8))
                out = nifmodels.NifDecoder().decode(nif, Path(tmp) / "o", ctx())
            self.assertEqual(out.kind, OutcomeKind.FAILED)
            self.assertIn(why, out.error)


if __name__ == "__main__":
    unittest.main()
