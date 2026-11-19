"""L1: `[slot_policy]` (doc 8.2, 9.2). Properties: under `main_only` a slot's spare is never
bound, never promoted when the main is missing (the slot is then unbound, and says why) and
never run after the main failed; every other slot is bound as without the section; a value
that is not a policy and a slot that does not exist are said, and failover used. Under
`supplement` (see SupplementTests) both run and the spare adds what the main left."""

import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import runtime
from viwo.contracts import workspace as ws
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.core.pipeline.failover import run_with_failover
from viwo.core.wiring.binder import bind_all, bind_slot


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

            outcome, _ = run_with_failover(only, backends, call, into=None, cancel=None)
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


def _writer(backend_id: str, files: dict[str, bytes], kind: OutcomeKind, into: Path):
    """A fake backend whose call writes `files` (and a names record for the first) into `into`."""

    def write() -> Outcome:
        for rel, data in files.items():
            (into / rel).parent.mkdir(parents=True, exist_ok=True)
            (into / rel).write_bytes(data)
        if files:
            first = next(iter(files))
            (into / ws.NAMES_FILE).write_text(json.dumps({first: f"{backend_id}:{first}"}))
        return Outcome(kind, len(files), error="" if kind is OutcomeKind.OK else "broke")

    return SimpleNamespace(backend_id=backend_id, families=("unarchive",), write=write)


def _tree(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in folder.rglob("*")
        if p.is_file() and p.name != ws.NAMES_FILE
    }


class SupplementTests(unittest.TestCase):
    """`supplement` (doc 8.2): when the main succeeds the spare runs too, and the folder ends as
    the main's output plus every file of the spare's the main did not write (the main's own
    bytes win), the names record following the added files; the outcome counts them and says
    what was added or why the spare failed. A main that fails falls over as under `failover`;
    after a cancel the spare never starts; any other policy never runs the spare after an ok."""

    def test_the_spare_adds_what_the_main_left(self) -> None:
        rng = random.Random(57)
        names = [f"{d}/f{i}.bin" for d in ("a", "a/b", "c") for i in range(3)]
        for case in range(40):
            with tempfile.TemporaryDirectory() as tmp, self.subTest(case=case):
                into = Path(tmp) / "out"
                into.mkdir()
                policy = rng.choice(["supplement", "supplement", "failover"])
                outputs = {
                    b: {n: f"{b}{n}".encode() for n in rng.sample(names, rng.randint(0, 5))}
                    for b in ("m", "s")
                }
                kinds = {
                    b: rng.choice([OutcomeKind.OK, OutcomeKind.OK, OutcomeKind.FAILED])
                    for b in ("m", "s")
                }
                fakes = {b: _writer(b, outputs[b], kinds[b], into) for b in ("m", "s")}
                binding = SimpleNamespace(main="m", spare="s", policy=policy, bound=True)
                cancel = SimpleNamespace(cancelled=rng.random() < 0.2)
                ran = []
                call = lambda f: (ran.append(f.backend_id), f.write())[1]  # noqa: E731
                outcome, used = run_with_failover(binding, fakes, call, into=into, cancel=cancel)
                main_ok = kinds["m"] is OutcomeKind.OK
                if not main_ok:  # failover: the spare alone, unless cancelled
                    self.assertEqual(ran, ["m"] if cancel.cancelled else ["m", "s"])
                    continue
                self.assertEqual(used, "m")
                both = policy == "supplement" and not cancel.cancelled
                self.assertEqual(ran, ["m", "s"] if both else ["m"])
                spare_ok = both and kinds["s"] is OutcomeKind.OK
                extra = {k: v for k, v in outputs["s"].items() if k not in outputs["m"]}
                expected = {**outputs["m"], **(extra if spare_ok else {})}
                self.assertEqual(_tree(into), expected)
                self.assertEqual(outcome.files, len(expected))
                record = ws.renamed(into)
                for rel, origin in record.items():
                    self.assertTrue(origin.startswith("s:" if rel in extra else "m:"), record)
                said = " ".join(outcome.notes)
                if spare_ok and extra:
                    self.assertIn(f"added {len(extra)} file(s)", said)
                if both and not spare_ok:
                    self.assertIn("supplement s failed", said)
                self.assertFalse((into.parent / "out.viwo-main").exists())

    def test_supplement_only_on_slots_that_write_folders(self) -> None:
        backends = {"a": backend("a", True), "b": backend("b", True)}
        problems: list[str] = []
        slots = {
            "decode.x": SlotDefinition("decode.x", "decode", "core", "a", "b"),
            "pack.x": SlotDefinition("pack.x", "pack", "core", "a", "b"),
        }
        policies = {"decode.x": "supplement", "pack.x": "supplement"}
        for b in backends.values():
            b.families = ("decode", "pack")
        bindings, problems = bind_all(slots, backends, {}, None, policies)
        self.assertEqual(bindings["decode.x"].policy, "supplement")
        self.assertEqual((bindings["pack.x"].policy, bindings["pack.x"].spare), ("failover", "b"))
        self.assertTrue(any("pack.x = supplement" in p and "failover used" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
