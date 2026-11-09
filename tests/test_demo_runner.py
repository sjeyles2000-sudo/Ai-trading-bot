"""Local-only tests for persistent paper account and fail-closed data validation."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import demo_runner as demo
from bot import MarketDataError, INTERVAL_MS

NOW = 1800000000000


def candles(prices):
    start = NOW - len(prices) * INTERVAL_MS
    return [{"end_ms": start + (i + 1) * INTERVAL_MS - 1,
             "open": float(p), "high": float(p) * 1.005,
             "low": float(p) * 0.995, "close": float(p)}
            for i, p in enumerate(prices)]


class TestDemoRunner(TestCase):
    def test_no_retroactive_start_and_no_duplicate_candle(self):
        data = candles([100.] * 28 + [101.] * 2)
        initial = demo.empty_account()
        next_state, events, snapshots = demo.process_candles("test", initial, data)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(next_state["last_candle_ms"], data[-1]["end_ms"])
        again, e2, s2 = demo.process_candles("test", next_state, data)
        self.assertEqual(again, next_state)
        self.assertEqual(e2, [])
        self.assertEqual(s2, [])

    def test_virtual_entry_stop_and_safe_position_sizing(self):
        # Close on bar 30 triggers an entry at bar 31 open; bar 32 stops it.
        prices = [100] * 30 + [104, 104, 90] + [90] * 3
        data = candles(prices)
        state = demo.empty_account()
        state["last_candle_ms"] = data[29]["end_ms"]
        after, trades, snapshots = demo.process_candles("test", state, data)
        self.assertEqual([e[2] for e in trades], ["BUY", "STOP SELL"])
        self.assertEqual(after["units"], 0)
        self.assertEqual(len(snapshots), 6)
        self.assertGreaterEqual(after["cash"], 0)
        self.assertLessEqual(float(trades[0][3]) * float(trades[0][4]), 200)

    def test_uses_completed_signal_and_next_open_not_same_close(self):
        data = candles([100] * 30 + [110, 105])
        state = demo.empty_account()
        state["last_candle_ms"] = data[29]["end_ms"]
        after, events, snapshots = demo.process_candles("test", state, data)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual([event[2] for event in events], ["BUY"])
        self.assertAlmostEqual(float(events[0][4]), 105 * (1 + demo.SLIPPAGE_PCT), places=3)
        self.assertEqual(events[0][0], demo.timestamp(data[31]["end_ms"] - INTERVAL_MS + 1))
        self.assertGreater(after["units"], 0)

    def test_bearish_signal_exits_at_following_open(self):
        data = candles([100] * 30 + [110, 110, 50, 79])
        # Use a very low existing stop to isolate the SMA signal exit.
        state = demo.empty_account()
        state.update(cash=9800.0, units=2.0, entry_price=100.0,
                     stop_price=1.0, last_candle_ms=data[31]["end_ms"])
        after, events, snapshots = demo.process_candles("test", state, data)
        self.assertEqual([e[2] for e in events], ["SIGNAL SELL"])
        self.assertAlmostEqual(float(events[0][4]), 79 * (1 - demo.SLIPPAGE_PCT), places=3)
        self.assertEqual(events[0][0], demo.timestamp(data[33]["end_ms"] - INTERVAL_MS + 1))
        self.assertEqual(after["units"], 0)

    def test_stale_state_fails_closed(self):
        data = candles([100] * 30)
        state = demo.empty_account()
        state["last_candle_ms"] = 123456
        with self.assertRaises(MarketDataError):
            demo.process_candles("test", state, data)

    def test_corrupt_account_fails_closed(self):
        state = demo.empty_account()
        state["cash"] = float("nan")
        with self.assertRaises(MarketDataError):
            demo.check_account(state)
        state = demo.empty_account()
        state["units"] = 4
        with self.assertRaises(MarketDataError):
            demo.check_account(state)

    def test_persistence_and_no_duplicate_rows(self):
        data = candles([100] * 30)
        feeds = {"binance": ("Binance", lambda now: data),
                 "hyperliquid": ("Hyperliquid", lambda now: data)}
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            demo.run(directory, feeds, NOW)
            p = directory / "ledger" / "state.json"
            self.assertTrue(p.exists())
            with (directory / "ledger" / "equity.csv").open() as f:
                self.assertEqual(len(list(csv.reader(f))), 3)
            demo.run(directory, feeds, NOW)
            with (directory / "ledger" / "equity.csv").open() as f:
                self.assertEqual(len(list(csv.reader(f))), 3)
            state = json.loads(p.read_text())
            self.assertEqual(state["markets"]["binance"]["cash"], 10000.)
            self.assertTrue((directory / "ledger" / "trades.csv").exists())

    def test_market_failure_does_not_commit_partial_data(self):
        data = candles([100] * 30)
        def bad(_):
            raise MarketDataError("bad feed")
        with TemporaryDirectory() as directory:
            feeds = {"binance": ("Binance", lambda now: data),
                     "hyperliquid": ("Hyperliquid", bad)}
            with self.assertRaises(MarketDataError):
                demo.run(directory, feeds, NOW)
            self.assertFalse((Path(directory) / "ledger").exists())
