"""L1: the worker pool of the parallel stages (core/pipeline/pool.py) and the first stage on it,
the search for nested archives. Properties: results come in the items' order whatever each
item takes; a cancel ends them early and starts nothing more; the budget is 80 % of the
processors, at least one, and VIWO_WORKERS overrides it; a large round of extracted files is
announced, finds what a serial search finds, and a zip inside a zip is still unpacked."""

import os
import random
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import runtime
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline import pool, unpack
from viwo.core.pipeline.identify import identify
from viwo.core.pipeline.runner import extract


class PoolTests(unittest.TestCase):
    def test_results_keep_the_order_and_a_cancel_ends_them(self) -> None:
        rng = random.Random(4)
        for _ in range(10):
            delays = [rng.random() / 200 for _ in range(rng.randint(1, 60))]

            def slow(i, delays=delays):
                time.sleep(delays[i])
                return i * 2

            self.assertEqual(
                list(pool.each(slow, range(len(delays)))), [i * 2 for i in range(len(delays))]
            )
        token, seen = CancelToken(), []
        for value in pool.each(lambda i: i, range(1000), token):
            seen.append(value)
            if value == 5:
                token.cancel()
        self.assertEqual(seen, list(range(6)))  # nothing after the cancel is handed on

    def test_the_budget_is_80_percent_and_can_be_set(self) -> None:
        for count in (1, 2, 4, 5, 20, 64):
            with mock.patch.object(os, "process_cpu_count", lambda c=count: c, create=True):
                with mock.patch.dict(os.environ, {"VIWO_WORKERS": ""}):
                    self.assertEqual(pool.workers(), max(1, int(count * 0.8)))
        with mock.patch.dict(os.environ, {"VIWO_WORKERS": "3"}):
            self.assertEqual(pool.workers(), 3)


class NestedSearchTests(unittest.TestCase):
    def test_a_large_round_is_said_and_matches_the_serial_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root)
            rng, items = random.Random(11), []
            for i in range(unpack.SAID_FROM + 40):
                path = root / f"f{i}{rng.choice(['.zip', '.bin', '.txt', ''])}"
                path.write_bytes(rng.choice([b"PK\x03\x04rest", b"plain", b""]))
                items.append((path, f"game:{path.name}"))
            said = []
            ctx = SimpleNamespace(log=lambda message, stage="": said.append((stage, message)))
            found = list(unpack._identified(rt, items, lambda owner: ctx, None))
            serial = [identify(path, list(rt.slots.values())) for path, _ in items]
            self.assertEqual(found, serial)
            self.assertTrue(any(m is not None for m in found))
            self.assertEqual(said[0][0], "identify")
            self.assertIn(f"{len(items):,} extracted file(s)", said[0][1])
            small = list(unpack._identified(rt, items[:5], lambda owner: 1 / 0, None))
            self.assertEqual(small, serial[:5])  # a small round: no context, nothing said

    def test_a_zip_inside_a_zip_among_many_files_is_unpacked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            inner = root / "inner.zip"
            with zipfile.ZipFile(inner, "w") as zf:
                zf.writestr("deep/secret.txt", "found")
            with zipfile.ZipFile(game / "data.zip", "w") as zf:
                for i in range(unpack.SAID_FROM + 10):
                    zf.writestr(f"notes/n{i}.md", f"note {i}")
                zf.write(inner, "packs/inner.zip")
            events = []
            request = ExtractionRequest(str(game), str(root / "ws"))
            result = extract(runtime(root), request, "j", events.append, CancelToken())
            self.assertEqual((result.archives_found, result.archives_extracted), (2, 2))
            self.assertEqual((root / "ws" / "txt" / "secret.txt").read_text(), "found")
            self.assertTrue(any("Looking for nested archives" in e.message for e in events))


if __name__ == "__main__":
    unittest.main()
