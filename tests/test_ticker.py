"""L1: throttled progress ticker (real counts, bounded event rate)."""

from __future__ import annotations

import unittest
from unittest import mock

from viwo.core.pipeline.ticker import Ticker


class TickerTests(unittest.TestCase):
    def test_throttles_and_reports_real_counts(self) -> None:
        said: list[str] = []
        clock = iter([0.0, 0.2, 0.5, 1.1, 1.3, 2.4])
        with mock.patch("viwo.core.pipeline.ticker.time.monotonic", lambda: next(clock)):
            ticker = Ticker(said.append, "Decoded files:", total=5)
            for _ in range(5):
                ticker.tick(note="x")
        self.assertEqual(said, ["Decoded files: 3 / 5 (x)", "Decoded files: 5 / 5 (x)"])
        Ticker(None, "quiet").tick()  # no sink: nothing to call, no error


if __name__ == "__main__":
    unittest.main()
