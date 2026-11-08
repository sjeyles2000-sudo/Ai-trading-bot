"""Synthetic offline tests. These do not establish trading profitability."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from price_action import simulate, walk_forward
from compare_price_action import run

START = 1800000000000


def candles(closes):
    return [{"end_ms": START + 3600000 * i,
             "open": float(p), "high": float(p) * 1.001,
             "low": float(p) * 0.999, "close": float(p)}
            for i, p in enumerate(closes)]


class PriceActionTests(unittest.TestCase):
    def test_flat_market_never_trades(self):
        result = simulate(candles([100] * 120))
        self.assertEqual(result["end"], 10000)
        self.assertFalse(result["events"])
        self.assertIsNone(result["win_rate_pct"])

    def test_no_signal_uses_future_bar(self):
        bars = candles([100] * 25 + [105, 104.9] + [105] * 73)
        first = simulate(bars[:45])
        second = simulate(bars[:46])
        self.assertTrue(all(item[0] >= "2027" for item in second["events"]))
        self.assertLessEqual(first["bar_count"], second["bar_count"])

    def test_walk_forward_preserves_holdout(self):
        result = walk_forward(candles([100] * 120))
        self.assertEqual(result["split"], 84)
        self.assertEqual(result["out_of_sample"]["bar_count"], 120 - 84 + 24)
        self.assertEqual(result["out_of_sample"]["end"], 10000)

    def test_reject_bad_data(self):
        bars = candles([100] * 120)
        bars[40]["close"] = float("nan")
        with self.assertRaises(ValueError):
            simulate(bars)

    def test_failed_feed_never_writes_results_or_ledger(self):
        bars = candles([100] * 120)
        def bad(_):
            raise ValueError("no data")
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "results"
            with self.assertRaises(ValueError):
                run(path, START, (("binance", "Binance", lambda _: bars),
                                  ("hyperliquid", "Hyperliquid", bad)))
            self.assertFalse(path.exists())
            self.assertFalse((Path(tmp) / "ledger").exists())

    def test_comparison_reports_are_research_only(self):
        bars = candles([100] * 120)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "results"
            run(path, START, (("binance", "Binance", lambda _: bars),
                              ("hyperliquid", "Hyperliquid", lambda _: bars)))
            self.assertIn("Breakout + retest", (path / "binance.md").read_text())
            self.assertFalse((Path(tmp) / "ledger").exists())


if __name__ == "__main__":
    unittest.main()
