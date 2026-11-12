"""Network-free regression checks for execution-stress research only."""
import unittest
from execution_stress import check_candles, run_stress, compare, report


def prices(n=160):
    p = [100.] * 32 + [100 + .7 * j for j in range(30)]
    p += [121 - .9 * j for j in range(32)]
    p += [92 + .4 * j for j in range(n-len(p))]
    return [{"end_ms": 1800000000000 + i*3600000, "open": v,
             "high": v*1.01, "low": v*.99, "close": v} for i, v in enumerate(p)]


class ExecutionStressTests(unittest.TestCase):
    def test_flat_prices_never_trade(self):
        bars = [{"end_ms": 1800000000000+i*3600000,
                 "open": 100, "high": 101, "low": 99, "close": 100}
                for i in range(160)]
        result = run_stress(bars)
        self.assertEqual(result["ending_equity"], 10000)
        self.assertEqual(result["closed_trades"], 0)

    def test_doubled_costs_are_worse_for_same_signals(self):
        bars = prices()
        base = run_stress(bars)
        double = run_stress(bars, fee=.002, slippage=.001)
        self.assertTrue(any(e[1] == "BUY" for e in base["events"]))
        self.assertLessEqual(double["ending_equity"], base["ending_equity"] + .0001)

    def test_outage_never_fills_during_block(self):
        bars = prices()
        r = run_stress(bars, outages=range(32,64))
        self.assertTrue(all(e[0] not in range(32,64) for e in r["events"]))

    def test_stale_or_bad_inputs_rejected(self):
        bars = prices()
        for overrides in ({"fee": float("nan")}, {"slippage": -.01},
                          {"delay": 4}, {"outages": [-1]},
                          {"outages": [len(bars)]}):
            with self.assertRaises(ValueError):
                run_stress(bars, **overrides)
        bad = [dict(x) for x in bars]
        bad[50]["end_ms"] += 3600000
        with self.assertRaises(ValueError):
            check_candles(bad)

    def test_five_scenarios_and_caveats(self):
        bars = prices()
        self.assertEqual(len(compare(bars)), 5)
        text = report(bars)
        self.assertIn("NO REAL OR PAPER TRADES", text)
        self.assertIn("Combined stress", text)
        self.assertIn("NOT", text)


if __name__ == "__main__":
    unittest.main()
