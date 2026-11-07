"""Deterministic, network-free safety and math tests for historical research."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backtesting import simulate, walk_forward, report
from run_backtest import run

START=1800000000000

def candles(prices):
    return [{"end_ms":START+i*3600000,
             "open":float(price),"high":float(price)*1.01,
             "low":float(price)*.99,"close":float(price)}
            for i,price in enumerate(prices)]


class BacktestTests(unittest.TestCase):
    def test_flat_prices_no_trades_or_profit(self):
        result=simulate(candles([100]*120))
        self.assertEqual(result["end"],10000)
        self.assertEqual(result["closed_trades"],0)
        self.assertIsNone(result["win_rate_pct"])
        self.assertIsNone(result["profit_factor"])
        self.assertEqual(result["max_drawdown_pct"],0)

    def test_directional_changes_are_costed_and_limited(self):
        data=candles([100]*35+[105]*22+[90]*43)
        r=simulate(data)
        buys=[event for event in r["events"] if event[1]=="BUY"]
        self.assertLessEqual(len(buys),1)
        self.assertGreaterEqual(r["end"],0)
        self.assertTrue(all(eq>=0 for eq in r["equity"]))
        self.assertTrue(all(len(event)==4 for event in r["events"]))
        self.assertLessEqual(r["end"],10000*1.02)

    def test_chronological_holdout_not_optimized(self):
        result=walk_forward(candles([100+0.15*i for i in range(120)]))
        self.assertEqual(result["split"],84)
        self.assertEqual(result["out_of_sample"]["bar_count"],120-84+21)
        output=report(result,"BTC example")
        self.assertIn("Holdout (30%)",output)
        self.assertIn("NOT A PERFORMANCE FORECAST",output)
        self.assertIn("N/A",output)

    def test_rejects_gaps_bad_prices_and_unsafe_settings(self):
        data=candles([100]*120)
        broken=[dict(c) for c in data]
        broken[53]["end_ms"]+=3600000
        with self.assertRaises(ValueError):
            walk_forward(broken)
        broken=[dict(c) for c in data]
        broken[33]["close"]=float("nan")
        with self.assertRaises(ValueError):
            simulate(broken)
        with self.assertRaises(ValueError):
            simulate(data,position_pct=0.5)
        with self.assertRaises(ValueError):
            simulate(data,short_window=30,long_window=20)

    def test_network_failure_creates_no_reports_or_paper_ledger(self):
        def bad(_):
            raise ValueError("unavailable feed")
        bars=candles([100]*120)
        with TemporaryDirectory() as temp:
            path=Path(temp)/"backtest-results"
            with self.assertRaises(ValueError):
                run(path,START,feeds=(("binance","A",lambda _:bars),
                                      ("hyperliquid","B",bad)))
            self.assertFalse(path.exists())
            self.assertFalse((Path(temp)/"ledger").exists())

    def test_success_standalone_report_only(self):
        bars=candles([100]*120)
        with TemporaryDirectory() as temp:
            path=Path(temp)/"backtest-results"
            run(path,START,feeds=(("binance","A",lambda _:bars),
                                  ("hyperliquid","B",lambda _:bars)))
            self.assertTrue((path/"binance.md").exists())
            self.assertTrue((path/"hyperliquid.md").exists())
            self.assertFalse((Path(temp)/"ledger").exists())


if __name__=="__main__":
    unittest.main()
