"""Offline deterministic safety tests for isolated Trendilo research."""
import unittest
from trendilo_lab import validate, indicators, simulate, compare, render, run, HISTORY
from tempfile import TemporaryDirectory
from pathlib import Path

ORIGIN=1_780_000_000_000
def bars(prices):
    return [{"end_ms":ORIGIN+i*3_600_000,
             "open":float(p),"high":float(p)*1.01,
             "low":float(p)*.99,"close":float(p)} for i,p in enumerate(prices)]

class TrendiloResearchTests(unittest.TestCase):
    def test_flat_market_has_no_magic_profit(self):
        b=bars([100]*240)
        r=compare(b)
        for strategy in r:
            for segment in r[strategy].values():
                self.assertAlmostEqual(segment["return_pct"],0)
                self.assertEqual(segment["buys"],0)
                self.assertIsNone(segment["win_pct"])

    def test_no_future_leak_in_signal_inputs(self):
        data=bars([100+0.1*i+2*(i%13==0) for i in range(230)])
        o1,u1,l1,a1=indicators(data)
        altered=[dict(x) for x in data]
        altered[-1]["close"]+=40
        altered[-1]["high"]+=40
        o2,u2,l2,a2=indicators(altered)
        self.assertEqual(o1[-2],o2[-2])
        self.assertEqual(u1[-2],u2[-2])
        self.assertEqual(a1[-2],a2[-2])

    def test_reject_incorrect_candles(self):
        b=bars([100]*200)
        bad=[dict(x) for x in b]
        bad[30]["end_ms"]+=120000
        with self.assertRaises(ValueError):
            validate(bad)
        bad=[dict(x) for x in b]
        bad[45]["close"]=float("nan")
        with self.assertRaises(ValueError):
            validate(bad)
        with self.assertRaises(ValueError):
            simulate(b,"trendilo",fee=-.01)

    def test_cost_and_position_controls(self):
        prices=[100+.2*i+2*(i%17==0) for i in range(300)]
        b=bars(prices)
        r=simulate(b,"trendilo")
        stress=simulate(b,"trendilo",fee=.002,slip=.001)
        self.assertGreaterEqual(r["buys"],0)
        self.assertLessEqual(r["drawdown_pct"],100)
        self.assertGreaterEqual(stress["drawdown_pct"],0)
        self.assertIsInstance(r["return_pct"],float)

    def test_fail_closed_does_not_write_report(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/"out"/"REPORT.md"
            def invalid(_):
                raise ValueError("No exchange data")
            with self.assertRaises(ValueError):
                run(path,feeds={"binance":lambda _:bars([100]*240),"hyperliquid":invalid})
            self.assertFalse(path.exists())

    def test_offline_report_only(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/"research"/"REPORT.md"
            result=run(path,feeds={"binance":lambda _:bars([100]*240),
                                   "hyperliquid":lambda _:bars([100]*240)})
            self.assertEqual(set(result),{"binance","hyperliquid"})
            self.assertIn("SMA",path.read_text())
            self.assertFalse((Path(temp)/"ledger").exists())

if __name__=="__main__":
    unittest.main()
