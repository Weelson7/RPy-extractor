"""L2: failover gives every attempt a fresh folder and never starts the spare after a cancel
(doc 8.2).

Properties, over random main outcomes (ok, failed, unavailable, needs_key, an exception),
random leftovers of the main (a truncated file, an export map, nested folders) and a random
cancel while the main runs:

1. The spare runs exactly when the main's outcome is retryable, a spare is bound and the run
   was not cancelled.
2. After the call, the folder holds exactly what the backend whose outcome is returned wrote:
   nothing of a failed main is left beside the spare's files.
3. `into` and `cancel` are required: a call without them is a TypeError, and every caller in
   ViWo names both (a probe, which writes nothing, says `into=None`).
4. The stages follow: EXPORT's staging, a CARVE folder and a DECODE folder hold the spare's
   files only after the main failed there; CARVE and DECODE start no spare after a cancel.
"""

from __future__ import annotations

import ast
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import ROOT
from viwo.contracts import Outcome, OutcomeKind
from viwo.contracts import workspace as ws
from viwo.contracts.pipeline import CarveMode
from viwo.contracts.slots import SlotBinding
from viwo.contracts.types import CancelToken
from viwo.core.pipeline.failover import run_with_failover

KINDS = [OutcomeKind.OK, OutcomeKind.FAILED, OutcomeKind.UNAVAILABLE, OutcomeKind.NEEDS_KEY]


def _files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


class Fake:
    """A backend of any family: writes `files` into the folder it is given, then answers."""

    def __init__(self, name: str, files: dict[str, bytes], kind, token=None, raises=False):
        self.name, self.files, self.kind, self.calls = name, files, kind, 0
        self.token, self.raises = token, raises

    def _write(self, folder: Path) -> Outcome:
        self.calls += 1
        for rel, data in self.files.items():
            (folder / rel).parent.mkdir(parents=True, exist_ok=True)
            (folder / rel).write_bytes(data)
        if self.token is not None:
            self.token.cancel()  # the user stops the run while this backend works
        if self.raises:
            raise OSError("disk went away")
        return Outcome(self.kind, len(self.files), error="" if self.kind.value == "ok" else "no")

    def export(self, ctx):
        return self._write(ctx.staging)

    def carve(self, path, dest, ctx):
        return self._write(dest)

    def decode(self, path, dest, ctx):
        return self._write(dest)


def _leftovers(rng: random.Random) -> dict[str, bytes]:
    out = {f"part{i}.png": rng.randbytes(rng.randint(0, 40)) for i in range(rng.randint(0, 3))}
    if rng.random() < 0.5:
        out[ws.EXPORT_MAP] = b'{"part0.png": ["c.pak", "a/b.png"]}'
    if rng.random() < 0.5:
        out["deep/er/truncated.wav"] = b"RIFF\x00"
    return out


class FailoverPropertyTests(unittest.TestCase):
    def test_each_attempt_starts_empty_and_a_cancel_stops_the_spare(self) -> None:
        rng = random.Random(71)
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(60):
                into = Path(tmp) / f"c{i}"
                if rng.random() < 0.5:  # a folder used before: emptied too
                    (into / "old").mkdir(parents=True)
                    (into / "old" / "stale.bin").write_bytes(b"x")
                token = CancelToken() if rng.random() < 0.7 else None
                stop = token if token is not None and rng.random() < 0.4 else None
                kind, raises = rng.choice(KINDS), rng.random() < 0.15
                main = Fake("m", _leftovers(rng), kind, stop, raises)
                spare = Fake("s", {"good.png": b"png"}, OutcomeKind.OK)
                spare_id = "s" if rng.random() < 0.8 else ""
                binding = SlotBinding("x", "m", spare_id)
                backends = {"m": main, "s": spare}
                out, used = run_with_failover(
                    binding, backends, lambda b: b._write(into), into=into, cancel=token
                )
                failed = raises or kind in (OutcomeKind.FAILED, OutcomeKind.UNAVAILABLE)
                expect = failed and bool(spare_id) and stop is None
                with self.subTest(kind=kind, raises=raises, spare=spare_id, cancel=bool(stop)):
                    self.assertEqual(spare.calls, int(expect))
                    self.assertEqual(used, "s" if expect else "m")
                    want = spare.files if expect else main.files
                    self.assertEqual(_files(into), want)  # nothing of another attempt
                    self.assertEqual(bool(out.fallback), expect)  # never silent

    def test_into_and_cancel_are_required_and_every_caller_names_both(self) -> None:
        binding, backends = SlotBinding("x", "m"), {"m": Fake("m", {}, OutcomeKind.OK)}
        for missing in ({"into": None}, {"cancel": None}, {}):
            with self.assertRaises(TypeError):
                run_with_failover(binding, backends, lambda b: b, **missing)
        callers = 0
        for path in (ROOT / "viwo").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") == (
                    "run_with_failover"
                ):
                    callers += 1
                    named = {k.arg for k in node.keywords}
                    self.assertLessEqual({"into", "cancel"}, named, f"{path.name}:{node.lineno}")
        # unpack, export, carve, decode x2, analysis, capture, repack pack and verify, merger
        self.assertGreaterEqual(callers, 10)


