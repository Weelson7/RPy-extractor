"""L0: the parallel test runner of the commit pipeline (tools/run_tests.py). Properties over
random module lists and outcomes: every module runs exactly once; the SERIAL ones run after the
pool, one at a time, in the given order; any failing module makes the exit 1 and is named with
its whole output; the tests and skips counted are the sum of what unittest said per module."""

import contextlib
import importlib.util
import io
import random
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("run_tests", ROOT / "tools" / "run_tests.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunTestsTests(unittest.TestCase):
    def test_every_module_once_serial_last_failures_named_counts_summed(self) -> None:
        rng = random.Random(8)
        serial = sorted(runner.SERIAL)
        for case in range(40):
            plain = [f"tests.test_fake{i}" for i in range(rng.randint(0, 12))]
            picked = rng.sample(plain + serial, rng.randint(1, len(plain) + len(serial)))
            fails = {m for m in picked if rng.random() < 0.2}
            tests = {m: rng.randint(0, 9) for m in picked}
            skips = {m: rng.randint(0, tests[m]) for m in picked}
            order, lock = [], threading.Lock()

            def run(module, fails=fails, tests=tests, skips=skips, order=order, lock=lock):
                with lock:
                    order.append(module)
                skipped = f" (skipped={skips[module]})" if skips[module] else ""
                verdict = "FAILED" if module in fails else "OK"
                out = f"Ran {tests[module]} tests in 0.1s\n\n{verdict}{skipped}\n"
                return module, int(module in fails), out, 0.1

            printed = io.StringIO()
            with mock.patch.object(runner, "run", run), contextlib.redirect_stdout(printed):
                code = runner.main(picked)
            self.assertEqual(sorted(order), sorted(picked), case)  # every module, once
            tail = [m for m in order if m in runner.SERIAL]
            self.assertEqual(order[len(order) - len(tail) :], tail, case)  # serial after the pool
            self.assertEqual(tail, [m for m in picked if m in runner.SERIAL], case)
            self.assertEqual(code, 1 if fails else 0, case)
            text = printed.getvalue()
            for module in fails:
                self.assertIn(f"===== {module} =====", text)
            self.assertIn(f"Ran {sum(tests.values())} tests in {len(picked)} modules", text)
            self.assertIn(f"(skipped={sum(skips.values())})", text)

    def test_a_real_module_runs_and_a_missing_one_fails(self) -> None:
        module, code, out, _ = runner.run("tests.test_version")
        self.assertEqual((module, code), ("tests.test_version", 0), out)
        self.assertEqual(runner.counts(out)[0] > 0, True)
        self.assertNotEqual(runner.run("tests.test_no_such_module")[1], 0)


if __name__ == "__main__":
    unittest.main()
