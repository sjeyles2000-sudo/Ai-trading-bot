"""Offline minute BTC breakout experiment regressions; no exchange credentials."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import minute_breakout_lab as lab


def synthetic(prices):
    start = 1_800_000_000_000
    return [{"end_ms": start + (i+1)*lab.MINUTE - 1,
             "open": float(price), "high": float(price)*1.001,
             "low": float(price)*.999, "close": float(price)}
            for i,price in enumerate(prices)]


class MinuteBreakoutTests(unittest.TestCase):
    def test_completed_five_minute_signal_never_looks_ahead(self):
        data=synthetic([100 + .002*i + .15*(i%17==0) for i in range(400)])
        original=lab.closed_bar_signals(data)
        changed=[dict(x) for x in data]
        changed[-1]["close"]*=1.1
        changed[-1]["high"]*=1.2
        altered=lab.closed_bar_signals(changed)
        for key in ("filtered","unfiltered","supports"):
            self.assertEqual(original[key][:-1],altered[key][:-1])

    def test_flat_market_has_no_fabricated_profit(self):
        data=synthetic([100]*1000)
        results=lab.compare(data)
        for strategy in ("filtered","unfiltered"):
            for phase in ("train","holdout","double_cost"):
                self.assertEqual(results[strategy][phase]["net_return_pct"],0)
                self.assertEqual(results[strategy][phase]["trades"],0)
                self.assertIsNone(results[strategy][phase]["win_pct"])

    def test_reject_missing_and_bad_candles(self):
        bars=synthetic([100]*500)
        gap=[dict(x) for x in bars]
        gap[200]["end_ms"] += lab.MINUTE
        with self.assertRaises(lab.MarketDataError):
            lab.validate(gap)
        bad=[dict(x) for x in bars]
        bad[300]["low"]=float("nan")
        with self.assertRaises(lab.MarketDataError):
            lab.validate(bad)

    def test_next_open_entry_and_same_bar_stop_priority(self):
        bars=synthetic([100]*330)
        # Signal on bar 300, next bar opens above prior support; both stop
        # and 3R target touched during the next candle, so stop must win.
        bars[300].update(open=100., high=100.2, low=99.95, close=100.2)
        bars[301].update(open=100.2, high=103., low=99.95, close=100.3)
        signals={"filtered":[False]*len(bars),
                 "unfiltered":[False]*len(bars),
                 "supports":[None]*len(bars)}
        signals["filtered"][300]=True
        signals["supports"][300]=99.95
        out=lab.simulate(bars,"filtered",first=301,last=320,
                         signal_data=signals)
        self.assertEqual(out["entries"],1)
        self.assertEqual(out["trades"],1)
        self.assertLess(out["net_return_pct"],0)

    def test_invalid_costs_are_rejected(self):
        bars=synthetic([100]*500)
        with self.assertRaises(ValueError):
            lab.simulate(bars,fee=-.1)
        with self.assertRaises(ValueError):
            lab.simulate(bars,strategy="unknown")

    def test_both_venues_required_before_report(self):
        bars=synthetic([100]*1000)
        def bad(_):
            raise lab.MarketDataError("Public feed unavailable")
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"report.md"
            with self.assertRaises(lab.MarketDataError):
                lab.run(path,feeds={"Binance":lambda _:bars,
                                    "Hyperliquid":bad})
            self.assertFalse(path.exists())
            self.assertFalse((Path(tmp)/"ledger").exists())

if __name__=="__main__":
    unittest.main()