class StageTests(unittest.TestCase):
    def _run(self, root: Path, backends: dict, slot: str, cancel=None) -> SimpleNamespace:
        rt = SimpleNamespace(
            bindings={slot: SlotBinding(slot, "m", "s")},
            backends=backends,
            slots={},
            plugins={
                "p": SimpleNamespace(export_slot=lambda: slot, manifest=SimpleNamespace(name="P"))
            },
        )
        ctx = SimpleNamespace(staging=root / "staging" / "p", cancel=cancel)
        return SimpleNamespace(
            rt=rt,
            detections={"p": None},
            ctx=lambda owner, game=None: ctx,
            log=lambda *a, **k: None,
            cancel=cancel or CancelToken(),
            work=root / "work",
            request=SimpleNamespace(carve=CarveMode.ALL),
        )

    def test_export_carve_and_decode_collect_only_the_spares_files(self) -> None:
        from viwo.core.decode import _decode_one
        from viwo.core.pipeline.carving import carve_all
        from viwo.core.pipeline.export import export_one, kinds

        rng = random.Random(73)
        for _ in range(4):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                left = {**_leftovers(rng), ws.EXPORT_MAP: b"{}", "cut.png": b"\x89PN"}
                good = {f"ok{i}.ogg": rng.randbytes(9) for i in range(rng.randint(1, 3))}
                pair = lambda: {  # noqa: E731
                    "m": Fake("m", left, OutcomeKind.FAILED),
                    "s": Fake("s", good, OutcomeKind.OK),
                }
                run = self._run(root, pair(), "export.p")
                done = export_one(run, "p")
                self.assertEqual(_files(root / "staging" / "p"), good)
                self.assertEqual(done.backend, "s")
                self.assertEqual(kinds(root / "staging" / "p"), {"ogg": len(good)})
                blob = root / "blob.bin"
                blob.write_bytes(rng.randbytes(2048))
                run = self._run(root, pair(), "carve.signatures")
                report = carve_all(run, frozenset(), [(blob, "game:blob.bin")])
                self.assertEqual([_files(d) for d in report.origins], [good])
                run = self._run(root, pair(), "decode.audio")
                (run.work).mkdir(exist_ok=True)
                source, _ = _decode_one(run, None, root, "blob.bin", "decode.audio")
                self.assertEqual(_files(source.root), good)

    def test_carve_and_decode_start_no_spare_after_a_cancel(self) -> None:
        from viwo.core.decode import _decode_one
        from viwo.core.pipeline.carving import carve_all

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blob = root / "blob.bin"
            blob.write_bytes(bytes(2048))
            for stage in ("carve.signatures", "decode.audio"):
                token = CancelToken()
                spare = Fake("s", {"a.wav": b"w"}, OutcomeKind.OK)
                backends = {"m": Fake("m", {"x": b"1"}, OutcomeKind.FAILED, token), "s": spare}
                run = self._run(root, backends, stage, token)
                run.work.mkdir(exist_ok=True)
                if stage == "carve.signatures":
                    report = carve_all(run, frozenset(), [(blob, "game:blob.bin")])
                    self.assertEqual(report.origins, {})
                else:
                    found = _decode_one(run, None, root, "blob.bin", stage)
                    self.assertIsNone(found[0])
                self.assertEqual(spare.calls, 0, stage)


if __name__ == "__main__":
    unittest.main()
