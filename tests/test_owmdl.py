"""L1: DataTool's .owmdl into .glb (viwo/plugins/overwatch/owmdl.py). Properties over random
models written the way DataTool writes them: every vertex, normal, UV and index is in the
.glb, turned from Blender's axes to glTF's and V flipped back; every bone link survives, four
to a set, an empty slot weighing nothing; each bone's inverse bind matrix undoes its place in
the reference pose; the textures are the PNG files' own bytes; the vertex colour sets are kept
but never as a tint; a file cut short or of another version is refused, not half-read; the
file names say the hero and the skin."""

import json
import random
import struct
import tempfile
import unittest
from array import array
from pathlib import Path

from viwo.plugins.overwatch import owmdl

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(40))


def text(value: str) -> bytes:
    raw = value.encode()
    head = [len(raw)] if len(raw) < 128 else [len(raw) % 128 + 128, len(raw) // 128]
    return bytes(head) + raw


def write_looks(folder: Path) -> None:
    """The look, one material and its textures, laid out as DataTool lays them out."""
    for sub in ("ModelLooks", "Materials", "Textures"):
        (folder / sub).mkdir(parents=True)
    (folder / "Textures" / "colour.png").write_bytes(PNG)
    (folder / "Textures" / "normal.png").write_bytes(PNG[::-1])
    slots = ((r"..\Textures\colour.png", owmdl.ALBEDO), (r"..\Textures\normal.png", owmdl.NORMAL))
    slots += ((r"..\Textures\gone.png", 7),)
    material = struct.pack("<HHIQQI", 3, 0, 0, len(slots), 0, 9)
    material += b"".join(text(p) + struct.pack("<I", s) for p, s in slots)
    (folder / "Materials" / "m.owmat").write_bytes(material)
    look = struct.pack("<HHIQQ", 3, 0, 1, 1, 77) + text(r"..\..\Materials\m.owmat")
    (folder / "ModelLooks" / "look.owmat").write_bytes(look)


def write_model(folder: Path, rng: random.Random) -> dict:
    write_looks(folder)
    floats = lambda n: [rng.uniform(-9, 9) for _ in range(n)]  # noqa: E731
    bones = [
        (f"bone_{i:04X}", rng.randint(-1, i - 1), floats(3), [1.0, 1.0, 1.0], floats(3))
        for i in range(rng.randint(1, 6))
    ]
    count, triangles, links = rng.randint(3, 30), rng.randint(1, 12), rng.choice((0, 1, 4, 6))
    mesh = {"pos": floats(3 * count), "nor": floats(3 * count), "tan": floats(4 * count)}
    mesh |= {"uv": [floats(2 * count), floats(2 * count)], "c1": floats(4 * count)}
    pick = lambda: rng.choice((0xFFFF, rng.randrange(len(bones))))  # noqa: E731
    mesh["joints"] = [pick() for _ in range(links * count)]
    mesh["weights"] = [rng.random() for _ in range(links * count)]
    mesh["idx"] = [rng.randrange(count) for _ in range(3 * triangles)]
    data = struct.pack("<HH", 2, 0) + text(r"ModelLooks\look.owmat")
    data += text("m" * rng.choice((3, 200))) + struct.pack("<IHII", 5, len(bones), 1, 0)
    for name, parent, move, scale, euler in bones:
        data += text(name) + struct.pack("<h9f", parent, *move, *scale, *euler)
    data += text("Submesh_0") + struct.pack("<QBIIb", 77, 2, count, triangles, links)
    for key in ("pos", "nor", "tan"):
        data += array("f", mesh[key]).tobytes()
    data += b"".join(array("f", uv).tobytes() for uv in mesh["uv"])
    data += array("H", mesh["joints"]).tobytes() + array("f", mesh["weights"]).tobytes()
    data += array("f", mesh["c1"]).tobytes() * 2 + array("I", mesh["idx"]).tobytes()
    (folder / "model.owmdl").write_bytes(data)
    return {"bones": bones, "count": count, "links": links, **mesh}


def open_glb(path: Path):
    raw = path.read_bytes()
    size = struct.unpack_from("<I", raw, 12)[0]
    doc, blob = json.loads(raw[20 : 20 + size]), raw[28 + size :]

    def values(index: int, kind: str = "f") -> array:
        view = doc["bufferViews"][doc["accessors"][index]["bufferView"]]
        out = array(kind)
        out.frombytes(blob[view["byteOffset"] : view["byteOffset"] + view["byteLength"]])
        return out

    return doc, blob, values


class OwmdlTests(unittest.TestCase):
    def close(self, got, want) -> None:
        self.assertEqual(len(got), len(want))
        self.assertTrue(all(abs(a - b) < 1e-3 for a, b in zip(got, want)), (got, want))

    def test_nothing_of_the_model_is_lost_on_the_way(self) -> None:
        rng = random.Random(70)
        for case in range(25):
            with tempfile.TemporaryDirectory() as tmp:
                made = write_model(Path(tmp) / "m", rng)
                notes = owmdl.convert(Path(tmp) / "m" / "model.owmdl", Path(tmp) / "out.glb")
                doc, blob, values = open_glb(Path(tmp) / "out.glb")
                part = doc["meshes"][0]["primitives"][0]
                at = part["attributes"]
                x, y, z = (made["pos"][n::3] for n in range(3))
                self.close(values(at["POSITION"])[0::3], x)
                self.close(values(at["POSITION"])[1::3], z)  # Blender's z is glTF's y
                self.close(values(at["POSITION"])[2::3], [-v for v in y])
                self.close(values(at["TANGENT"])[3::4], made["tan"][3::4])  # handedness kept
                for n in (0, 1):
                    uv = values(at[f"TEXCOORD_{n}"])
                    self.close(uv[0::2], made["uv"][n][0::2])
                    self.close(uv[1::2], [1 - v for v in made["uv"][n][1::2]])
                self.assertEqual(list(values(part["indices"], "I")), made["idx"])
                self.assertNotIn("COLOR_0", at)  # the engine's masks are never a tint
                self.close(values(at["_COLOR_A"]), made["c1"])
                self.links(made, at, values)
                self.skeleton(made, doc, values)
                views = [doc["bufferViews"][i["bufferView"]] for i in doc["images"]]
                kept = [blob[v["byteOffset"] : v["byteOffset"] + v["byteLength"]] for v in views]
                self.assertEqual(kept, [PNG, PNG[::-1]], case)  # the files' own bytes
                self.assertEqual(notes, ())

    def links(self, made, at, values) -> None:
        links, count, sets = made["links"], made["count"], -(-made["links"] // 4)
        self.assertEqual(sum(k.startswith("JOINTS_") for k in at), sets)
        for vertex in range(count if links else 0):
            want, got = {}, {}
            for k in range(vertex * links, vertex * links + links):
                if made["joints"][k] != 0xFFFF:
                    joint = made["joints"][k]
                    want[joint] = want.get(joint, 0.0) + made["weights"][k]
            for group in range(sets):
                joints = values(at[f"JOINTS_{group}"], "H")[vertex * 4 : vertex * 4 + 4]
                weights = values(at[f"WEIGHTS_{group}"])[vertex * 4 : vertex * 4 + 4]
                for joint, weight in zip(joints, weights):
                    got[joint] = got.get(joint, 0.0) + weight
            for joint in set(want) | set(got):  # an empty slot adds nothing to bone 0
                self.assertAlmostEqual(got.get(joint, 0.0), want.get(joint, 0.0), 3)

    def skeleton(self, made, doc, values) -> None:
        """inverse bind x the bone's place in the reference pose = identity, for every bone."""
        bones = made["bones"]
        self.assertEqual(doc["skins"][0]["joints"], list(range(len(bones))))
        inverse = values(doc["skins"][0]["inverseBindMatrices"])

        def world(i: int):
            _, parent, move, scale, euler = bones[i]
            local = owmdl._matrix(move, owmdl._quaternion(euler), scale)
            return local if parent < 0 else owmdl._times(world(parent), local)

        for i, bone in enumerate(bones):
            self.assertEqual(doc["nodes"][i]["name"], bone[0])
            cols = inverse[i * 16 : i * 16 + 16]
            one = owmdl._times([[cols[c * 4 + r] for c in range(4)] for r in range(3)], world(i))
            for r in range(3):
                self.close(one[r], [float(r == c) for c in range(4)])

    def test_a_damaged_file_is_refused_and_names_say_where_a_model_sits(self) -> None:
        rng = random.Random(71)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "staging"
            skin = root / "extract-unlocks" / "Heroes" / "Tracer" / "Skin" / "Overwatch" / "Posh"
            write_model(skin / "Models" / "0000000003BB.00C", rng)
            model = skin / "Models" / "0000000003BB.00C" / "model.owmdl"
            self.assertEqual(owmdl.label(model, root), "Tracer - Overwatch - Posh - model")
            whole = model.read_bytes()
            (model.parent / "cut.owmdl").write_bytes(whole[: rng.randrange(30, len(whole) - 1)])
            (model.parent / "old.owmdl").write_bytes(struct.pack("<HH", 1, 6) + whole[4:])
            made, lost = owmdl.convert_all(root)
            self.assertEqual((made, len(lost)), (1, 2))
            self.assertTrue(any("only version 2" in why for why in lost))
            glbs = sorted(p.name for p in model.parent.glob("*.glb"))
            self.assertEqual(glbs, ["Tracer - Overwatch - Posh - model.glb"])  # nothing half-made


if __name__ == "__main__":
    unittest.main()
