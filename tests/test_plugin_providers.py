"""L3: what built-in plugins provide to core beyond their slots (doc 2.2, 0.4, 5.1).

Properties, over random synthetic fixtures:

1. Source keeps an inventory: every member its VPK directories list. After an extraction,
   `inventoryItems` counts the listed members of the extensions the run selected and
   `collectedFromInventory` exactly the ones that came out (a member in a missing part file
   does not); every missing one is counted in a verify warning that names the first ones,
   and a run with nothing missing passes verify.
2. Ren'Py ships the sanitizer rule `renpy.cache`: in a plan, exactly the non-empty `.rpyb`
   files (any case) are its findings, each a `trash`; it is in the safe recipe, the plugin
   reports the `sanitize` and Source the `inventory` capability.
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime
from tests.test_formats import vpk
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core import sanitizer
from viwo.core.pipeline.runner import extract
from viwo.core.sanitizer_rules import collect_rules
from viwo.core.wiring.conformance import capabilities_of
from viwo.plugins.source import listed

EXTS = ("txt", "vmt", "cfg", "res")


def _members(rng: random.Random) -> dict[str, tuple[bytes, int]]:
    """Distinct member paths -> (bytes, 0 inline or 1 in part 000)."""
    names = {
        f"{rng.choice(['materials', 'scripts', 'cfg/sub'])}/m{i}.{rng.choice(EXTS)}"
        for i in range(rng.randint(1, 8))
    }
    return {n: (f"{n}:{rng.random()}".encode(), rng.randint(0, 1)) for n in sorted(names)}


class SourceInventoryTests(unittest.TestCase):
    def test_inventory_counts_what_came_out_and_names_what_did_not(self) -> None:
        rng = random.Random(71)
        for case in range(8):
            with tempfile.TemporaryDirectory() as tmp, self.subTest(case=case):
                root = Path(tmp)
                game, sets = root / "game", {}
                for k in range(rng.randint(1, 3)):
                    members = _members(rng)
                    vdir, v000 = vpk(members)
                    folder = game / rng.choice(["hl2", "tf", "tf/custom"])
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / f"p{k}_dir.vpk").write_bytes(vdir)
                    part = rng.random() < 0.6
                    if part:
                        (folder / f"p{k}_000.vpk").write_bytes(v000)
                    rel = (folder / f"p{k}_dir.vpk").relative_to(game).as_posix()
                    sets[rel] = {m: where == 0 or part for m, (_, where) in members.items()}
                selected = (
                    frozenset(f".{e}" for e in rng.sample(EXTS, 2)) if rng.random() < 0.3 else None
                )
                expected = {
                    f"{rel}/{m}": out
                    for rel, members in sets.items()
                    for m, out in members.items()
                    if selected is None or Path(m).suffix in selected
                }
                self.assertLessEqual(set(expected), set(listed(game)))
                request = ExtractionRequest(str(game), str(root / "ws"), selected_exts=selected)
                result = extract(runtime(root), request, "j", lambda e: None, CancelToken())
                run = next(r for r in result.runs if r.plugin_id == "source")
                missing = sum(not out for out in expected.values())
                self.assertEqual(
                    (run.inventory_items, run.inventory_found),
                    (len(expected), len(expected) - missing),
                )
                said = [w for w in run.warnings if "inventory item(s) not collected" in w]
                self.assertEqual(len(said), 1 if missing else 0, run.warnings)
                if missing:
                    self.assertIn(f"{missing} of {len(expected)}", said[0])
                    first = min(k for k, out in expected.items() if not out)
                    self.assertIn(first, said[0])
                legacy = result.to_legacy_dict()
                self.assertEqual(legacy["inventoryItems"], len(expected))
                self.assertEqual(legacy["collectedFromInventory"], len(expected) - missing)

    def test_a_damaged_directory_lists_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / "a_dir.vpk").write_bytes(b"\x34\x12\xaa\x55\x01")  # magic, cut short
            (game / "a_000.vpk").write_bytes(b"part, no magic")
            self.assertEqual(listed(game), [])


class RenPyCacheRuleTests(unittest.TestCase):
    def test_exactly_the_non_empty_rpyb_files_are_trashed(self) -> None:
        rng = random.Random(73)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root)
            rules = collect_rules(rt)
            self.assertIn("renpy.cache", sanitizer.recipes(rules)[0]["rules"])
            self.assertIn("sanitize", capabilities_of(rt.plugins["renpy"]))
            self.assertIn("inventory", capabilities_of(rt.plugins["source"]))
            for case in range(6):
                ws = root / f"ws{case}"
                (ws / ".viwo-workspace").parent.mkdir(parents=True)
                (ws / ".viwo-workspace").write_text("")
                cache = set()
                for i in range(rng.randint(1, 12)):
                    ext = rng.choice([".rpyb", ".RPYB", ".rpyc", ".rpy", ".bin"])
                    path = ws / ext[1:].lower() / f"f{i}{ext}"
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(rng.randbytes(rng.choice([0, 3, 40])))
                    if ext.lower() == ".rpyb" and path.stat().st_size:
                        cache.add(path.relative_to(ws).as_posix())
                plan = sanitizer.plan(ws, rules=rules)
                mine = [f for f in plan["findings"] if f["rule"] == "renpy.cache"]
                self.assertEqual({f["path"] for f in mine}, cache)
                self.assertTrue(all(f["action"] == "trash" for f in mine))


if __name__ == "__main__":
    unittest.main()
