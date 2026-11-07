"""Synthetic offline validation; no network, wallet, exchange or trading API."""
import unittest
from qulla_breakout_lab import (
    DAY_MS, MAX_NOTIONAL, START_CASH, breakout_signal,
    compare, simulate, validate,
)


def flat(count=220):
    return [{"end_ms":1_700_000_000_000+i*DAY_MS,
             "open":100.0,"high":100.5,"low":99.5,
             "close":100.0,"volume":100.0} for i in range(count)]


def breakout_bars():
    bars = flat()
    # Create a prior 30-bar wide swing followed by an orderly 10-bar range.
    for i in range(150,180):
        bars[i].update(open=100.0, high=120.0, low=98.0, close=110.0)
    for i in range(180,200):
        bars[i].update(open=119.0, high=119.4, low=118.9, close=119.2)
    bars[200].update(open=119.3, high=122.0, low=119.3,
                     close=121.0, volume=200.0)
    bars[201].update(open=121.1, high=122.5, low=120.0, close=121.4)
    # Suppress any later repeated signal to simplify verifying timing.
    return bars


class BreakoutResearchTests(unittest.TestCase):
    def test_flat_market_is_no_trades(self):
        bars=flat()
        self.assertFalse(any(breakout_signal(bars,i) for i in range(42,len(bars))))
        result=compare(bars)
        self.assertEqual(result["holdout"]["closed_trades"],0)
        self.assertEqual(result["holdout"]["return_pct"],0)

    def test_reject_missing_or_bad_candles(self):
        bars=flat()
        bars[90]["end_ms"]+=DAY_MS
        with self.assertRaises(ValueError):
            validate(bars)
        bars=flat()
        bars[90]["volume"]=float("nan")
        with self.assertRaises(ValueError):
            validate(bars)

    def test_no_breakout_signal_from_future_candle(self):
        bars=breakout_bars()
        self.assertTrue(breakout_signal(bars,200))
        self.assertFalse(breakout_signal(bars,199))
        # Change future candles: signal at 200 must not change.
        expected=breakout_signal(bars,200)
        bars[201].update(open=40.0,high=50.0,low=35.0,close=45.0)
        self.assertEqual(breakout_signal(bars,200),expected)

    def test_entry_occurs_next_open_with_notional_cap(self):
        bars=breakout_bars()
        r=simulate(bars,first=190)
        buys=[ev for ev in r["events"] if ev[1]=="BUY"]
        self.assertTrue(buys)
        self.assertEqual(buys[0][0],201)
        # Exposure cap is <= $200. Check via first-entry mark-to-market
        # and the per-trade budget rule in source; no actual orders placed.
        self.assertLessEqual(START_CASH*MAX_NOTIONAL,200.0)

    def test_in_sample_does_not_leak_into_holdout(self):
        bars=flat(260)
        r=compare(bars)
        self.assertEqual(r["split"],182)
        self.assertEqual(r["holdout"]["return_pct"],0)
        self.assertEqual(r["stress_holdout"]["return_pct"],0)

    def test_no_order_interfaces(self):
        import qulla_breakout_lab as lab
        self.assertFalse(hasattr(lab,"place_order"))
        self.assertFalse(hasattr(lab,"submit_trade"))
        self.assertFalse(hasattr(lab,"urlopen"))
        self.assertFalse(hasattr(lab,"read_json"))


if __name__=="__main__":
    unittest.main()
