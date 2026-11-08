"""Network-free regression tests for the isolated virtual five-role lab."""
import unittest
from agent_lab import (LIVE_ORDERS_ENABLED, MAX_POSITION_PCT, check_candles,
                       evaluate_market, market_scanner, paper_trader,
                       performance_analyst, place_live_order, risk_manager, run,
                       strategy_agent)


def bars(prices):
    result = []
    for i, close in enumerate(prices):
        prev = prices[i - 1] if i else close
        result.append({"end_ms": 1700000000000 + i * 3600000,
                       "open": prev, "close": close,
                       "high": max(prev, close), "low": min(prev, close)})
    return result


class FiveRoleTests(unittest.TestCase):
    def setUp(self):
        self.candles = bars([100] * 23 + [101] + [101] * 4 + [99] * 4)

    def test_live_order_hard_block(self):
        self.assertIs(LIVE_ORDERS_ENABLED, False)
        with self.assertRaises(RuntimeError):
            place_live_order("BTC", "BUY")

    def test_next_open_signal_only(self):
        self.assertEqual(strategy_agent(market_scanner(self.candles[:24])), "BUY_WATCH")
        trades = paper_trader(self.candles)["trades"]
        self.assertEqual(trades[0]["action"], "BUY")
        self.assertEqual(trades[0]["asof_ms"], self.candles[24]["end_ms"])

    def test_risk_gates(self):
        allowed = risk_manager("BUY_WATCH", 10000, 10000, 0, 10000, False, 0.01)
        self.assertEqual(allowed["allocation"], MAX_POSITION_PCT * 10000)
        self.assertEqual(risk_manager("BUY_WATCH", 9900, 9900, 0, 10000, False, 0)["action"], "HOLD")
        self.assertEqual(risk_manager("BUY_WATCH", 10000, 10000, 0, 10000, True, 0)["action"], "HOLD")
        self.assertEqual(risk_manager("BUY_WATCH", 10000, 10000, 0, 10000, False, .09)["action"], "HOLD")

    def test_hourly_timestamp_validation(self):
        for delta in (0, 300000, 7200000):
            broken = [dict(x) for x in self.candles]
            for x in broken[5:]:
                x["end_ms"] += delta - 3600000
            with self.assertRaises(ValueError):
                check_candles(broken)

    def test_bad_ohlc_validation(self):
        broken = [dict(x) for x in self.candles]
        broken[4]["high"] = 0
        with self.assertRaises(ValueError):
            check_candles(broken)

    def test_gap_stop_conservative(self):
        data = bars([100] * 23 + [101, 101, 90, 90])
        stops = [t for t in paper_trader(data)["trades"] if t["action"] == "STOP_SELL"]
        self.assertTrue(stops)
        self.assertLessEqual(stops[0]["fill"], data[25]["open"])

    def test_zero_trades_no_invented_win_rate(self):
        result = performance_analyst(paper_trader(bars([100] * 28)))
        self.assertIsNone(result["win_rate_pct"])
        self.assertEqual(result["virtual_transactions"], 0)
        self.assertEqual(result["ending_virtual_usd"], 10000)

    def test_feeds_fail_closed(self):
        def ok(_):
            return self.candles
        def fail(_):
            raise ValueError("bad public feed")
        with self.assertRaises(ValueError):
            run(feeds={"binance_spot": ok, "hyperliquid_perpetual": fail})
        result = run(feeds={"binance_spot": ok, "hyperliquid_perpetual": ok})
        self.assertFalse(result["real_orders_enabled"])
        self.assertEqual(len(result["markets"]), 2)
        self.assertIn("paper_performance", evaluate_market(self.candles))


if __name__ == "__main__":
    unittest.main()
