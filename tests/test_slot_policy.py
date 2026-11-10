"""L1: `[slot_policy]` (doc 8.2, 9.2). Properties: under `main_only` a slot's spare is never
bound, never promoted when the main is missing (the slot is then unbound, and says why) and
never run after the main failed; every other slot is bound as without the section; a value
that is not a policy and a slot that does not exist are said, and failover used."""

import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.core.pipeline.failover import run_with_failover
from viwo.core.wiring.binder import bind_slot


def backend(backend_id: str, there: bool):
    why = (there, "" if there else "tool missing")
    return SimpleNamespace(backend_id=backend_id, families=("decode",), available=lambda os: why)


class PolicyTests(unittest.TestCase):
    def test_main_only_never_binds_promotes_or_runs_the_spare(self) -> None:
        rng = random.Random(53)
        slot = SlotDefinition("decode.x", "decode", "core", "a", "b")
        for _ in range(40):
            main_there, spare_there = rng.random() < 0.5, rng.random() < 0.5
            backends = {"a": backend("a", main_there), "b": backend("b", spare_there)}
            free = bind_slot(slot, backends, None, None)
            only = bind_slot(slot, backends, None, None, "main_only")
            self.assertEqual((only.policy, only.spare, only.promoted), ("main_only", "", False))
            self.assertEqual(only.main, "a" if main_there else "")
            self.assertEqual(free.main, "a" if main_there else ("b" if spare_there else ""))
            if not main_there:
                self.assertTrue(any("a unavailable" in r for r in only.reasons))  # said
            called = []

            def call(found, called=called):
                called.append(found.backend_id)
                return Outcome(OutcomeKind.FAILED, error="broke")

            outcome, _ = run_with_failover(only, backends, call)
            self.assertEqual(called, ["a"] if main_there else [])
            self.assertFalse(outcome.ok)

    def test_the_ini_section_binds_those_slots_and_only_those(self) -> None:
        rng = random.Random(54)
        with tempfile.TemporaryDirectory() as tmp:
            base = runtime(Path(tmp))
            both = [s for s, b in sorted(base.bindings.items()) if b.main and b.spare]
            chosen = rng.sample(both, min(4, len(both)))
            body = "[plugins]\ngeneric = on\n[slot_policy]\n"
            body += "".join(f"{s} = Main_Only\n" for s in chosen)
            body += f"{both[-1]}x = main_only\n{chosen[0]}.y = sometimes\n"
            rt = runtime(Path(tmp), body)
            for slot, was in base.bindings.items():
                now = rt.bindings[slot]
                if slot in chosen:
                    self.assertEqual((now.main, now.spare, now.policy), (was.main, "", "main_only"))
                else:
                    kept = (was.main, was.spare, "failover")
                    self.assertEqual((now.main, now.spare, now.policy), kept)
            self.assertTrue(any("unknown slot" in p and "slot_policy" in p for p in rt.problems))
            self.assertTrue(any("sometimes" in p and "failover used" in p for p in rt.problems))
            self.assertEqual(rt.info()["slots"][chosen[0]]["policy"], "main_only")


if __name__ == "__main__":
    unittest.main()
